"""Cross-platform file locking for ClipOps lease files.

POSIX uses flock + O_NOFOLLOW exactly as before. Windows has neither, so it
uses msvcrt byte-range locking and a plain os.open. The public helpers keep
callers unchanged, so Linux/WSL behaviour is byte-for-byte identical.
"""
from __future__ import annotations

import contextlib
import os
import threading
import time
from pathlib import Path

NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
DIRECTORY = getattr(os, "O_DIRECTORY", 0)
NONBLOCK = getattr(os, "O_NONBLOCK", 0)
LEASE_FLAGS = os.O_CREAT | os.O_RDWR | NOFOLLOW

try:  # POSIX: unchanged behaviour.
    import resource
except ImportError:  # pragma: no cover - Windows
    class _Usage:
        ru_utime = 0.0
        ru_stime = 0.0
        ru_maxrss = 0

    class _Resource:
        RUSAGE_SELF = 0
        RUSAGE_CHILDREN = 1

        @staticmethod
        def getrusage(_who):
            return _Usage()

    resource = _Resource()


@contextlib.contextmanager
def exclusive(fd: int, wait: bool = False):
    """Hold an exclusive advisory lock on fd for the duration of the block."""
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        mode = msvcrt.LK_LOCK if wait else msvcrt.LK_NBLCK
        try:
            msvcrt.locking(fd, mode, 1)
        except OSError as exc:
            # Match the POSIX exception that callers already translate.
            raise BlockingIOError("lock is held by another worker") from exc
        try:
            yield
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)


_CURRENT_SID = None
_WINDOWS_ACL_CACHE = {}


def _current_sid():
    """Return the current Windows SID, resolved once per process."""
    global _CURRENT_SID
    if _CURRENT_SID is None:
        try:
            import subprocess
            out = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                                 capture_output=True, text=True, check=True).stdout
            sid = out.strip().split('","')[-1].strip('"')
            _CURRENT_SID = sid if sid.upper().startswith("S-1-") else False
        except Exception:
            _CURRENT_SID = False
    return _CURRENT_SID or None


def _allowed_sids():
    """SIDs that may hold access without making the directory shared.

    Windows has no 0700 mode bit; a private directory is one whose DACL grants
    only the owning account plus the local SYSTEM/Administrator aliases.
    """
    # S-1-3-0 = CREATOR OWNER, S-1-3-4 = OWNER RIGHTS; Windows uses these
    # placeholders in place of an explicit owner grant on inherited DACLs.
    allowed = {"S-1-5-18", "S-1-5-32-544", "S-1-3-0", "S-1-3-4"}
    sid = _current_sid()
    if sid:
        allowed.add(sid)
    return allowed


def _dacl_sids(path):
    """ACCESS_ALLOWED SIDs on `path`, or None when they cannot be read.

    Reads advapi32 directly instead of shelling out, so the verdict is stable
    and cheap: the media pipeline replaces subprocess.run with test doubles,
    and a per-request icacls/whoami round trip is pure overhead.
    """
    import ctypes
    from ctypes import wintypes

    class AceHeader(ctypes.Structure):
        _fields_ = [("AceType", wintypes.BYTE), ("AceFlags", wintypes.BYTE),
                    ("AceSize", wintypes.WORD)]

    class Acl(ctypes.Structure):
        _fields_ = [("AclRevision", wintypes.BYTE), ("Sbz1", wintypes.BYTE),
                    ("AclSize", wintypes.WORD), ("AceCount", wintypes.WORD),
                    ("Sbz2", wintypes.WORD)]

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_info = advapi32.GetNamedSecurityInfoW
    get_info.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
                         ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                         ctypes.POINTER(ctypes.c_void_p)]
    get_info.restype = wintypes.DWORD
    get_ace = advapi32.GetAce
    get_ace.argtypes = [ctypes.c_void_p, wintypes.DWORD,
                        ctypes.POINTER(ctypes.c_void_p)]
    get_ace.restype = wintypes.BOOL
    to_string = advapi32.ConvertSidToStringSidW
    to_string.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    to_string.restype = wintypes.BOOL

    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    if get_info(str(path), 1, 0x4, None, None,
                ctypes.byref(dacl), None, ctypes.byref(descriptor)) != 0:
        return None
    if not dacl:
        return []  # A null DACL grants everyone access.
    try:
        acl = ctypes.cast(dacl, ctypes.POINTER(Acl)).contents
        sids = []
        for index in range(acl.AceCount):
            ace = ctypes.c_void_p()
            if not get_ace(dacl, index, ctypes.byref(ace)) or not ace:
                return None
            header = ctypes.cast(ace, ctypes.POINTER(AceHeader)).contents
            if header.AceType != 0:  # Only ACCESS_ALLOWED_ACE is relevant.
                return None
            # ACCESS_ALLOWED_ACE: header (4) + mask (4) then the SID.
            text = ctypes.c_void_p()
            if not to_string(ctypes.c_void_p(ace.value + ctypes.sizeof(AceHeader) + 4),
                             ctypes.byref(text)) or not text:
                return None
            try:
                sids.append(ctypes.cast(text, ctypes.c_wchar_p).value)
            finally:
                kernel32.LocalFree(text)
        return sids
    finally:
        if descriptor:
            kernel32.LocalFree(descriptor)


