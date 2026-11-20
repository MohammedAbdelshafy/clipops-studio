# Windows launcher through WSL2 Ubuntu. Never exposes a public server or uses paid APIs.
$ErrorActionPreference = 'Stop'
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw 'WSL2 is required for the verified Linux pilot. Install Ubuntu using wsl --install -d Ubuntu.'
}
$project = (Resolve-Path $PSScriptRoot).Path
$linuxPath = (& wsl.exe wslpath -a $project | Out-String).Trim()
if (-not $linuxPath -or $LASTEXITCODE -ne 0) {
    throw 'Could not resolve the extracted project folder inside WSL2.'
}
$escaped = $linuxPath.Replace("'", "'\''")
Write-Host 'Starting ClipOps locally. Open http://127.0.0.1:8765 in your Windows browser.'
& wsl.exe --exec bash -lc "cd '$escaped' && bash ./START_CLIPOPS.sh"
if ($LASTEXITCODE -ne 0) {
    throw "ClipOps exited with code $LASTEXITCODE. Check Python, FFmpeg and Ubuntu packages."
}
