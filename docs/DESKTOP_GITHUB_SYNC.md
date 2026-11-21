# ClipOps Studio: GitHub-to-Windows source synchronization

**Status (2026-11-21): draft, review only; not installed or executed on the owner's Windows laptop.**
This protocol protects local edits. It is **not** a force reset, an EXE updater, or a remote desktop connection.

## Why GitHub updates are not automatically visible in Studio

The active Studio is a Python/FFmpeg app launched from a **local directory** (Windows via WSL2 and `START_CLIPOPS_WINDOWS.ps1`). Pushing a commit changes a GitHub branch, not a running Windows process or an extracted ZIP. PR review branches are not part of `main` until intentionally reconciled and merged.

Cloud Antigravity Remote Agents clone their own GitHub workspace; they cannot modify an offline Windows disk. Antigravity Remote Control can operate the host's folders only when enabled on that host and the machine stays powered on and connected. The first Windows update setup therefore requires access to the laptop at least once.

## Version policy and safe rollout

1. Develop on isolated `review/*` branches, preserving existing worktrees and all uncommitted local files. Never push secrets, transcripts, client footage or private project data to the public repository.
2. Merge only reviewed work with passing repository unit tests, browser E2E and packaging gates. Confirm GitHub **push** CI is green on the exact `main` commit; green PR checks alone do not establish the result.
3. On an independently clean Windows **Git checkout** of this exact repository, run the updater in check-only mode. It confirms canonical `origin`, branch `main`, a clean tracked/untracked tree, fast-forward ancestry and the successful `ClipOps offline release gate` GitHub Actions run on the exact pushed commit.
4. When ready to install, stop Studio, run the script with `-Apply`, then restart the existing local launcher. The updater creates a local backup branch pointing at the prior commit and uses `git merge --ff-only`. It never runs `reset --hard`, `clean`, `stash`, force-push or automatic deployment.
5. Check installed `git rev-parse HEAD`, run `python -m unittest discover -v`, `node --check studio/app.js`, the real desktop browser smoke, and a rights-cleared test video. Dependency changes require separately approved installation. The updater **does not** update Python environments or force restart processes.
6. Preserve `CLIPOPS_PROJECT_DIR` outside Git as designed. Do not touch source footage, user projects, local Drive authorizations or approval records. Review migrations before a new version processes existing project data.

## Windows PowerShell (once a clean source checkout exists)

From that checkout's root (not a source ZIP, not a dirty development worktree):

```powershell
# Safe check: fetches GitHub metadata only and reports the eligible commit.
powershell.exe -NoProfile -File .\tools\Update-ClipOpsCheckout.ps1

# Apply only after successful CI, with the app closed:
powershell.exe -NoProfile -File .\tools\Update-ClipOpsCheckout.ps1 -Apply

# Optional SHA pin for supervised rollouts:
powershell.exe -NoProfile -File .\tools\Update-ClipOpsCheckout.ps1 -Apply -ExpectedSha <full-40-character-reviewed-SHA>
```

The first invocation requires **Git for Windows** and a clone already available to the Windows Git executable. An extracted `ClipOps-Studio-TEST.zip`, a standalone executable, or a checkout inside an inaccessible WSL filesystem is **not** converted automatically. Preserve and reconcile the original first; create an independent clean checkout only after its actual path and ownership are verified.

## Automatically applying future releases

**Not enabled by this PR.** After Windows install and end-to-end validation, an owner-approved Windows Task Scheduler task could invoke the exact same script with `-Apply` at a chosen interval. It would still refuse to update any dirty/diverged checkout or unverified commit, and changes would take effect only on the next safe Studio launch. For a future packaged desktop application, build a separate **signed/versioned release updater** based on immutable release assets and SHA-256 checks; do not silently replace running EXEs or copy from PR branches.

Do **not** expose the Windows machine as a public GitHub Actions self-hosted runner. This is a public repository; GitHub's security guidance warns that untrusted PR code can compromise persistent self-hosted runners.

## Current blockers

- Reconcile Windows/Drive/uncommitted work and PRs #22–#25; do not force-merge.
- Repair the remaining async render browser failure and obtain all green CI gates on the target commit.
- Perform actual Windows WSL2 boot/render/QA; GitHub-hosted Linux CI is not a Windows acceptance certificate.
- Test physical 15–20 GiB import and bilingual real-footage editing before commercial claims.

References: [GitHub releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases), [GitHub Actions security](https://docs.github.com/en/actions/reference/security/secure-use), [Antigravity Remote Agents](https://antigravity.google/docs/remote-agents).