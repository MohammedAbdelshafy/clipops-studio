---
type: repository
status: active
owner_repo: MohammedAbdelshafy/clipops-studio
product_name: Clip Delivery Tools
source_of_truth: https://github.com/MohammedAbdelshafy/clipops-studio
---

# Clip Delivery Tools CONTEXT

One job: prepare batches of image assets using the code that exists in this repository. The full Remotion video pipeline described in the README is planned reference material, not shipped functionality.

## Inputs
- Current capabilities and roadmap caveats: [README](README.md)
- Implementation: [batch_images.py](batch_images.py)
- Tests: [test_batch_images.py](test_batch_images.py)

## Process
1. Read the batch brief and confirm output requirements.
2. Run the existing image-batch utility in dry-run or a safe sample first.
3. Check the generated files and any provider/runtime assumptions.
4. Keep the future video workflow separate until its code is committed and tested.
5. Track time and accepted outputs before offering a paid production package.

## Output
A batch of prepared images from the current utility, plus any run notes.

## Check
Run the repository's documented tests. Never sell the planned Remotion pipeline as available until its code, render host, quality checks and delivery path are present and verified.
