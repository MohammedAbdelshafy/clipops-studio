"""Review-only Google Drive -> canonical ClipOps Studio UploadStore adapter.

Uses the existing Studio resumable upload checkpoints (no parallel media spool).
No HTTP/OAuth endpoints, implicit worker, or public deployment are installed.
The host must provide an authenticated DriveReader and existing Studio session.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import md5, sha256
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import hmac
import os

from studio_drive_reader import (
    DriveFolderImporter, DriveImportError, DriveImportCancelled,
    DriveVideo, _video_from_metadata, parse_drive_folder_reference,
)


class StudioDriveBridge:
    """Copies source bytes into Studio's own TUS UploadStore and checks provenance.

    All methods are synchronous; ``copy_pass`` must run in an authorized worker,
    never on an HTTP request thread. The caller enforces active-session auth,
    CSRF, job ownership, worker lease, disk quota and cancellation policy.
    """

    def __init__(self, upload_store, drive_reader, *, max_chunk=8 * 1024**2):
        if not 0 < max_chunk <= upload_store.chunk:
            raise ValueError("Drive chunk may not exceed the Studio upload limit")
        self.store = upload_store
        self.reader = drive_reader
        self.chunk = max_chunk

    def preview(self, folder_url: str) -> list[dict]:
        # Reuse link validation, pagination and filtering rather than reimplementing.
        importer = DriveFolderImporter(SimpleNamespace(max_size=self.store.capacity), self.reader)
        return [{k: v for k, v in asdict(item).items() if k != "resource_key"}
                for item in importer.preview(folder_url)]

    def start(self, folder_url: str, file_id: str, spec: dict, *, rights_confirmed: bool) -> dict:
        if rights_confirmed is not True:
            raise DriveImportError("Rights confirmation required before importing Drive media")
        if not isinstance(spec, dict) or spec.get("filename") is None:
            raise DriveImportError("A validated Studio import specification is required")
        ref = parse_drive_folder_reference(folder_url)
        importer = DriveFolderImporter(SimpleNamespace(max_size=self.store.capacity), self.reader)
        videos = importer.preview(folder_url)
        chosen = next((v for v in videos if v.id == file_id), None)
        if chosen is None:
            raise DriveImportError("Selected file is not downloadable from this folder")
        if spec["filename"] != chosen.name:
            raise DriveImportError("Selected video does not match Studio import metadata")
        # Do not preserve a client-supplied Drive binding in the metadata object.
        if "drive_source" in spec:
            raise DriveImportError("Drive source metadata is server-managed")
        current = _video_from_metadata(
            self.reader.metadata(chosen.id, resource_key=chosen.resource_key),
            require_parent=ref.folder_id,
        )
        if current != chosen:
            raise DriveImportError("Drive source changed during selection")
        if current.size > self.store.capacity or not current.download_allowed:
            raise DriveImportError("Selected video is unavailable or exceeds the storage limit")
        key = uuid4().hex
        metadata = dict(spec)
        metadata["drive_source"] = {
            "folder_id": ref.folder_id,
            "folder_resource_key": ref.resource_key,
            "file": asdict(current),
        }
        state = self.store.begin(key, current.size, metadata)
        return self._status(key, state)

    @staticmethod
    def _status(key: str, state: dict) -> dict:
        return {"upload_id": key, "total_bytes": state["size"],
                "received_bytes": state["offset"],
                "state": "complete" if state.get("done") else "queued"}

    def _binding(self, key: str) -> tuple[dict, DriveVideo]:
        state = self.store.inspect(key)
        try:
            source = state["metadata"]["drive_source"]
            old = DriveVideo(**source["file"])
            if source["folder_id"] not in self.reader.metadata(
                old.id, resource_key=old.resource_key).get("parents", []):
                raise DriveImportError("Source video was moved out of the shared Drive folder")
        except (KeyError, TypeError, ValueError) as exc:
            raise DriveImportError("Import has no valid Drive source binding") from exc
        return state, old

    def _fresh(self, state: dict, old: DriveVideo) -> None:
        source = state["metadata"]["drive_source"]
        current = _video_from_metadata(
            self.reader.metadata(old.id, resource_key=old.resource_key),
            require_parent=source["folder_id"],
        )
        if current != old or not current.download_allowed:
            raise DriveImportError("Drive source changed or access was revoked")

    def copy_pass(self, upload_id: str, *, max_chunks: int = 4,
                  continue_allowed=None) -> dict:
        """Advance a checkpoint by at most max_chunks * 8 MiB; no auto-finalize.

        One worker must own an exclusive job lease. A caller-supplied predicate
        can fail closed on user cancellation between network reads and writes.
        """
        if type(max_chunks) is not int or not 1 <= max_chunks <= 16:
            raise ValueError("max_chunks must be within 1..16")
        state, old = self._binding(upload_id)
        self._fresh(state, old)
        if state.get("done"):
            return self._status(upload_id, state)
        for _ in range(max_chunks):
            if continue_allowed is not None and not continue_allowed():
                raise DriveImportCancelled("Import cancelled")
            if state["offset"] >= state["size"]:
                break
            offset = state["offset"]
            count = min(self.chunk, state["size"] - offset)
            block = self.reader.read_range(
                old.id, offset, count, state["size"], resource_key=old.resource_key)
            if len(block) != count:
                raise DriveImportError("Source returned an incomplete media range")
            if continue_allowed is not None and not continue_allowed():
                raise DriveImportCancelled("Import cancelled")
            state = self.store.append(upload_id, offset, count, sha256(block).digest(), BytesIO(block))
        self._fresh(state, old)
        return self._status(upload_id, state)

    def verify_complete(self, upload_id: str) -> dict:
        """Verify transfer and Drive checksum before Studio finish()/render.

        No file is marked imported merely because bytes reached the target size.
        """
        state, old = self._binding(upload_id)
        self._fresh(state, old)
        if state.get("done"):
            return self._status(upload_id, state)
        if state["offset"] != state["size"]:
            raise DriveImportError("Media transfer is not complete")
        part = self.store.path(upload_id) / state["metadata"]["filename"]
        if not part.is_file() or part.is_symlink() or part.stat().st_size != old.size:
            raise DriveImportError("Staged video file has an invalid size")
        if old.md5_checksum:
            checksum = md5(usedforsecurity=False)
            with part.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    checksum.update(chunk)
            if not hmac.compare_digest(checksum.hexdigest(), old.md5_checksum):
                raise DriveImportError("Downloaded bytes failed the Google Drive integrity check")
        return self._status(upload_id, state)
