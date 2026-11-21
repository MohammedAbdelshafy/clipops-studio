"""Read-only Google Drive metadata and ranged-content client for ClipOps Studio.

This adapter intentionally does not include a second media spool.
Studio's existing UploadStore owns all resumable transfer checkpoints.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Callable, Protocol
from urllib.parse import quote, urlsplit, parse_qs

ALLOWED_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})

# A hard allowlist of Google-owned request destinations avoids arbitrary URL fetches
# and SSRF from untrusted pasted folder links.
_DRIVE_API = "https://www.googleapis.com/drive/v3/files"
_FOLDER_RE = re.compile(r"^[a-zA-Z0-9_-]{10,128}$")
_FILE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{10,128}$")
_MD5 = re.compile(r"^[a-fA-F0-9]{32}$")
_RESOURCE_KEY = re.compile(r"^[a-zA-Z0-9_-]{1,256}$")
_MEDIA_MIMES = {
    "video/mp4", "video/quicktime", "video/x-matroska", "video/webm",
    "video/x-msvideo", "video/x-m4v", "application/octet-stream",
}


class DriveImportError(ValueError):
    """Invalid URL, permissions, unsupported asset, or inconsistent remote bytes."""


class DriveImportCancelled(DriveImportError):
    """An authenticated owner requested cancellation of an in-flight import."""


@dataclass(frozen=True)
class DriveFolderReference:
    folder_id: str
    resource_key: str | None = None


def parse_drive_folder_reference(link: str) -> DriveFolderReference:
    """Parse link-shared folders, keeping Google's optional resource key private."""
    if not isinstance(link, str) or len(link) > 2048:
        raise DriveImportError("A Google Drive folder URL is required")
    parts = urlsplit(link.strip())
    if parts.scheme != "https" or parts.hostname != "drive.google.com" or parts.port is not None:
        raise DriveImportError("Use an HTTPS drive.google.com folder link")
    if parts.username or parts.password or parts.fragment:
        raise DriveImportError("Malformed Google Drive folder URL")
    keys = parse_qs(parts.query, keep_blank_values=True)
    entries = keys.get("resourcekey", [])
    if len(entries) > 1 or (entries and not _RESOURCE_KEY.fullmatch(entries[0])):
        raise DriveImportError("Invalid Google Drive folder resource key")
    components = [p for p in parts.path.split("/") if p]
    if len(components) >= 2 and components[0] == "drive":
        remainder = components[1:]
        if len(remainder) >= 3 and remainder[0] == "u" and remainder[1].isdigit():
            remainder = remainder[2:]
        if len(remainder) == 2 and remainder[0] == "folders":
            folder_id = remainder[1]
            if _FOLDER_RE.fullmatch(folder_id):
                return DriveFolderReference(folder_id, entries[0] if entries else None)
    raise DriveImportError("Expected https://drive.google.com/drive/folders/FOLDER_ID")


def parse_drive_folder_link(link: str) -> str:
    """Compatibility helper returning only the folder ID, not its resource key."""
    return parse_drive_folder_reference(link).folder_id


@dataclass(frozen=True)
class DriveVideo:
    id: str
    name: str
    size: int
    mime_type: str
    version: str
    md5_checksum: str | None
    download_allowed: bool
    resource_key: str | None = None


class DriveReader(Protocol):
    def metadata(self, file_id: str, resource_key: str | None = None) -> dict: ...
    def list_children(self, folder_id: str, page_token: str | None = None,
                      folder_resource_key: str | None = None) -> dict: ...
    def read_range(self, file_id: str, start: int, length: int, total: int,
                   resource_key: str | None = None) -> bytes: ...


