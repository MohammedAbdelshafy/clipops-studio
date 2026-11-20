"""Cross-platform file locking for ClipOps lease files.

POSIX uses flock + O_NOFOLLOW exactly as before. Windows has neither, so it
uses msvcrt byte-range locking and a plain os.open. The public helpers keep
callers unchanged, so Linux/WSL behaviour is byte-for-byte identical.
"""
from __future__ import annotations

import contextlib
import os
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


def _current_sid():
    """Return the current Windows SID without third-party dependencies."""
    try:
        import subprocess
        out = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                             capture_output=True, text=True, check=True).stdout
        sid = out.strip().split('","')[-1].strip('"')
        return sid if sid.upper().startswith("S-1-") else None
    except Exception:
        return None


def _private_principals():
    allowed = {"SYSTEM", "BUILTIN\\Administrators", "OWNER RIGHTS", "CREATOR OWNER"}
    user = os.environ.get("USERNAME", "")
    if user:
        allowed.add(user)
    sid = _current_sid()
    if sid:
        allowed.update((sid, "*" + sid))
    return allowed


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


def is_private_path(path, *, directory=False):
    """POSIX: exactly the old mode-bit test. Windows: verify the ACL grants
    only the owner, SYSTEM and Administrators (Windows has no real 0700)."""
    from pathlib import Path as _Path
    path = _Path(path)
    if os.name != "nt":
        return not path.stat().st_mode & 0o077
    try:
        import subprocess
        out = subprocess.run(["icacls", str(path)], capture_output=True,
                             text=True, check=True).stdout
    except Exception:
        return False
    import re
    # icacls prints grants as `PRINCIPAL:(RIGHTS)`; the first line also carries
    # the path. Match only entries followed by an ACL flag, never `C:\...`.
    grants = []
    for number, line in enumerate(out.splitlines()):
        idx = line.find(":(")
        if idx < 0:
            continue
        principal = line[:idx].strip()
        if number == 0:
            principal = principal.replace(str(path), "").strip()
        rights = line[idx:]
        if principal and ":\\" not in principal and "(D)" not in rights:
            grants.append(principal)
    principals = grants
    allowed = {p.lower() for p in _private_principals()}
    machine = os.environ.get("COMPUTERNAME", "")
    user = os.environ.get("USERNAME", "")
    if machine and user:
        allowed.add((machine + "\\" + user).lower())
    allowed.update({"nt authority\\system", "builtin\\administrators",
                    "owner rights", "creator owner"})
    return bool(principals) and all(p.lower() in allowed for p in principals)


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
