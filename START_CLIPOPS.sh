#!/usr/bin/env bash
# Start the offline ClipOps Studio pilot. No cloud credentials are loaded.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
umask 077
export CLIPOPS_ALLOW_PUBLISH=0
unset POSTIZ_API_KEY GEMINI_API_KEY GOOGLE_API_KEY || true
for tool in python3 ffmpeg ffprobe fc-match; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing $tool. On Ubuntu/WSL2 run: sudo apt-get install python3 python3-venv python3-pip ffmpeg fontconfig fonts-dejavu-core fonts-liberation" >&2
    exit 2
  fi
done
python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit('ClipOps Studio requires Python 3.11 or newer')
PY
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import PIL' >/dev/null 2>&1; then
  echo 'Installing the free, pinned caption-layout dependency...'
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements-pilot.txt
fi
ROOT="${CLIPOPS_PRIVATE_ROOT:-$HOME/ClipOps-private}"
mkdir -p "$ROOT"
chmod 700 "$ROOT" || true
echo 'ClipOps Studio: http://127.0.0.1:8765'
echo 'Keep this terminal running; press Ctrl+C to stop.'
exec .venv/bin/python studio.py --root "$ROOT" --port 8765
