#!/usr/bin/env python3
"""Measure authorized local transfer with one forced Studio restart at a saved checkpoint."""
import argparse
from base64 import b64encode
from contextlib import closing
from hashlib import sha256
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
from time import monotonic
from uuid import uuid4

STUDIO = Path(__file__).resolve().parents[1] / "studio.py"


class Desk:
    def __init__(self, root):
        env = dict(os.environ, CLIPOPS_ALLOW_PUBLISH="0", POSTIZ_API_KEY="", GEMINI_API_KEY="")
        self.process = subprocess.Popen([sys.executable, str(STUDIO), "--root", str(root), "--port", "0"],
                                        stdout=subprocess.PIPE, text=True, env=env)
        line = self.process.stdout.readline()
        match = re.search(r"127\.0\.0\.1:(\d+)", line)
        if not match:
            self.stop()
            raise RuntimeError("Studio failed to start")
        self.port = int(match[1])
        self.headers = {"Tus-Resumable": "1.0.0", "Origin": f"http://127.0.0.1:{self.port}"}
        _, headers, _ = self.request("GET", "/")
        cookie = SimpleCookie(headers["Set-Cookie"])
        self.headers["Cookie"] = "; ".join(f"{k}={v.value}" for k, v in cookie.items())
        _, _, session = self.request("GET", "/api/session")
        info = json.loads(session)
        self.headers["X-ClipOps-CSRF"] = info["csrf"]
        self.chunk = info["chunk_bytes"]

    def request(self, method, url, body=None, headers=None, *, status=200):
        with closing(HTTPConnection("127.0.0.1", self.port, timeout=180)) as conn:
            conn.request(method, url, body, {**self.headers, **(headers or {})})
            reply = conn.getresponse()
            result = reply.status, dict(reply.getheaders()), reply.read()
            if result[0] != status:
                raise RuntimeError(f"{method} returned {result[0]}: {result[2].decode(errors='replace')}")
            return result

    def stop(self):
        self.process.terminate()
        self.process.wait(timeout=10)
        self.process.stdout.close()


def benchmark(root, source, transcript):
    key = uuid4().hex
    size = source.stat().st_size
    spec = {"rights": True, "filename": source.name, "transcript": transcript, "render_count": 0}
    body = json.dumps({"id": key, "size": size, "metadata": spec}, ensure_ascii=False).encode("utf-8")
    started = monotonic()
    desk = Desk(root)
    offset = resumed = 0
    digest = sha256()
    try:
        _, response, _ = desk.request("POST", "/api/uploads", body, {"Content-Type": "application/json"}, status=201)
        path = response["Location"]
        with source.open("rb") as video:
            while chunk := video.read(desk.chunk):
                check = "sha256 " + b64encode(sha256(chunk).digest()).decode()
                _, response, _ = desk.request("PATCH", path, chunk, {"Content-Type": "application/offset+octet-stream",
                                              "Upload-Offset": str(offset), "Upload-Checksum": check}, status=204)
                digest.update(chunk)
                offset += len(chunk)
                assert str(offset) == response["Upload-Offset"]
                if not resumed and offset >= size / 2 and offset < size:
                    desk.stop()
                    desk = Desk(root)
                    _, response, _ = desk.request("HEAD", path)
                    resumed = int(response["Upload-Offset"])
                    assert resumed == offset
        uploaded = monotonic()
        headers = {"Content-Type": "application/json"}
        _, _, reply = desk.request("POST", path + "/complete", b"{}", headers, status=201)
        finished = monotonic()
        assert json.loads(reply)["id"] == key
        saved = json.loads((root / key / "project.json").read_text())
        assert saved["source"]["sha256"] == digest.hexdigest()
        assert not (root / ".uploads" / key / source.name).exists()
    finally:
        desk.stop()
    resources = resource.getrusage(resource.RUSAGE_CHILDREN)
    scale = 1024**2 if sys.platform == "darwin" else 1024
    assert offset == size and resumed
    return {"bytes": size, "allocated_source_bytes": source.stat().st_blocks * 512,
            "duration_seconds": saved["source"]["duration"], "confirmed_restart_offset": resumed,
            "transfer_seconds": round(uploaded - started, 3), "complete_seconds": round(finished - uploaded, 3),
            "mib_per_second": round(size / 1024**2 / (uploaded - started), 2),
            "server_cpu_seconds": round(resources.ru_utime + resources.ru_stime, 3),
            "server_peak_mib": round(resources.ru_maxrss / scale, 1), "sha256": digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--scratch", type=Path)
    args = parser.parse_args()
    subtitle = json.loads(args.transcript.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(dir=args.scratch, prefix="clipops-transfer-") as location:
        print(json.dumps(benchmark(Path(location), args.source, subtitle), indent=2))


if __name__ == "__main__":
    main()
