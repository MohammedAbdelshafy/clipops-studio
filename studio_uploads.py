"""Private, bounded tus offset and checksum transport for a single Studio workspace."""
from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import format_datetime
import fcntl
import hashlib
import hmac
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from uuid import uuid4

from pilot import MAX_MEDIA, load_json, private_root, save_json, sync_directory

TUS = "1.0.0"
PART_BYTES = 8 * 1024**2
RESERVE_BYTES = 64 * 1024**2
MAX_SESSIONS = 8
TTL = 24 * 60 * 60
ID = re.compile(r"[a-f0-9]{32}")
EMPTY_RECEIPT = "00" * 32


class UploadError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


@contextmanager
def lease(path):
    fd = os.open(path, os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise UploadError(409, "This upload is busy. Retry from the saved offset.") from exc
        yield
    finally:
        os.close(fd)


def checksum(value):
    try:
        algorithm, encoded = value.split()
        digest = base64.b64decode(encoded, validate=True)
        if algorithm != "sha256" or len(digest) != 32:
            raise ValueError
    except (ValueError, binascii.Error):
        raise UploadError(400, "Provide an Upload-Checksum using SHA-256.") from None
    return digest


def update(path, state):
    save_json(path / "upload.json", state)


def expires(state):
    return format_datetime(datetime.fromtimestamp(state["expires"], timezone.utc), usegmt=True)


class UploadStore:
    def __init__(self, root, *, capacity=MAX_MEDIA, chunk=PART_BYTES, ttl=TTL):
        self.location = private_root(Path(root) / ".uploads")
        self.capacity = capacity
        self.chunk = chunk
        self.ttl = ttl

    def path(self, key):
        if not isinstance(key, str) or not ID.fullmatch(key):
            raise UploadError(404, "Unknown upload.")
        path = self.location / key
        if path.is_symlink() or not path.is_dir():
            raise UploadError(404, "Unknown or expired upload.")
        return path

    def state(self, path):
        state = load_json(path / "upload.json")
        if state["expires"] <= time.time():
            raise UploadError(410, "The upload expired. Choose the file again.")
        return state

    def inspect(self, key):
        return self.state(self.path(key))

    def _reserved(self):
        remaining = active = 0
        for path in self.location.iterdir():
            if path.is_symlink() or not path.is_dir():
                continue
            if path.name.startswith((".pending-", ".discard-")):
                if time.time() - path.stat().st_mtime >= self.ttl:
                    shutil.rmtree(path, ignore_errors=True)
                continue
            if not ID.fullmatch(path.name):
                continue
            try:
                state = load_json(path / "upload.json")
            except (OSError, ValueError):
                continue
            if state["expires"] <= time.time():
                try:
                    with lease(path / ".lock"):
                        # Another worker may have extended the expiry since the scan.
                        if load_json(path / "upload.json")["expires"] <= time.time():
                            shutil.rmtree(path)
                except (UploadError, FileNotFoundError):
                    pass
            elif not state.get("done"):
                active += 1
                remaining += state["size"] - state["offset"]
        return remaining, active

    def begin(self, key, size, metadata):
        if not ID.fullmatch(key):
            raise UploadError(400, "Provide a random upload ID.")
        if type(size) is not int or not 0 < size <= self.capacity:
            raise UploadError(413, "Choose a video up to 20 GiB.")
        with lease(self.location / ".create"):
            path = self.location / key
            if path.is_dir():
                existing = self.inspect(key)
                if existing["size"] != size or (not existing.get("done") and existing["metadata"] != metadata):
                    raise UploadError(409, "This ID already belongs to another upload.")
                return existing
            reserved, active = self._reserved()
            if active >= MAX_SESSIONS:
                raise UploadError(429, "The workspace has too many unfinished uploads.")
            if size + reserved + RESERVE_BYTES > shutil.disk_usage(self.location).free:
                raise UploadError(507, "This disk needs space for the video and working files.")
            with tempfile.TemporaryDirectory(dir=self.location, prefix=".pending-") as pending:
                stage = Path(pending) / "upload"
                stage.mkdir(mode=0o700)
                media = stage / metadata["filename"]
                fd = os.open(media, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
                state = {"size": size, "offset": 0, "expires": time.time() + self.ttl,
                         "metadata": metadata, "receipt": EMPTY_RECEIPT}
                update(stage, state)
                stage.rename(path)
                sync_directory(self.location)
            return state

    def append(self, key, offset, size, digest, stream):
        if not 0 < size <= self.chunk:
            raise UploadError(413, "Upload one bounded chunk at a time.")
        path = self.path(key)
        with lease(path / ".lock"):
            state = self.state(path)
            saved = state["offset"]
            if offset != saved or state.get("done"):
                raise UploadError(409, "The upload offset changed. Resume from the saved offset.")
            if offset + size > state["size"]:
                raise UploadError(413, "This chunk exceeds the declared file size.")
            media = path / state["metadata"]["filename"]
            if shutil.disk_usage(path).free < size + RESERVE_BYTES:
                raise UploadError(507, "Disk is full. Free space and resume from the saved offset.")
            fd = os.open(media, os.O_WRONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "wb") as output:
                if os.fstat(fd).st_size < saved:
                    raise UploadError(409, "The upload data is shorter than its saved checkpoint.")
                # A process crash can leave data beyond the last atomic checkpoint.
                output.truncate(saved)
                output.seek(saved)
                sha = hashlib.sha256()
                remaining = size
                try:
                    while remaining:
                        block = stream.read(min(remaining, 256 * 1024))
                        if not block:
                            raise UploadError(400, "The chunk ended early. Resume from the saved offset.")
                        sha.update(block)
                        output.write(block)
                        remaining -= len(block)
                    if not hmac.compare_digest(sha.digest(), digest):
                        raise UploadError(460, "Chunk checksum mismatch. Retry this chunk.")
                    output.flush()
                    os.fsync(fd)
                except BaseException:
                    output.flush()
                    output.truncate(saved)
                    raise
            previous = bytes.fromhex(state.get("receipt", EMPTY_RECEIPT))
            receipt = hashlib.sha256(previous + size.to_bytes(8, "big") + digest).hexdigest()
            state.update(offset=saved + size, expires=time.time() + self.ttl, receipt=receipt)
            update(path, state)
            return state

    def finish(self, key, root, create):
        path = self.path(key)
        with lease(path / ".lock"):
            state = self.state(path)
            if state.get("done"):
                return key, state.get("render_count", 5)
            if state["size"] != state["offset"]:
                raise UploadError(409, "All bytes must be committed before import.")
            metadata = state["metadata"]
            media = path / metadata["filename"]
            if media.is_symlink() or media.stat().st_size != state["size"]:
                raise UploadError(409, "Stored media does not match the completed upload.")
            # The project installs a hardlink and an atomic manifest. If the
            # reply or Studio dies after that install, finalize the same ID.
            installed = Path(root) / key / "project.json"
            if not installed.is_file():
                create(media, path, metadata)
            update(path, {"size": state["size"], "offset": state["offset"], "done": True,
                          "expires": time.time() + self.ttl, "render_count": metadata["render_count"],
                          "receipt": state.get("receipt", EMPTY_RECEIPT)})
            media.unlink()
            (path / "timed-transcript.json").unlink(missing_ok=True)
            return key, metadata["render_count"]

    def cancel(self, key):
        path = self.path(key)
        with lease(path / ".lock"):
            if load_json(path / "upload.json").get("done"):
                raise UploadError(409, "This upload already belongs to an imported project.")
            # Rename before deleting to close the session atomically to new requests.
            removed = path.with_name(".discard-" + uuid4().hex)
            path.rename(removed)
            shutil.rmtree(removed)
            sync_directory(self.location)
