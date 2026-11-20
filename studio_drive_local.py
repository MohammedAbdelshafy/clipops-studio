#!/usr/bin/env python3
"""Opt-in Google Drive folder import into ClipOps Studio's existing UploadStore.

Single-user workstation pilot. The OAuth web/desktop client configuration and token are
stored outside the repository in the private Studio project root. No publishing.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace

from studio_drive_reader import GoogleDriveV3Reader, DriveImportError
from studio_drive_bridge import StudioDriveBridge
from clipops_compat import is_private_path, restrict_private_file

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
TOKEN_FILE = ".google-drive-oauth.json"


def secure_root(root: str | Path) -> Path:
    requested = Path(root).expanduser().absolute()
    # Resolving first hides a symlink at the root itself. Reject the caller's
    # symlink before resolving; the OAuth token must stay at the chosen path.
    if requested.is_symlink():
        raise ValueError("Studio root must not be a symbolic link")
    p = requested.resolve()
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not p.is_dir():
        raise ValueError("Studio root must be a private local directory")
    return p


def token_path(root: str | Path) -> Path:
    return secure_root(root) / TOKEN_FILE


def save_token(root: str | Path, payload: dict) -> None:
    """Keep OAuth credentials off source control and out of stdout/logs."""
    if not isinstance(payload, dict) or not payload.get("token"):
        raise ValueError("Google OAuth credentials are incomplete")
    target = token_path(root)
    if target.is_symlink():
        raise ValueError("Refusing to replace a symbolic OAuth token file")
    with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, prefix=".google-auth-",
                                     suffix=".tmp", delete=False, encoding="utf-8") as fp:
        temp = Path(fp.name)
        try:
            restrict_private_file(temp)
            json.dump(payload, fp, ensure_ascii=False)
            fp.flush()
            os.fsync(fp.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    os.replace(temp, target)
    restrict_private_file(target)


def oauth_configuration(client_json: str | Path, *, web_port: int = 8766) -> tuple[Path, str, str | None]:
    """Validate a Google-downloaded Web/Installed OAuth JSON before networking.

    A Web application's redirect URI MUST be registered verbatim in Google Cloud.
    No client ID, secret or token is ever returned to the caller or printed.
    """
    source = Path(client_json).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != ".json":
        raise ValueError("Provide the downloaded Google OAuth client JSON")
    try:
        config = json.loads(source.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("The OAuth client JSON is invalid") from exc
    if not isinstance(config, dict):
        raise ValueError("The OAuth client JSON must contain a web or installed client")
    if "web" in config:
        if type(web_port) is not int or not 1024 <= web_port <= 65535:
            raise ValueError("Use a local OAuth port from 1024 to 65535")
        client = config["web"]
        if not isinstance(client, dict) or not client.get("client_id") or not client.get("client_secret"):
            raise ValueError("The Web OAuth client is missing required fields")
        redirect = f"http://localhost:{web_port}/"
        allowed = client.get("redirect_uris") or []
        if redirect not in allowed:
            raise ValueError("Google Cloud OAuth Web client must authorize exactly " + redirect)
        return source, "web", redirect
    if "installed" in config:
        client = config["installed"]
        if not isinstance(client, dict) or not client.get("client_id"):
            raise ValueError("The Desktop OAuth client is incomplete")
        return source, "installed", None
    raise ValueError("The Google JSON is not a Web or Desktop OAuth client")


def connect(root: str | Path, client_json: str | Path, *, web_port: int = 8766,
            open_browser: bool = True) -> None:
    """Run an explicit local-browser consent; never send secrets to client JavaScript."""
    source, client_type, _redirect = oauth_configuration(client_json, web_port=web_port)
    # Cloud Shell runs remotely. Redirecting an Android/desktop browser to
    # localhost will reach that device, not the remote Cloud Shell process.
    # This CLI implements local loopback OAuth only; never instruct users to
    # tunnel the callback publicly or disable the existing auth boundary.
    if os.environ.get("WEB_HOST"):
        raise RuntimeError("Cloud Shell cannot use this localhost OAuth callback. "
                           "Run connect on the same local workstation/browser; "
                           "a separate authenticated HTTPS callback is required for Cloud Shell.")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError("Install the optional requirements-drive-local.txt first") from exc
    # InstalledAppFlow supports both Google's `installed` and `web` client
    # configurations. For a Web client, use the fixed, pre-registered callback;
    # unlike a Desktop client, an arbitrary ephemeral port is not valid.
    flow = InstalledAppFlow.from_client_secrets_file(
        str(source), scopes=[DRIVE_SCOPE], autogenerate_code_verifier=True)
    server_options = {"host": "localhost", "port": web_port, "open_browser": open_browser,
                      "authorization_prompt_message":
                      "Open this URL to authorize ClipOps Google Drive: {url}"}
    if client_type == "installed":
        server_options.update(host="127.0.0.1", port=0)
    # `run_local_server` validates OAuth state and exchanges the authorization
    # code server-side; token/secret are never exposed to ClipOps frontend JS.
    credentials = flow.run_local_server(**server_options, access_type="offline", prompt="consent")
    if not credentials.valid:
        raise RuntimeError("Google OAuth did not provide valid authorization")
    save_token(root, json.loads(credentials.to_json()))
    print("Google Drive authorization saved in private ClipOps storage.")


def credential_supplier(root: str | Path):
    """Refresh via the official Google SDK without exposing tokens to browser JS."""
    p = token_path(root)
    if p.is_symlink() or not p.is_file():
        raise RuntimeError("Google Drive is not connected; run `connect` first")
    if os.name != "nt" and p.stat().st_mode & 0o077:
        raise RuntimeError("OAuth token file is not private; restrict access before continuing")
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise RuntimeError("Install the optional requirements-drive-local.txt first") from exc
    creds = Credentials.from_authorized_user_file(str(p), scopes=[DRIVE_SCOPE])
    if not creds.valid:
        if not creds.refresh_token:
            raise RuntimeError("Google Drive authorization has expired; reconnect")
        creds.refresh(Request())
        save_token(root, json.loads(creds.to_json()))
    if not creds.token:
        raise RuntimeError("Google Drive authorization has no active access token")
    return creds.token


def make_bridge(root: str | Path):
    try:
        from studio_uploads import UploadStore
    except ImportError as exc:
        raise RuntimeError("Run inside the current ClipOps Studio repository") from exc
    root = secure_root(root)
    store = UploadStore(root)
    reader = GoogleDriveV3Reader(lambda: credential_supplier(root))
    return StudioDriveBridge(store, reader), store


def selected_video(bridge, folder_url: str, file_id: str):
    files = bridge.preview(folder_url)
    return next((entry for entry in files if entry["id"] == file_id), None)


def import_source(bridge, store, root, *, folder_url=None, file_id=None, upload_id=None,
                  transcript=None, model=None, rights=False, style="podcast", platform="shorts",
                  render_count=0, process=False, write=print):
    """Run a resumable foreground import; Ctrl-C preserves the checkpoint."""
    root = secure_root(root)
    if upload_id is None:
        if not rights:
            raise ValueError("Confirm permission using --rights-confirmed")
        if not folder_url or not file_id:
            raise ValueError("Choose the Drive folder and file ID from preview")
        choice = selected_video(bridge, folder_url, file_id)
        if not choice:
            raise DriveImportError("Video is not accessible in the selected Drive folder")
        if not transcript and not model:
            raise ValueError("Provide --transcript or --model for the ClipOps pilot")
        if transcript:
            doc = json.loads(Path(transcript).expanduser().resolve(strict=True).read_text(encoding="utf-8"))
            if not isinstance(doc, (dict, list)):
                raise ValueError("Transcript must be a JSON object or cue array")
        else:
            doc = None
        spec = {"filename": choice["name"], "name": Path(choice["name"]).stem,
                "rights": True, "mime": choice["mime_type"],
                "render_count": render_count, "transcript": doc,
                "style": style, "platform": platform}
        upload_id = bridge.start(folder_url, file_id, spec, rights_confirmed=True)["upload_id"]
        write(f"Upload checkpoint: {upload_id}")
    else:
        state = store.inspect(upload_id)
        spec = state["metadata"]
    while True:
        status = bridge.copy_pass(upload_id, max_chunks=4)
        total, done = status["total_bytes"], status["received_bytes"]
        write(f"Drive import: {done}/{total} verified bytes")
        if done >= total:
            break
    bridge.verify_complete(upload_id)
    write("Google source integrity verified. Creating the local ClipOps project…")
    try:
        import pilot
    except ImportError as exc:
        raise RuntimeError("ClipOps pilot.py was not found in the current working directory") from exc

    def create_project(media, work, config):
        saved_transcript = None
        if config.get("transcript") is not None:
            from pilot import save_json
            saved_transcript = work / "timed-transcript.json"
            save_json(saved_transcript, config["transcript"])
        target_model = Path(model).expanduser().resolve(strict=True) if model else None
        if config.get("transcript") is None and target_model is None:
            raise ValueError("This import requires --model to finish project creation")
        pilot.create_project(media, root, transcript=saved_transcript, model=target_model,
                             rights=True, name=config.get("name", "Drive import"),
                             render_count=config.get("render_count", 0),
                             style=config.get("style", "podcast"),
                             platform=config.get("platform", "shorts"),
                             job_id=upload_id, staged_upload=True)

    project_id, count = store.finish(upload_id, root, create_project)
    write(f"ClipOps project: {project_id} (initial render count: {count})")
    if process:
        pilot.process_project(root, project_id, render_count=count,
                              model=Path(model).expanduser().resolve(strict=True) if model else None)
        write("Local processing completed; open the review desk for editorial approval.")
    return project_id


def main():
    parser = argparse.ArgumentParser(description="Local-first ClipOps Google Drive folder link import")
    parser.add_argument("--root", required=True, help="Private root used by `launch-studio --root`")
    sub = parser.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("connect", help="Ask for Google Drive authorization through your browser")
    auth.add_argument("--client-secrets", required=True, help="Private Google OAuth JSON (web or installed)")
    auth.add_argument("--oauth-port", type=int, default=8766, help="Fixed Google Web OAuth callback port; default 8766")
    auth.add_argument("--no-browser", action="store_true", help="Print the consent URL instead of opening a browser (WSL2)")
    check = sub.add_parser("check-oauth", help="Validate your local OAuth JSON and redirect URI without signing in")
    check.add_argument("--client-secrets", required=True, help="Local OAuth JSON; values are never printed")
    check.add_argument("--oauth-port", type=int, default=8766, help="Expected registered callback port")
    prev = sub.add_parser("preview", help="List downloadable videos from an authorized folder")
    prev.add_argument("folder_url")
    start = sub.add_parser("start", help="Import one explicitly selected video and create a ClipOps project")
    start.add_argument("folder_url")
    start.add_argument("file_id")
    start.add_argument("--rights-confirmed", action="store_true")
    start.add_argument("--transcript")
    start.add_argument("--model")
    start.add_argument("--style", default="podcast")
    start.add_argument("--platform", default="shorts")
    start.add_argument("--render-count", type=int, default=0)
    start.add_argument("--process", action="store_true", help="Run local analysis after import")
    resume = sub.add_parser("resume", help="Continue an existing checkpoint without uploading again")
    resume.add_argument("upload_id")
    resume.add_argument("--model")
    resume.add_argument("--process", action="store_true")
    args = parser.parse_args()
    if args.command == "connect":
        connect(args.root, args.client_secrets, web_port=args.oauth_port,
                open_browser=not args.no_browser)
        return
    if args.command == "check-oauth":
        _, client_type, redirect_uri = oauth_configuration(
            args.client_secrets, web_port=args.oauth_port)
        print("OAuth configuration valid:", client_type)
        if redirect_uri:
            print("Registered callback:", redirect_uri)
        print("Credentials and media were not accessed.")
        return
    bridge, store = make_bridge(args.root)
    if args.command == "preview":
        print(json.dumps(bridge.preview(args.folder_url), ensure_ascii=False, indent=2))
    elif args.command == "start":
        import_source(bridge, store, args.root, folder_url=args.folder_url, file_id=args.file_id,
                      rights=args.rights_confirmed, transcript=args.transcript, model=args.model,
                      style=args.style, platform=args.platform, render_count=args.render_count,
                      process=args.process)
    else:
        import_source(bridge, store, args.root, upload_id=args.upload_id,
                      model=args.model, process=args.process)


if __name__ == "__main__":
    main()
