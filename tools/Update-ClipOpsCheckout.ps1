# ClipOps Studio source-checkout synchronizer (Windows PowerShell 5.1+).
# Default = inspect only. -Apply updates ONLY a clean main checkout after green push CI.
# Never reset/stash/clean a working tree. A source ZIP or separate installed app
# is NOT updated by this script. See docs/DESKTOP_GITHUB_SYNC.md.
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot '..'),
    [switch]$Apply,
    [string]$ExpectedSha = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$RepoName = 'MohammedAbdelshafy/clipops-studio'
$Root = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git for Windows is required; this updater does not install software.'
}

function Invoke-CheckedGit {
    param([string[]]$Arguments)
    $output = @(& git -C $Root @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($Arguments[0]) (exit $LASTEXITCODE). Inspect this checkout manually; no reset was attempted."
    }
    return ($output -join [Environment]::NewLine).Trim()
}

$top = Invoke-CheckedGit -Arguments @('rev-parse', '--show-toplevel')
if (-not [string]::Equals(
    [System.IO.Path]::GetFullPath($top).TrimEnd('\', '/'),
    [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/'),
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw 'ProjectRoot must be the root of the ClipOps checkout, not a subfolder.'
}

$origin = Invoke-CheckedGit -Arguments @('remote', 'get-url', 'origin')
$allowedOrigins = @(
    "https://github.com/$RepoName",
    "https://github.com/$RepoName.git",
    "git@github.com:$RepoName.git",
    "ssh://git@github.com/$RepoName.git"
)
if ($allowedOrigins -notcontains $origin) {
    throw "Unexpected Git remote. Refusing to update from '$origin'."
}
$branch = Invoke-CheckedGit -Arguments @('symbolic-ref', '--quiet', '--short', 'HEAD')
if ($branch -ne 'main') {
    throw "Checkout is on '$branch', not main. Preserve this worktree and use a separate main checkout."
}
$dirty = Invoke-CheckedGit -Arguments @('status', '--porcelain=v1', '--untracked-files=all')
if ($dirty) {
    throw 'Uncommitted/untracked files detected. No reset/stash/clean: preserve the work and reconcile it in a separate branch before updating.'
}

$local = Invoke-CheckedGit -Arguments @('rev-parse', 'HEAD')
# Fetch updates only remote-tracking metadata, not source files or user projects.
Invoke-CheckedGit -Arguments @('fetch', '--no-tags', 'origin', 'refs/heads/main:refs/remotes/origin/main') | Out-Null
$remote = Invoke-CheckedGit -Arguments @('rev-parse', 'refs/remotes/origin/main')
if ($local -eq $remote) {
    Write-Output "ClipOps main checkout already matches GitHub: $local"
    return
}
if ($ExpectedSha) {
    if ($ExpectedSha -notmatch '^[0-9a-fA-F]{40}$' -or $remote -ne $ExpectedSha.ToLowerInvariant()) {
        throw "GitHub main SHA ($remote) does not match the explicitly expected commit."
    }
}
& git -C $Root merge-base --is-ancestor $local $remote | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Local history diverged from GitHub main. Refusing force-update or history rewrite.'
}

# Fail closed if CI cannot be verified; a PR check is NOT sufficient.
$api = "https://api.github.com/repos/$RepoName/actions/runs?branch=main&event=push&head_sha=$remote&per_page=100"
try {
    $response = Invoke-RestMethod -Method Get -Uri $api -TimeoutSec 20 -Headers @{
        Accept = 'application/vnd.github+json'
        'User-Agent' = 'ClipOps-Safe-Desktop-Updater'
    }
} catch {
    throw "Cannot verify GitHub push CI for $remote; no update. $($_.Exception.Message)"
}
$run = $response.workflow_runs |
    Where-Object { $_.name -eq 'ClipOps offline release gate' -and $_.head_sha -eq $remote } |
    Sort-Object -Property run_number -Descending |
    Select-Object -First 1
if ($null -eq $run -or $run.status -ne 'completed' -or $run.conclusion -ne 'success') {
    throw "Required ClipOps offline release gate has not passed on pushed main SHA $remote. No update."
}

Write-Output "Current checkout: $local"
Write-Output "Approved GitHub main: $remote"
Write-Output "Passing CI: $($run.html_url)"
if (-not $Apply) {
    Write-Output 'DRY RUN ONLY. Re-run with -Apply to install this verified fast-forward update.'
    return
}

# Never replace running application files; the operator can restart after updating.
if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    $listeners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        throw 'ClipOps appears to be listening on local port 8765. Stop the desktop server before applying an update.'
    }
}
$checkpoint = "backup/clipops-before-update-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Invoke-CheckedGit -Arguments @('branch', $checkpoint, $local) | Out-Null
Invoke-CheckedGit -Arguments @('merge', '--ff-only', 'refs/remotes/origin/main') | Out-Null
$installed = Invoke-CheckedGit -Arguments @('rev-parse', 'HEAD')
if ($installed -ne $remote) {
    throw "Unexpected installed commit $installed (expected $remote). Inspect before launching."
}
Write-Output "UPDATED ClipOps source checkout to $installed"
Write-Output "Previous commit preserved under local branch $checkpoint"
Write-Output 'Restart Studio and run its regression checks. This script does NOT update a separate ZIP/EXE installation, install dependencies, or alter private project data.'
