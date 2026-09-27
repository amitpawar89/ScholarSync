# ScholarSync

ScholarSync is currently a Phase 0 backend for extracting complete PDF report
text with page and block source locations. Later fact extraction is allowed to
use Gemini only after evidence is preserved and validated against the upload.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Put a Gemini API key in `.env` only for AI-dependent endpoints. Health and text
extraction do not require a key.

## Run

```powershell
python -m backend.main
```

Open `http://127.0.0.1:8000/docs` for the interactive API documentation.

## Endpoints

- `GET /health`: always returns `200` and `{"status":"ok"}`.
- `POST /extract-text`: accepts a PDF upload and returns every page, raw text,
  cleaned text, and block bounding boxes.
- `POST /structured-facts`: accepts a PDF upload and returns schema-validated,
  source-checked facts. It requires `GEMINI_API_KEY`.

## Limits and errors

Defaults are 20 MiB per upload, 100 pages, and 1,000,000 extracted characters.
Structured-facts AI input is separately limited to 200,000 characters by
`SCHOLARSYNC_STRUCTURED_MAX_TEXT_CHARS`, and structured output is capped at 100
facts by `SCHOLARSYNC_MAX_STRUCTURED_FACTS`. Override these and other limits with
the `SCHOLARSYNC_*` variables in `.env`. Uploads must have a
valid `%PDF-` signature and contain extractable text. Malformed, encrypted,
empty, oversized, and unsupported PDFs return safe `4xx` responses. Missing
Gemini configuration returns `503` from AI-dependent endpoints. The service
does not silently discard table-of-contents pages in the trusted extraction
path.

The Gemini integration is deliberately free-tier compatible: it serializes one
request at a time, uses low thinking, caps output tokens, and defaults to only
five Gemini attempts per process day. Only transient `429` and `503` failures
are retried a maximum of three times with bounded exponential backoff. Invalid
requests and authentication failures are not retried. Free-tier quota can still
be exhausted; waiting for the provider quota reset is expected and no billing
or paid-plan setup is required.

Paper section titles are report-driven. Only facts marked `verified` and carrying
server-generated IDs can be selected by the planner or passed to section writing.
If no verified facts support a section, it is omitted and the saved fact response's
missing-information questions are shown instead.

Paper generation saves partial results safely. Each generated section is marked
`draft_requires_review` and includes the verified fact IDs used to create it;
generated prose is never presented as verified or final. The result also records
`generated_sections`, `skipped_sections`, `remaining_budget`, and `next_action`.
The local daily request counter is a per-process courtesy limit: it resets when
the server restarts and does not replace Gemini provider quotas. A provider
free-tier quota may still be exhausted, in which case waiting for its reset is
expected.
## Tests

```powershell
pytest -q
```

Tests mock Gemini and never use a real API key.