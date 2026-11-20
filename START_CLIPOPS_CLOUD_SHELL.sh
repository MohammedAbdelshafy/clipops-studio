#!/usr/bin/env bash
# Account-restricted Android browser access using Google Cloud Shell Web Preview.
# Cloud Shell provides the authentication proxy. Do not publish this app on Cloud Run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
umask 077
export CLIPOPS_ALLOW_PUBLISH=0
unset POSTIZ_API_KEY GEMINI_API_KEY GOOGLE_API_KEY || true
if [[ -z "${WEB_HOST:-}" || "${WEB_HOST}" != *.cloudshell.dev ]]; then
  echo 'Start this script inside Google Cloud Shell, not a public VM.' >&2
  exit 2
fi
if ! python3 -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
  echo 'Cloud Shell must provide Python 3.11 or newer.' >&2
  exit 2
fi
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null || ! command -v fc-match >/dev/null; then
  echo 'Installing local-only FFmpeg and caption fonts in Cloud Shell...'
  sudo apt-get update -qq
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg fontconfig fonts-dejavu-core fonts-liberation
fi
if [[ ! -x .venv/bin/python ]]; then python3 -m venv .venv; fi
if ! .venv/bin/python -c 'import PIL' >/dev/null 2>&1; then
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements-pilot.txt
fi
ROOT="${CLIPOPS_PRIVATE_ROOT:-$HOME/ClipOps-private}"
mkdir -p "$ROOT" && chmod 700 "$ROOT"
echo
printf 'Open this private HTTPS link on your Android phone:\nhttps://8080-%s\n' "$WEB_HOST"
echo 'Or tap Cloud Shell Web Preview > Preview on port 8080.'
echo 'Leave this terminal session running. Ctrl+C stops ClipOps.'
echo 'Small demo videos only: Cloud Shell storage is not suitable for 15–20 GB inputs.'
exec .venv/bin/python studio.py --root "$ROOT" --port 8080 --cloud-shell
