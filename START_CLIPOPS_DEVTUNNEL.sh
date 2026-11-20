#!/usr/bin/env bash
# Private Microsoft Dev Tunnel test backend; CLI hosting is done by the owner separately.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
umask 077
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: bash START_CLIPOPS_DEVTUNNEL.sh https://TUNNELID-PORT.REGION.devtunnels.ms [PORT=8765]" >&2
  exit 2
fi
PORT="${2:-8765}"
if [[ ! "$PORT" =~ ^[0-9]{4,5}$ ]] || (( PORT < 2000 || PORT > 65000 )); then
  echo "Choose a valid private Dev Tunnel port in 2000..65000." >&2
  exit 2
fi
for executable in python3 ffmpeg ffprobe fc-match; do
  command -v "$executable" >/dev/null || {
    echo "Missing $executable. See docs/TRY_CLIPOPS.md for free dependencies." >&2
    exit 2
  }
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
echo "Private test only: Microsoft account authentication required; never use --allow-anonymous."
echo "Remote video traffic is limited by Microsoft's 5 GB/user/month Dev Tunnels quota."
exec .venv/bin/python studio.py --root "$ROOT" --port "$PORT" --devtunnel-url "$1"
