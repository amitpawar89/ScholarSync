# ScholarSync Project Context

## Project Overview

ScholarSync converts a student's own project report, provided as PDF, Word, or LaTeX, into a properly formatted professional research paper draft using IEEE, ACM, or Springer styles.

The system must never fabricate facts, numbers, results, comparisons, or contributions.

## Core Principle

ScholarSync may use only factual information that comes from the student's own report.

- Numbers, results, comparisons, and contributions must never be invented.
- General background or related-work text may be suggested by AI, but it must be clearly flagged for the student to approve, edit, or remove.
- Every fact extracted from the report must retain its source location, such as page number or paragraph reference, for traceability.

## Review Screen Marking Rules

These colours and markings are used only in the review screen. They must not appear in the final exported paper.

- **No marking:** Information came from the report and passed verification.
- **Yellow - suggestion:** AI added this content. The student must approve, edit, or remove it.
- **Red - issue:** Verification failed, such as a number mismatch, broken citation link, or unsupported claim. The issue must be fixed before the final paper can be generated.
- **Blue - citation:** External reference. The student must check the link.

The final exported paper must be clean and contain no review colours or markings.

## High-Level Pipeline

1. Upload the student's report in PDF, Word, or LaTeX format.
2. Parse the report into sections and text while preserving page locations. Use PyMuPDF for PDF parsing.
3. Extract facts into a fixed JSON schema containing:
   - Problem
   - Objectives
   - Method
   - Dataset
   - Metrics
   - Results
   - Project type
4. Detect missing required fields and ask the student for the missing information. Never guess.
5. Retrieve related work from Semantic Scholar and arXiv, then verify citations.
6. Generate paper sections using only verified facts and verified citations.
7. Verify every sentence with an NLI check and verify every number by exact matching against the report.
8. Display a review screen with the appropriate markings so the student can approve, edit, or remove content.
9. Allow LaTeX-to-PDF export only after all red issues have been resolved. Support IEEE, ACM, and Springer templates.

## Technology Stack

- Python
- FastAPI for the backend
- PyMuPDF for PDF parsing
- python-docx for Word parsing
- LaTeX parsing support
- An LLM API for fact extraction and paper generation
- A Hugging Face NLI model for local sentence verification
- sentence-transformers for similarity checks
- Semantic Scholar API for related work and citation retrieval
- arXiv API for related work and citation retrieval
- Crossref API for citation verification
- LaTeX templates including IEEEtran, acmart, and Springer templates
- BibTeX for bibliography output
- SQLite for storing extracted facts and student decisions
- React for the review-screen UI in a later phase

## Current Development Phase

The project is being built incrementally, phase by phase. The current phase is:

### Phase 0 - Extracting Text from a PDF Report

The immediate focus is extracting text from a PDF report while preserving page-level traceability.

Do not generate the entire project at once. Work only on the specific phase or feature requested in each task.

## Development Constraints

- Preserve the student's original facts and their source locations.
- Never infer or invent missing information.
- Ask the student when required information is missing.
- Keep externally suggested content visibly distinguishable from report-derived content in the review screen.
- Verify claims, citations, sentences, and numbers before allowing export.
- Keep the final paper free of all review markings.
- Prefer small, incremental changes that match the current development phase.
- Do not implement later pipeline phases unless explicitly requested.

## Current Status (Updated)

- The project now has a working FastAPI backend under backend/ with these endpoints: /health, /extract-text, /structured-facts (Gemini-powered fact extraction with block-level evidence verification), and /generate-paper (budget-aware section drafting from verified facts).
- Facts are extracted with strict verification: every fact's claim and evidence must be a substring match against the original PDF's text blocks (page_number + block_number), otherwise it is marked unverified and excluded.
- The POST /generate-paper endpoint is built and wired into main.py, integrating section_planner.py and paper_sections.py to produce draft_requires_review sections with budget protection.
- Rate limiting: this project uses the Gemini free tier only. gemini.py enforces a daily request budget (default 5/day, configurable via SCHOLARSYNC_GEMINI_DAILY_REQUEST_LIMIT), serializes requests with a lock, and only retries transient 429/503 errors (max 3 attempts, exponential backoff). Never increase concurrency or remove this rate limiting without being asked.
- Tests in tests/test_backend.py mock Gemini and must keep passing; never call the real Gemini API in tests.
- Do not delete or restructure files without explaining what changed and why.
- I am a student with limited coding experience. Always explain what you changed and why, in simple terms, before or after making edits.

