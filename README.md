# DastaWays

**From paperwork to possibilities.**

DastaWays is an evidence-driven application readiness platform for scholarship, grant, and public-service applications. This repository is being built incrementally. The current foundation provides a FastAPI service, SQLite-backed anonymous sessions, and a small React/TypeScript frontend.

## Current module: Phase 2 workflow

- Synthetic demo scholarship with no official policy claims
- Applicant profile form (name, education level, course, academic year, optional marks)
- PDF upload with size/type checks, SHA-256 duplicate detection, page-aware text extraction, and per-session isolation
- Deterministic report that marks self-reported fields `UNCERTAIN`, absent evidence `MISSING`, and keyword-only document matches `UNCERTAIN`
- Report disclaimer and next steps; PDFs and workspaces can be deleted
- SQLite stores extracted PDF text; the original PDF bytes are not retained
- Additive SQLite migration for users who already ran Phase 1

There is no conventional account/password system. Session tokens are a lightweight MVP ownership mechanism, not production-grade authentication. Do not put real sensitive data in this demo. Scanned PDFs and OCR are not supported yet.

## Run locally

Requirements: Python 3.11+, Node.js 20+.

1. Copy `.env.example` to `.env` and adjust values if needed.
2. Backend, from the repository root:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r backend\requirements.txt
   uvicorn app.main:app --app-dir backend --reload
   ```

3. Frontend in another terminal:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

The API is at `http://localhost:8000`; interactive API docs are at `http://localhost:8000/docs`; the frontend is at `http://localhost:5173`.

### Try the Phase 2 workflow

1. Create a private workspace.
2. Fill and save the applicant profile.
3. Upload a text PDF with `transcript` or `marksheet` in its name/content and one with `enrollment` or `admission` in its name/content. A PDF whose text cannot be extracted is rejected with an explanation.
4. Generate a readiness report. Profile facts and keyword-matched documents remain `UNCERTAIN`; no document is treated as valid based only on its name.
5. Delete test documents or the full workspace when finished.

Verification in this environment: `npm run build` passes (TypeScript compile and Vite production build); Python source compilation passes. The API could not be started because FastAPI and SQLAlchemy are not installed in the available Python runtime. No backend or end-to-end test results are claimed.

## Planned modules

1. Foundation: API, frontend, configuration, database, anonymous session ownership.
2. One clearly labeled demo scheme, applicant profile, PDF uploads, deterministic readiness checks (current).
3. Policy/evidence ingestion, embeddings, Chroma retrieval, grounded answers.
4. LLM integration and LangGraph tools/workflow.
5. Connected report and assistant UI, downloadable report.
6. Tests, end-to-end verification, and technical documentation.

The current scheme is explicitly synthetic and carries no official eligibility criteria.
