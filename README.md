# DastaWays

**From paperwork to possibilities.**

DastaWays is an evidence-driven application readiness platform for scholarship, grant, and public-service applications. This repository is being built incrementally. The current MVP has a FastAPI service, SQLite-backed anonymous sessions, a React/TypeScript workflow, deterministic readiness checks, and source retrieval.

## Current module: Phase 5 report export

- Synthetic demo scholarship with no official policy claims
- Applicant profile form (name, education level, course, academic year, optional marks)
- PDF upload with size/type checks, SHA-256 duplicate detection, page-aware text extraction, and per-session isolation
- Deterministic report that compares the applicant name with extracted PDF text, marks other self-reported fields `UNCERTAIN`, absent evidence `MISSING`, and keyword-only document matches `UNCERTAIN`
- Report disclaimer and next steps; PDFs and workspaces can be deleted
- SQLite stores extracted PDF text; the original PDF bytes are not retained
- Additive SQLite migration for users who already ran Phase 1
- Local semantic retrieval uses LangChain text splitting, Hugging Face sentence-transformer embeddings, and persistent Chroma collections
- Synthetic demo policy passages carry section citations; uploaded applicant evidence is indexed separately and filtered by the owning session
- Retrieved excerpts are returned as sources; this module does not fabricate an LLM-generated answer
- LangGraph workflow with explicit state, conditional tool-call routing, and five session-bound tools
- Optional OpenAI chat model with tool calling; without an API key, a labeled deterministic demo route runs instead
- Downloadable, session-protected PDF readiness report with applicant summary, per-requirement status/explanations, evidence filenames, next steps, and advisory disclaimer

There is no conventional account/password system. Session tokens are a lightweight MVP ownership mechanism, not production-grade authentication. Do not put real sensitive data in this demo. Scanned PDFs and OCR are not supported yet. The included scholarship policy is wholly synthetic, not official. With an OpenAI key configured, chat questions and any profile or document excerpts selected by tools are sent to the configured model provider; the UI displays this disclosure.

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

### Prepare the Phase 3 retrieval index

The first indexing/search command downloads the configured Hugging Face embedding model if it is not cached. From the repository root, with the backend virtual environment active:

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
python -m app.rag.ingest_demo_policy
python -m app.rag.evaluate_retrieval
```

The first command indexes the invented sample policy into `data/chroma/`. The second runs three source-retrieval checks. Applicant PDFs are indexed into a separate Chroma collection and every evidence query filters by the current session ID. The search UI shows the retrieved passages with their source and page/section metadata; it does not yet compose a natural-language answer.

### Configure and try the Phase 4 assistant

For real model inference, put your own key in the local `.env` file:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=your_key_here
# Optional: OPENAI_BASE_URL=https://your-compatible-endpoint/v1
```

Restart the API after changing `.env`. Without a key, the LangGraph workflow uses a clearly labeled deterministic demo tool-selection route and does not claim model inference. With a key, the assistant can use these tools: `search_scheme_policy`, `get_applicant_profile`, `inspect_submitted_documents`, `evaluate_requirements`, and `generate_readiness_report`. LangGraph routes tool calls through a `ToolNode`; deterministic logic remains the authority for requirement statuses. Never commit `.env` or share the key.

In the workspace, ask “What documents does the sample request?” or “What am I missing?”. The UI shows the assistant mode, tool activity, readiness results when relevant, and citations from retrieved passages. No application submission or other external action is available.

The readiness report panel has a **Download PDF** action. It downloads the current saved report; if the report is visible from a deterministic chat check but not yet persisted, the endpoint regenerates and saves it from the current profile and documents before export. The PDF is generated in memory and is not retained on the server.

### Try the Phase 2 workflow

1. Create a private workspace.
2. Fill and save the applicant profile.
3. Upload a text PDF with `transcript` or `marksheet` in its name/content and one with `enrollment` or `admission` in its name/content. A PDF whose text cannot be extracted is rejected with an explanation.
4. Generate a readiness report. A profile name found in extracted PDF text can be marked `VERIFIED` for text consistency only; that does not verify identity or document authenticity. Other self-reported profile details and keyword-matched document categories remain `UNCERTAIN`.
5. Click **Download PDF** in the report and review the exported summary, statuses, evidence references, next steps, and disclaimer.
6. Ask a question in “Search your source documents” and inspect matching policy/evidence passages and citations.
7. Delete test documents or the full workspace when finished.

Verification so far: the user ran the Phase 3 retrieval evaluation and confirmed all three cases passed. `npm run build` and Python source compilation pass. I generated and visually checked representative one-page and longer multi-page PDFs with ReportLab/Poppler. The live FastAPI download route has not been exercised here, and real model inference still requires a configured provider key.

## Planned modules

1. Foundation: API, frontend, configuration, database, anonymous session ownership.
2. One clearly labeled demo scheme, applicant profile, PDF uploads, deterministic readiness checks.
3. Policy/evidence ingestion, embeddings, Chroma retrieval and source citations (complete; retrieval evaluation passed).
4. LLM integration and LangGraph tool-calling workflow.
5. Downloadable readiness report and report polish (current).
6. Tests, end-to-end verification, and technical documentation.

The current scheme is explicitly synthetic and carries no official eligibility criteria.