def sync_directory(path):
    """Durably flush a directory on POSIX; Windows cannot open dirs this way."""
    if os.name == "nt":
        return None
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def replace_file(source, target, *, attempts=100, delay=0.005):
    """Install `source` over `target`, retrying through a concurrent reader.

    Windows refuses MoveFileEx(REPLACE_EXISTING) while any handle to the target
    is open -- even one that grants FILE_SHARE_DELETE -- so a reader can make
    os.replace fail with WinError 5. Callers that share one file serialise their
    readers and writers with `serialised`; this retry covers readers that do
    not, and re-raises if the handle is genuinely long lived. POSIX keeps the
    single plain syscall.
    """
    if os.name != "nt":
        os.replace(source, target)
        return
    for remaining in range(attempts, 0, -1):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if remaining == 1:
                raise
            time.sleep(delay)


_FILE_LOCKS = {}
_FILE_LOCKS_GUARD = threading.Lock()


@contextlib.contextmanager
def serialised(path, *, timeout=30.0):
    """Exclude concurrent readers and writers of one file within this process.

    ClipOps writes project state atomically (temp file plus rename) from its
    render worker while HTTP handlers read the same file. Windows cannot replace
    a file that any handle still has open, so retrying alone cannot make that
    safe; both sides take this per-path lock instead. Process-local is enough
    because the worker and the readers live in one process, and POSIX keeps the
    same call shape without needing the lock.
    """
    key = str(path)
    with _FILE_LOCKS_GUARD:
        lock = _FILE_LOCKS.setdefault(key, threading.Lock())
    if not lock.acquire(timeout=timeout):
        raise TimeoutError(f"timed out waiting to access {key}")
    try:
        yield
    finally:
        lock.release()


@contextlib.contextmanager
def shared_read(path, *, attempts=100 if os.name == "nt" else 1, delay=0.005):
    """Yield an open reader for `path`, tolerating a transient sharing denial.

    An atomic replace leaves a brief window in which a concurrent open of the
    target is denied with EACCES, so a reader of project or transcript JSON can
    fail even though the writer is about to succeed. Readers retry briefly
    because the writer converges; POSIX keeps a single plain open. A genuinely
    missing file is not retried -- it propagates at once, because retrying it
    would cost the caller the full retry budget on every absent-file lookup.
    """
    for remaining in range(attempts, 0, -1):
        try:
            stream = open(path, encoding="utf-8-sig")
        except PermissionError:
            if remaining == 1:
                raise
            time.sleep(delay)
            continue
        try:
            yield stream
        finally:
            stream.close()
        return


def is_private_path(path, *, directory=False):
    """POSIX: exactly the old mode-bit test. Windows: the DACL must grant only
    the owning account, SYSTEM and Administrators (Windows has no real 0700).

    The verdict is cached per resolved path: an ACL change mid-process is not
    re-read, which is the right trade for a single-user desktop store and keeps
    the check off the per-request hot path.
    """
    path = Path(path)
    if os.name != "nt":
        return not path.stat().st_mode & 0o077
    key = str(path.resolve())
    if key in _WINDOWS_ACL_CACHE:
        return _WINDOWS_ACL_CACHE[key]
    sids = _dacl_sids(path)
    verdict = bool(sids) and all(sid in _allowed_sids() for sid in sids)
    if len(_WINDOWS_ACL_CACHE) > 512:
        _WINDOWS_ACL_CACHE.clear()
    _WINDOWS_ACL_CACHE[key] = verdict
    return verdict


def restrict_private_file(path):
    """Make a credential file private on both POSIX and Windows."""
    import stat as _stat
    from pathlib import Path as _Path
    path = _Path(path)
    try:
        path.chmod(_stat.S_IRUSR | _stat.S_IWUSR)
    except OSError:
        pass
    if os.name != "nt":
        return
    sid = _current_sid()
    if not sid:
        raise RuntimeError("Cannot resolve Windows SID for private credential file")
    import subprocess
    for args in (["icacls", str(path), "/inheritance:r"],
                 ["icacls", str(path), "/grant:r", f"*{sid}:(F)"]):
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError("Cannot set private ACL on credential file")


def font_path(family):
    """Windows replacement for `fc-match`; POSIX callers keep fc-match."""
    if os.name != "nt":
        return None
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    needles = [n for n in str(family).lower().split() if len(n) > 2]
    candidates = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1
                low = name.lower()
                if any(n in low for n in needles) and ("bold" in low or "bd" in low):
                    candidates.append(fonts / str(value).split(",")[0])
    except Exception:
        pass
    candidates += [fonts / n for n in ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf")]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None
