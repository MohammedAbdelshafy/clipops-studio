# Intel Quick Sync optional encoder — isolated review evidence

Date: 2026-11-20.
Source: local Windows branch review/clipops-qsv-encoder-selection-20261120.
The QSV-only files were reconstructed in a separate clean test worktree from
local base c539f3442c093b50a787c26e86bfe2ba2cd18996.
No other dirty working-tree changes or temporary probes are included.

## Implementation
- Real, timeout-bounded, one-frame FFmpeg hardware probes with cached results.
- Explicit CPU, NVENC and QSV choices. Auto retains NVENC then CPU unless
  CLIPOPS_AUTO_QSV=1 explicitly opts into QSV.
- Hardware failure falls back to libx264, recording the actual codec.
- Project settings, Studio UI, selection traces and render metadata.
- Human approval, rights and export QC remain unchanged.

## Previous-agent reported measurements (not remeasured by this note)
12 encoder regression tests and 165 total tests/52 subtests reportedly passed.
Ten-second 720p sample: CPU 8.48/10.75/15.35 s; QSV 10.88/11.96/15.00 s.
SSIM vs lossless reference CPU 0.997097, QSV 0.997182; mutual 0.996941.
No consistent QSV speed benefit has been demonstrated on this machine.
Intel UHD 620 QSV probe succeeded; NVIDIA MX250 NVENC probe failed.
These are narrow tests, not proof of comparable editorial quality.

## Release safeguards
Do not automatically enable QSV for all systems.
Do not include unrelated Windows serialization, loudness, model,
benchmark-probe or local performance files from the original dirty checkout.
Clean-runner CI and supervised editorial QA are required before merging.
No paid/public hosting, client footage transfer, publishing or cleanup.