class GoogleDriveV3Reader:
    """Small official-API HTTP adapter; no untrusted download URL is ever fetched.

    token_supplier must return a valid short-lived token (and refresh as needed).
    Redirects are blocked to avoid inadvertently forwarding Authorization to
    an unexpected host; there is no public-link scraping or anonymous fallback.
    """

    def __init__(self, token_supplier: Callable[[], str], *, timeout: int = 90, session=None):
        import requests  # optional runtime dependency: requests >=2.32,<3
        self._session = session or requests.Session()
        self._session.trust_env = False
        self._token_supplier = token_supplier
        self._timeout = timeout

    def _get(self, url: str, *, params: dict | None = None, headers: dict | None = None, stream=False):
        token = self._token_supplier()
        if not isinstance(token, str) or not token.strip():
            raise DriveImportError("Google Drive is not connected for this user")
        request_headers = {"Authorization": f"Bearer {token}", "Accept-Encoding": "identity"}
        request_headers.update(headers or {})
        try:
            response = self._session.get(url, params=params, headers=request_headers,
                                         timeout=self._timeout, stream=stream, allow_redirects=False)
        except Exception as exc:
            raise DriveImportError("Google Drive request failed; retry after checking connection") from exc
        if 300 <= response.status_code < 400:
            response.close()
            raise DriveImportError("Unexpected Google Drive redirect; refused to forward credentials")
        if response.status_code in (401, 403):
            response.close()
            raise DriveImportError("Google Drive access denied or expired; reconnect or request access")
        if response.status_code in (404,):
            response.close()
            raise DriveImportError("Google Drive item not found or not shared with this account")
        if response.status_code >= 400:
            status = response.status_code
            response.close()
            raise DriveImportError(f"Google Drive request failed (HTTP {status})")
        return response

    @staticmethod
    def _resource_key_header(file_id: str, resource_key: str | None) -> dict:
        _require_id(file_id)
        if resource_key is None:
            return {}
        if not isinstance(resource_key, str) or not _RESOURCE_KEY.fullmatch(resource_key):
            raise DriveImportError("Invalid Google Drive resource key")
        return {"X-Goog-Drive-Resource-Keys": f"{file_id}/{resource_key}"}

    def metadata(self, file_id: str, resource_key: str | None = None) -> dict:
        _require_id(file_id)
        with self._get(f"{_DRIVE_API}/{quote(file_id, safe='')}", params={
            "fields": "id,name,mimeType,size,version,md5Checksum,parents,resourceKey,capabilities(canDownload),trashed",
            "supportsAllDrives": "true",
        }, headers=self._resource_key_header(file_id, resource_key)) as response:
            return response.json()

    def list_children(self, folder_id: str, page_token: str | None = None,
                      folder_resource_key: str | None = None) -> dict:
        _require_id(folder_id)
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "pageSize": 100,
            "fields": "nextPageToken,files(id,name,mimeType,size,version,md5Checksum,resourceKey,parents,capabilities(canDownload),trashed)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        with self._get(_DRIVE_API, params=params,
                       headers=self._resource_key_header(folder_id, folder_resource_key)) as response:
            return response.json()

    def read_range(self, file_id: str, start: int, length: int, total: int,
                   resource_key: str | None = None) -> bytes:
        _require_id(file_id)
        if length < 1 or start < 0 or start + length > total:
            raise DriveImportError("Invalid Drive download range")
        end = start + length - 1
        with self._get(f"{_DRIVE_API}/{quote(file_id, safe='')}", params={"alt": "media", "supportsAllDrives": "true"},
                       headers={"Range": f"bytes={start}-{end}",
                                **self._resource_key_header(file_id, resource_key)}, stream=True) as response:
            if response.status_code != 206:
                raise DriveImportError("Google Drive ignored byte range; refusing unbounded download")
            content_range = response.headers.get("Content-Range", "")
            if content_range != f"bytes {start}-{end}/{total}":
                raise DriveImportError("Google Drive returned an inconsistent content range")
            buffer = bytearray()
            # Never call response.content: it could buffer the whole 20 GB object.
            for chunk in response.iter_content(chunk_size=min(1024 * 1024, length)):
                buffer.extend(chunk)
                if len(buffer) > length:
                    raise DriveImportError("Google Drive returned more bytes than requested")
            if len(buffer) != length:
                raise DriveImportError("Incomplete Google Drive ranged response")
            return bytes(buffer)


