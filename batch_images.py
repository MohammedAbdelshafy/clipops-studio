#!/usr/bin/env python3
"""ClipOps Studio / FanForge — Gemini Batch API overnight image client.

Submits image-generation jobs to the Gemini Batch API (50% Batch pricing)
and collects per-key results. stdlib only (urllib, json).

BLOCKED_ON_KEY: live calls need the Gemini credential — the stored
`custom.gemini` connector (preferred) or GEMINI_API_KEY / GOOGLE_API_KEY
env fallback. With neither, the client runs in dry-run mode: it builds
the exact JSONL payload and the cost estimate but performs zero network
I/O. Key values are never printed or logged.

Verified 2026-10-05 — do not invent beyond these:
  * model: gemini-3-pro-image
  * Batch pricing: $0.067 per 1K/2K image ($60 / 1M image tokens),
    text input $1.00 / 1M, thinking+text output $6.00 / 1M.
    (4K Batch image pricing NOT verified — estimate_cost refuses it.)
  * Worked example: Batch 2K with default tokens = $0.0732 / image.
  * 24h turnaround target; job EXPIRES at 48h with no results;
    results kept 6 weeks.
  * JSONL line shape per request:
      {"key": "sku-00001",
       "request": {"contents": [{"parts": [{"text": "<prompt>"}]}],
                   "generation_config": {"responseModalities": ["TEXT","IMAGE"],
                     "imageConfig": {"imageSize": "2K", "aspectRatio": "4:5"}}}}
    imageSize is one of 1K / 2K / 4K.

REST transport — batch endpoints verified against the official Batch API
guide (https://ai.google.dev/api/batch-mode, fetched 2026-10-05):
  * create: POST /v1beta/models/{model}:batchGenerateContent
            body {displayName, inputConfig: {fileName: "files/..."}}
            -> long-running Operation
  * poll:   GET  /v1beta/batches/{batchId} -> Operation
                 {name, done, metadata, response|error}
  * cancel: POST /v1beta/batches/{batchId}:cancel
  * auth:   x-goog-api-key header (documented Gemini REST API-key auth)
The Files API upload/download adapter below (multipart upload endpoint,
:download) follows the documented Files API flow but has NOT been
live-exercised from this codebase — FilesTransport.NEEDS_LIVE_VERIFICATION
is True. One live dry-run against the real API before first paid use.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

MODEL = "gemini-3-pro-image"
BASE_URL = "https://generativelanguage.googleapis.com"
BATCH_API = "/v1beta"

# --- Verified Batch rate card (2026-10-05) ---------------------------------
IMAGE_USD = {"1K": 0.067, "2K": 0.067}  # 4K pricing NOT verified
TEXT_IN_PER_1M = 1.00
THINKING_OUT_PER_1M = 6.00

VALID_SIZES = ("1K", "2K", "4K")
DEFAULT_PROMPT_TOKENS = 200
DEFAULT_THINKING_TOKENS = 1000


class BatchError(RuntimeError):
    """Base error for batch lifecycle failures."""


class BatchExpired(BatchError):
    """The batch job expired (48h with no results)."""


class BatchFailed(BatchError):
    """The batch job failed or was cancelled."""


# ---------------------------------------------------------------------------
# Cost estimation (offline, no key needed)
# ---------------------------------------------------------------------------

def estimate_cost(num_images: int,
                  size: str = "2K",
                  prompt_tokens: int = DEFAULT_PROMPT_TOKENS,
                  thinking_tokens: int = DEFAULT_THINKING_TOKENS) -> dict:
    """USD estimate for a Batch image run at the verified rate card.

    Raises ValueError for 4K: its Batch image price was not verified, so no
    number is invented for it.
    """
    if size not in IMAGE_USD:
        raise ValueError(
            f"Batch image pricing for size {size!r} is not verified "
            f"(verified: {sorted(IMAGE_USD)}). Refusing to estimate."
        )
    per_image = (
        IMAGE_USD[size]
        + prompt_tokens * TEXT_IN_PER_1M / 1_000_000
        + thinking_tokens * THINKING_OUT_PER_1M / 1_000_000
    )
    return {
        "model": MODEL,
        "size": size,
        "num_images": num_images,
        "per_image_usd": round(per_image, 4),
        "total_usd": round(per_image * num_images, 4),
        "rate_card": {
            "image_usd": IMAGE_USD[size],
            "text_input_per_1m": TEXT_IN_PER_1M,
            "thinking_output_per_1m": THINKING_OUT_PER_1M,
        },
    }


# ---------------------------------------------------------------------------
# JSONL payload (offline, no key needed)
# ---------------------------------------------------------------------------

def build_line(key: str, prompt: str, size: str = "2K",
               aspect_ratio: str = "4:5") -> dict:
    """One JSONL request line in the verified schema."""
    if size not in VALID_SIZES:
        raise ValueError(f"imageSize must be one of {VALID_SIZES}, got {size!r}")
    return {
        "key": key,
        "request": {
            "contents": [{"parts": [{"text": prompt}]}],
            "generation_config": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"imageSize": size, "aspectRatio": aspect_ratio},
            },
        },
    }


def build_jsonl(prompts: list,
                size: str = "2K",
                aspect_ratio: str = "4:5",
                out_path: str | None = None) -> str:
    """Write prompts to a Batch JSONL file. Returns the file path.

    prompts: list of strings, or list of {"prompt": ..., "key": ...} dicts.
    Keys default to sku-00001, sku-00002, ...
    """
    if out_path is None:
        fd, out_path = tempfile.mkstemp(prefix="clipops-batch-", suffix=".jsonl")
        os.close(fd)
    with open(out_path, "w", encoding="utf-8") as fh:
        for i, p in enumerate(prompts, 1):
            if isinstance(p, dict):
                key, prompt = p.get("key") or f"sku-{i:05d}", p["prompt"]
            else:
                key, prompt = f"sku-{i:05d}", p
            fh.write(json.dumps(build_line(key, prompt, size, aspect_ratio),
                                ensure_ascii=False) + "\n")
    return out_path


def parse_results_jsonl(text: str) -> dict:
    """Parse a batch output JSONL into {key: {ok, response|error|raw}}.

    Failed lines (bad JSON, missing key) are recorded under
    "_failed_lines" instead of raising, so one corrupt line never kills
    the whole overnight run's accounting.
    """
    results: dict = {}
    failed = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            failed.append({"lineno": lineno, "reason": "bad JSON"})
            continue
        key = obj.get("key")
        if not key:
            failed.append({"lineno": lineno, "reason": "missing key"})
            continue
        if "error" in obj and obj["error"]:
            results[key] = {"ok": False, "error": obj["error"]}
        else:
            results[key] = {"ok": True, "response": obj.get("response")}
    if failed:
        results["_failed_lines"] = failed
    return results


# ---------------------------------------------------------------------------
# HTTP plumbing (stdlib)
# ---------------------------------------------------------------------------

def _api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")


# ---------------------------------------------------------------------------
# Connector auth (preferred): the stored `custom.gemini` credential, attached
# as an authd surrogate — the real key never touches this process.
# ---------------------------------------------------------------------------

_CONNECTOR_CREDENTIAL = "custom.gemini"
_CONNECTOR_HOSTS = ("generativelanguage.googleapis.com",)
_DC_BIN = "/opt/hatch/skills/skill-creator/bin"
_connector_probe_cache: bool | None = None


def _connector_available() -> bool:
    """True when the stored Gemini connector yields a surrogate (cached)."""
    global _connector_probe_cache
    if _connector_probe_cache is not None:
        return _connector_probe_cache
    try:
        if _DC_BIN not in sys.path:
            sys.path.insert(0, _DC_BIN)
        import dynamic_credentials as dc
        req = urllib.request.Request(BASE_URL, method="GET")
        dc.add_surrogate_to_request(
            req, _CONNECTOR_CREDENTIAL, allowed_hosts=_CONNECTOR_HOSTS)
        _connector_probe_cache = any(
            k.lower() == "x-goog-api-key" for k, _ in req.header_items())
    except Exception:
        _connector_probe_cache = False
    return _connector_probe_cache


def _auth_headers(url: str, api_key: str) -> dict:
    """Auth headers: explicit env key first, connector surrogate second."""
    if api_key:
        return {"x-goog-api-key": api_key}
    if _connector_available():
        if _DC_BIN not in sys.path:
            sys.path.insert(0, _DC_BIN)
        import dynamic_credentials as dc
        req = urllib.request.Request(url, method="GET")
        dc.add_surrogate_to_request(
            req, _CONNECTOR_CREDENTIAL, allowed_hosts=_CONNECTOR_HOSTS)
        return {k: v for k, v in req.header_items()
                if k.lower() == "x-goog-api-key"}
    return {}


def _http(method: str, url: str, api_key: str,
          body: dict | None = None, timeout_s: int = 60) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    headers.update(_auth_headers(url, api_key))
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise BatchError(f"Gemini API HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise BatchError(f"Gemini API request failed: {e}") from e
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        raise BatchError("Gemini API returned non-JSON") from e


# ---------------------------------------------------------------------------
# Files API adapter — NOT live-verified from this codebase
# ---------------------------------------------------------------------------

class FilesTransport:
    """Upload JSONL / download result files via the Gemini Files API.

    NEEDS_LIVE_VERIFICATION = True: endpoints follow the documented Files
    API flow, but no live call has been exercised from this codebase yet.
    Run one live dry-run before first paid use; fix URLs here if rejected.
    """
    NEEDS_LIVE_VERIFICATION = True
    UPLOAD_URL = BASE_URL + "/upload/v1beta/files"

    def __init__(self, api_key: str):
        self._key = api_key

    def _headers(self, url: str, extra: dict | None = None) -> dict:
        headers = _auth_headers(url, self._key)
        if extra:
            headers.update(extra)
        return headers

    def upload_jsonl(self, path: str, display_name: str) -> str:
        """Upload a JSONL file. Returns the file resource name (files/...)."""
        boundary = "----clipops" + uuid.uuid4().hex
        with open(path, "rb") as fh:
            payload = fh.read()
        meta = json.dumps({"file": {"display_name": display_name}}).encode()
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=utf-8\r\n\r\n"
            .encode() + meta + f"\r\n--{boundary}\r\n".encode()
            + b"Content-Type: application/jsonl\r\n\r\n" + payload
            + f"\r\n--{boundary}--\r\n".encode()
        )
        req = urllib.request.Request(
            self.UPLOAD_URL, data=body, method="POST",
            headers=self._headers(
                self.UPLOAD_URL,
                {"Content-Type": f"multipart/related; boundary={boundary}"}),
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise BatchError(
                f"Files upload HTTP {e.code} — verify endpoint "
                f"{self.UPLOAD_URL} (NEEDS_LIVE_VERIFICATION)") from e
        name = (data.get("file") or {}).get("name", "")
        if not name:
            raise BatchError(f"Files upload returned no file name: {data}")
        return name

    def download(self, file_name: str) -> str:
        """Download a file's bytes as text (result JSONL)."""
        url = (f"{BASE_URL}{BATCH_API}/{file_name}:download"
               f"?{urllib.parse.urlencode({'alt': 'media'})}")
        req = urllib.request.Request(
            url, method="GET", headers=self._headers(url))
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise BatchError(f"Files download HTTP {e.code} for {file_name}") from e


