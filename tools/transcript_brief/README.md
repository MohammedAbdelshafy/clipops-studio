# Offline Transcript Content Brief (review-only MVP)

This is an extractive editorial drafting utility. It does not create videos, infer timestamps, fact-check statements, upload data, or send outreach. Use only transcripts that the customer is authorized to provide.

## Test and run

From this directory:

```bash
python3 -m unittest -v test_transcript_brief.py
python3 transcript_brief.py sample.txt --title "Synthetic demo" --output brief.json
python3 -m json.tool brief.json >/dev/null
```

No third-party dependencies, credentials, or network requests are required. The generated output is a draft; a human must review every excerpt and hook before delivery. The program writes to the path supplied in `--output`; use a non-production destination.

## Commercial pilot (proposal, not published)

**Transcript Content Brief — $49 pilot hypothesis.** One client-supplied transcript (up to 30 minutes of recording, supplied as text), up to three candidate excerpts/hooks, a human-reviewed one-page brief, and one revision. Proposed 48-hour turnaround is subject to capacity. No video editing, subtitles, timestamps, posting, guaranteed reach, or automated clipping.

### Acceptance and revenue gates

1. Verify the client owns or is permitted to use the transcript.
2. Review every quotation against the source; do not promise generated hooks are factual.
3. Confirm deliverable format and scope with the client before payment.
4. Verify a lawful live payment method and settlement eligibility before offering checkout. Sandbox credentials do not establish live payments.
5. Record qualified inbound requests, paid pilots, delivery time, revisions, refunds and repeat purchases. Forecasts are not realized revenue.
6. Do not contact suppressed or Do Not Send leads. No CRM changes or outreach are part of this PR.

### Next safe iteration

Add an optional human-reviewable Markdown export with source excerpt references, then test exact quote preservation, input-size limits, UTF-8 handling, and malformed input. Keep the renderer and paid API integrations out of this MVP.

## Official references

- https://docs.python.org/3/library/unittest.html
- https://docs.python.org/3/library/argparse.html
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://docs.stripe.com/testing