def _require_id(file_id: str) -> None:
    if not isinstance(file_id, str) or _FILE_ID_RE.fullmatch(file_id) is None:
        raise DriveImportError("Invalid Drive item ID")


def _video_from_metadata(value: dict, *, require_parent: str | None = None) -> DriveVideo:
    file_id = value.get("id")
    _require_id(file_id)
    name = value.get("name")
    mime = value.get("mimeType")
    if value.get("trashed") or not isinstance(name, str):
        raise DriveImportError("Invalid or deleted Google Drive item")
    # Our ingest core enforces filenames and extensions too. Do not sanitize
    # silently: a dangerous or ambiguous remote filename must be renamed by user.
    # Match Studio's import-name contract before creating a durable upload
    # checkpoint. This also rejects CR/LF injection in local logs and reports.
    if (not 1 <= len(name) <= 180 or Path(name).name != name or
            "\\" in name or any(ord(character) < 32 for character in name)):
        raise DriveImportError("Invalid Google Drive media filename")
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS or mime not in _MEDIA_MIMES:
        raise DriveImportError("Google Drive item is not a supported video file")
    if require_parent is not None and require_parent not in value.get("parents", []):
        raise DriveImportError("The video no longer belongs to the selected folder")
    try:
        size = int(value.get("size", ""))
    except (ValueError, TypeError):
        raise DriveImportError("Google Drive file size is not available") from None
    if size <= 0:
        raise DriveImportError("Cannot import an empty video")
    version = str(value.get("version") or "")
    if not version:
        raise DriveImportError("Missing Drive source version; refusing unsafe resume")
    md5 = value.get("md5Checksum")
    if md5 is not None and not _MD5.fullmatch(md5):
        raise DriveImportError("Invalid Drive MD5 metadata")
    resource_key = value.get("resourceKey")
    if resource_key is not None and (not isinstance(resource_key, str) or
                                     not _RESOURCE_KEY.fullmatch(resource_key)):
        raise DriveImportError("Invalid Drive item resource key")
    return DriveVideo(id=file_id, name=name, size=size, mime_type=mime,
                      version=version, md5_checksum=md5 and md5.lower(),
                      download_allowed=(value.get("capabilities") or {}).get("canDownload") is True,
                      resource_key=resource_key)


class DriveFolderImporter:
    """Preview/choose/start/resume; never bulk-import without file selection."""

    def __init__(self, ingest: object, reader: DriveReader):
        self.ingest = ingest
        self.reader = reader

    def preview(self, folder_link: str, *, max_pages: int = 20) -> list[DriveVideo]:
        reference = parse_drive_folder_reference(folder_link)
        folder_id = reference.folder_id
        folder = self.reader.metadata(folder_id, resource_key=reference.resource_key)
        if folder.get("mimeType") != "application/vnd.google-apps.folder" or folder.get("trashed"):
            raise DriveImportError("Google Drive link does not point to an accessible folder")
        items: list[DriveVideo] = []
        next_token = None
        seen_tokens: set[str] = set()
        for _ in range(max_pages):
            page = self.reader.list_children(folder_id, next_token,
                                             folder_resource_key=reference.resource_key)
            for entry in page.get("files", []):
                try:
                    v = _video_from_metadata(entry)
                except DriveImportError:
                    continue  # Skip folders, native Docs and unsupported objects.
                if v.size <= self.ingest.max_size and v.download_allowed:
                    items.append(v)
            next_token = page.get("nextPageToken")
            if not next_token:
                return items
            if next_token in seen_tokens:
                raise DriveImportError("Google Drive returned a repeated page token")
            seen_tokens.add(next_token)
        raise DriveImportError("Folder contains too many pages; narrow the folder selection")

