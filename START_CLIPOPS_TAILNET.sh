#!/usr/bin/env bash
# Optional owner-gated private Tailnet Studio. Does not enable Tailscale Serve or Funnel.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
umask 077
if [ "$#" -ne 2 ]; then
  echo "Usage: bash START_CLIPOPS_TAILNET.sh laptop.tailnet.ts.net owner@example.com" >&2
  exit 2
fi
HOST="$1"
LOGIN="$2"
for tool in python3 ffmpeg ffprobe fc-match; do
  command -v "$tool" >/dev/null || { echo "Missing $tool (see docs/TRY_CLIPOPS.md)" >&2; exit 2; }
done
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
if ! .venv/bin/python -c "import PIL" >/dev/null 2>&1; then
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements-pilot.txt
fi
ROOT="${CLIPOPS_PRIVATE_ROOT:-$HOME/ClipOps-private}"
mkdir -p "$ROOT"
chmod 700 "$ROOT" || true
export CLIPOPS_ALLOW_PUBLISH=0
unset POSTIZ_API_KEY GEMINI_API_KEY GOOGLE_API_KEY || true
echo "Local backend stays on 127.0.0.1:8765."
echo "In another terminal on the same reachable host, use only: tailscale serve 8765"
echo "Never use Tailscale Funnel or an unrestricted public tunnel."
exec .venv/bin/python studio.py --root "$ROOT" --port 8765 --tailnet-host "$HOST" --tailnet-user "$LOGIN"