# ---------------------------------------------------------------------------
# Batch job client
# ---------------------------------------------------------------------------

class GeminiBatchClient:
    """Overnight image-batch lifecycle: create -> poll -> download -> parse.

    Dry-run (no credential): every method that would touch the network
    instead returns the exact plan it would have executed. A credential is
    the stored `custom.gemini` connector (preferred) or GEMINI_API_KEY /
    GOOGLE_API_KEY env fallback.
    """

    def __init__(self, api_key: str | None = None, model: str = MODEL):
        self._key = api_key or _api_key()
        self._live = bool(self._key) or _connector_available()
        self.model = model
        self.dry_run = not self._live
        self.files = FilesTransport(self._key) if self._live else None

    # -- create -----------------------------------------------------------
    def create_batch(self, jsonl_path: str, display_name: str) -> dict:
        """Upload JSONL and enqueue the batch. Returns the Operation."""
        with open(jsonl_path, encoding="utf-8") as fh:
            num_requests = sum(1 for line in fh if line.strip())
        cost = estimate_cost(num_requests)
        if self.dry_run:
            return {
                "dry_run": True,
                "blocked_on": "gemini_credential",
                "would_upload": jsonl_path,
                "num_requests": num_requests,
                "display_name": display_name,
                "estimated_cost_usd": cost["total_usd"],
                "note": "No key set — zero network I/O. "
                        "Connect the custom.gemini credential or set GEMINI_API_KEY to run live.",
            }
        file_name = self.files.upload_jsonl(jsonl_path, display_name)
        url = (f"{BASE_URL}{BATCH_API}/models/{self.model}:batchGenerateContent")
        op = _http("POST", url, self._key,
                   {"displayName": display_name,
                    "inputConfig": {"fileName": file_name}})
        op["estimated_cost_usd"] = cost["total_usd"]
        return op

    # -- poll --------------------------------------------------------------
    def get_batch(self, batch_name: str) -> dict:
        """GET the latest Operation state for batches/{batchId}."""
        if self.dry_run:
            return {"dry_run": True, "blocked_on": "gemini_credential",
                    "batch": batch_name}
        url = f"{BASE_URL}{BATCH_API}/{batch_name}"
        return _http("GET", url, self._key)

    @staticmethod
    def _terminal_state(op: dict) -> str | None:
        """Return 'expired' / 'failed' / 'succeeded' / None (still running)."""
        if not op.get("done"):
            return None
        err = op.get("error") or {}
        resp = op.get("response") or {}
        state = str(resp.get("state", "")).upper()
        err_text = json.dumps(err).upper()
        if "EXPIRED" in state or "EXPIRED" in err_text or "DEADLINE" in err_text:
            return "expired"
        if err or "FAILED" in state or "CANCELLED" in state:
            return "failed"
        return "succeeded"

    def wait(self, batch_name: str, timeout_s: int = 25 * 3600,
             poll_s: int = 300) -> dict:
        """Poll until the batch completes. Raises BatchExpired / BatchFailed."""
        if self.dry_run:
            return {"dry_run": True, "blocked_on": "gemini_credential",
                    "batch": batch_name}
        deadline = time.time() + timeout_s
        op = None
        while time.time() < deadline:
            op = self.get_batch(batch_name)
            terminal = self._terminal_state(op)
            if terminal == "expired":
                raise BatchExpired(
                    f"Batch {batch_name} expired (48h with no results).")
            if terminal == "failed":
                raise BatchFailed(
                    f"Batch {batch_name} failed: {op.get('error')}")
            if terminal == "succeeded":
                return op
            time.sleep(poll_s)
        raise BatchError(f"Timed out waiting {timeout_s}s for {batch_name}")

    def cancel(self, batch_name: str) -> dict:
        if self.dry_run:
            return {"dry_run": True, "blocked_on": "gemini_credential"}
        url = f"{BASE_URL}{BATCH_API}/{batch_name}:cancel"
        return _http("POST", url, self._key, {})

    # -- download + parse ---------------------------------------------------
    def download_results(self, operation: dict) -> dict:
        """Fetch the output JSONL and parse per-key results.

        Handles both output shapes: responsesFile (file-based input) and
        inlinedResponses (inlined input). Failed lines never raise.
        """
        if self.dry_run:
            return {"dry_run": True, "blocked_on": "gemini_credential"}
        resp = operation.get("response") or {}
        output = resp.get("output") or {}
        if output.get("responsesFile"):
            text = self.files.download(output["responsesFile"])
            return parse_results_jsonl(text)
        inlined = (output.get("inlinedResponses") or {}).get("inlinedResponses", [])
        results = {}
        for i, item in enumerate(inlined):
            key = (item.get("metadata") or {}).get("key", f"index-{i}")
            if item.get("error"):
                results[key] = {"ok": False, "error": item["error"]}
            else:
                results[key] = {"ok": True, "response": item.get("response")}
        return results

    # -- one-shot ------------------------------------------------------------
    def run_overnight(self, prompts: list, display_name: str,
                      size: str = "2K", aspect_ratio: str = "4:5") -> dict:
        """Build JSONL + cost plan; enqueue when a key is present."""
        jsonl_path = build_jsonl(prompts, size=size, aspect_ratio=aspect_ratio)
        cost = estimate_cost(len(prompts), size=size)
        plan = {
            "jsonl_path": jsonl_path,
            "num_requests": len(prompts),
            "size": size,
            "aspect_ratio": aspect_ratio,
            "estimated_cost_usd": cost["total_usd"],
            "per_image_usd": cost["per_image_usd"],
            "limits": {"target_turnaround_h": 24, "expires_h": 48,
                       "results_kept_weeks": 6},
        }
        if self.dry_run:
            plan.update({"dry_run": True, "blocked_on": "gemini_credential",
                         "note": "No key set — JSONL built, zero network I/O. "
                                 "Connect the custom.gemini credential or set GEMINI_API_KEY to enqueue."})
            return plan
        op = self.create_batch(jsonl_path, display_name)
        plan.update({"dry_run": False, "operation": op.get("name")})
        return plan


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Gemini Batch overnight images — build JSONL + cost plan, "
                    "enqueue when GEMINI_API_KEY is set.")
    ap.add_argument("--prompt", action="append", default=[],
                    help="image prompt (repeatable)")
    ap.add_argument("--file", help="text file with one prompt per line")
    ap.add_argument("--size", default="2K", choices=VALID_SIZES)
    ap.add_argument("--aspect", default="4:5")
    ap.add_argument("--name", default="clipops-overnight")
    args = ap.parse_args()
    prompts = list(args.prompt)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            prompts += [l.rstrip("\n") for l in fh if l.strip()]
    if not prompts:
        ap.error("give at least one --prompt or --file")
    client = GeminiBatchClient()
    print(json.dumps(client.run_overnight(prompts, args.name, size=args.size,
                                         aspect_ratio=args.aspect), indent=2))
