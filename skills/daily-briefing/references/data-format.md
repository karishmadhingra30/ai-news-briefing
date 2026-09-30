# Data format and helper commands

Python 3.11+; standard library only. Run from repository root:

```sh
python3 skills/daily-briefing/scripts/briefing.py collect --hours 30 --out runs/candidates.json
python3 skills/daily-briefing/scripts/briefing.py render --input examples/digest.json --out runs/preview
python3 -m unittest discover -s tests -v
```

Collection produces `collected_at`, `since`, `items` and per-source `coverage`. An item contains `title`, `url`, `published_at` (nullable), `source`, and `excerpt`. Undated items remain candidates and require date verification. Future-dated entries beyond a five-minute clock tolerance are excluded. A returned candidate is not necessarily relevant, reliable, or novel. The agent makes those decisions after reading sources.

The input to `render` contains:

- `date`: local edition date YYYY-MM-DD; `timezone`: IANA timezone.
- `coverage_start`, `coverage_end`: ISO 8601 timestamps with timezone; end cannot precede start.
- `preview`: boolean; true adds `PREVIEW |` to subjects and marks outputs visibly.
- `coverage_notes`: strings identifying actual failures, caveats, or complete collection.
- `stories`: at most 8 events. Empty is allowed for a verified quiet day.
- Per story: `event_key`, `revision_key`, `title`, `scores` (five 0–5 numeric dimensions), `score_reason`, `sources` (nonempty list of `title`, `url`), `plain` and `technical`.
- `plain`: `what_happened`, `why_it_matters`, `customer_angle`.
- `technical`: `what_changed`, `implementation`, `availability_and_limits`, `try_or_ask`.
- Optional `extras`: objects containing `label` (Worth trying or Coming up), `text`, `url`; the text must state verified event dates where applicable.

All prose fields are plain text, not Markdown or HTML. The renderer escapes them. Link only the structured source URLs and extras. Use stable event keys across editions and days; a revision describes a real change, not a different wording.

`render` writes `technical.html/.txt`, `plain-english.html/.txt`, and `messages.json`. The messages file contains edition, subject, event keys, and a MIME payload suitable for a Gmail connector. It deliberately omits recipient and credentials. Running it never sends email.

Each body ends with `AI-BRIEFING-RECORD` JSON containing version, date, edition, preview, coverage_start, coverage_end, and event/revision keys. Read only this workflow's sent records to reconstruct history. The companion command `history --input PATH` accepts exported briefing body text or a JSON array of objects with a `body` string, and extracts non-preview records. This supports tests and hosts that can export connector results. It is not an email reader or persistent backend.

Agent-side delivery uses the installed Gmail tools, not a Python API key. Consult the actual tool schema in the current runtime. Search Sent before and after each send; verify exact subject and recipient rather than assuming Gmail search matches exactly. A concurrent run can still race, so run only one instance at a time.
