import hashlib
from uuid import uuid4

import fitz
from fastapi import APIRouter, Depends, Header, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import ApplicantDocument, ApplicationSession
from app.schemas import ApplicantProfile, ChatRequest, ChatResponse, DocumentSummary, HealthResponse, ReadinessReport, RetrievalRequest, RetrievalResponse, SchemeSummary, SessionCreated
from app.security import create_session_token, hash_token

router = APIRouter(prefix="/api")
DEMO_SCHEME = SchemeSummary(
    id="demo-scholarship",
    name="DastaWays Sample Scholarship",
    label="Synthetic demo",
    description="A sample workflow for demonstrating readiness checks. This is not an official scheme.",
)


def require_owned_session(
    session_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ApplicationSession:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A session access token is required")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A session access token is required")
    record = db.query(ApplicationSession).filter_by(id=session_id, token_hash=hash_token(token)).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return record


@router.get("/health", response_model=HealthResponse)
def health():
    from app.config import get_settings
    return HealthResponse(status="ok", app=get_settings().app_name)


@router.get("/schemes", response_model=list[SchemeSummary])
def list_schemes():
    return [DEMO_SCHEME]


@router.get("/schemes/{scheme_id}", response_model=SchemeSummary)
def get_scheme(scheme_id: str):
    if scheme_id != DEMO_SCHEME.id:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return DEMO_SCHEME


@router.post("/sessions", response_model=SessionCreated, status_code=status.HTTP_201_CREATED)
def create_session(db: Session = Depends(get_db)):
    token = create_session_token()
    record = ApplicationSession(id=str(uuid4()), token_hash=hash_token(token))
    db.add(record)
    db.commit()
    db.refresh(record)
    return SessionCreated(session_id=record.id, access_token=token, created_at=record.created_at)


@router.get("/sessions/{session_id}")
def get_session(record: ApplicationSession = Depends(require_owned_session)):
    return {"session_id": record.id, "created_at": record.created_at}


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(record: ApplicationSession = Depends(require_owned_session), db: Session = Depends(get_db)):
    from app.rag.retrieval import delete_session_evidence

    try:
        delete_session_evidence(record.id)
    except ModuleNotFoundError:
        # No vector collection exists yet; there is nothing to remove.
        pass
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not remove this workspace's indexed evidence") from exc
    db.query(ApplicantDocument).filter_by(session_id=record.id).delete()
    db.delete(record)
    db.commit()


@router.put("/sessions/{session_id}/profile", response_model=ApplicantProfile)
def save_profile(profile: ApplicantProfile, record: ApplicationSession = Depends(require_owned_session), db: Session = Depends(get_db)):
    record.profile = profile.model_dump()
    record.report = None
    db.commit()
    return profile


@router.get("/sessions/{session_id}/profile", response_model=ApplicantProfile | None)
def get_profile(record: ApplicationSession = Depends(require_owned_session)):
    return record.profile


@router.post("/sessions/{session_id}/documents", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    record: ApplicationSession = Depends(require_owned_session),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if file.content_type != "application/pdf" or not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Upload a PDF file")
    raw = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"PDF exceeds the {settings.max_upload_mb} MB limit")
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="File content is not a valid PDF")
    digest = hashlib.sha256(raw).hexdigest()
    existing = db.query(ApplicantDocument).filter_by(session_id=record.id, content_hash=digest).first()
    if existing:
        raise HTTPException(status_code=409, detail="This PDF has already been uploaded to this workspace")
    try:
        pdf = fitz.open(stream=raw, filetype="pdf")
        pages = [page.get_text().strip() for page in pdf]
        page_count = pdf.page_count
        pdf.close()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The PDF could not be opened or parsed") from exc
    extracted = "\n".join(f"[Page {i + 1}] {text}" for i, text in enumerate(pages) if text)
    if not extracted.strip():
        raise HTTPException(status_code=422, detail="No readable text was found. Scanned PDFs are not supported in this module.")
    document = ApplicantDocument(
        id=str(uuid4()), session_id=record.id, filename=file.filename[:255], content_hash=digest,
        page_count=page_count, extracted_text=extracted, status="processed",
    )
    db.add(document)
    record.report = None
    db.commit()
    db.refresh(document)
    try:
        from app.rag.retrieval import index_applicant_document
        index_applicant_document(record.id, document.id, document.filename, document.extracted_text)
        document.status = "processed_and_indexed"
        db.commit()
    except Exception:
        # Keep the uploaded text available for the deterministic module even if local
        # embedding setup is missing; retrieval UI reports the unavailable index.
        document.status = "processed_index_unavailable"
        db.commit()
    return DocumentSummary(id=document.id, filename=document.filename, page_count=document.page_count,
                           status=document.status, text_characters=len(extracted), created_at=document.created_at)


@router.get("/sessions/{session_id}/documents", response_model=list[DocumentSummary])
def list_documents(record: ApplicationSession = Depends(require_owned_session), db: Session = Depends(get_db)):
    docs = db.query(ApplicantDocument).filter_by(session_id=record.id).order_by(ApplicantDocument.created_at).all()
    return [DocumentSummary(id=d.id, filename=d.filename, page_count=d.page_count, status=d.status,
                            text_characters=len(d.extracted_text), created_at=d.created_at) for d in docs]


@router.delete("/sessions/{session_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, record: ApplicationSession = Depends(require_owned_session), db: Session = Depends(get_db)):
    document = db.query(ApplicantDocument).filter_by(id=document_id, session_id=record.id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        from app.rag.retrieval import delete_applicant_document
        delete_applicant_document(record.id, document.id)
    except ModuleNotFoundError:
        pass
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not remove the document's indexed evidence") from exc
    db.delete(document)
    record.report = None
    db.commit()


@router.post("/sessions/{session_id}/assess", response_model=ReadinessReport)
def assess(record: ApplicationSession = Depends(require_owned_session), db: Session = Depends(get_db)):
    if not record.profile:
        raise HTTPException(status_code=409, detail="Save applicant information before assessment")
    docs = db.query(ApplicantDocument).filter_by(session_id=record.id).all()
    from app.services.assessment import evaluate_readiness
    report = evaluate_readiness(record.id, DEMO_SCHEME.id, record.profile, docs)
    record.report = report.model_dump(mode="json")
    db.commit()
    return report


@router.get("/sessions/{session_id}/report", response_model=ReadinessReport)
def get_report(record: ApplicationSession = Depends(require_owned_session)):
    if not record.report:
        raise HTTPException(status_code=404, detail="No readiness report yet. Run an assessment first.")
    return record.report


@router.get("/sessions/{session_id}/report/download")
def download_readiness_report(
    record: ApplicationSession = Depends(require_owned_session),
    db: Session = Depends(get_db),
):
    from app.services.assessment import evaluate_readiness
    from app.services.report_pdf import render_readiness_report

    if not record.report:
        if not record.profile:
            raise HTTPException(status_code=404, detail="Save applicant information and generate a report first")
        documents = db.query(ApplicantDocument).filter_by(session_id=record.id).all()
        report = evaluate_readiness(record.id, DEMO_SCHEME.id, record.profile, documents)
        record.report = report.model_dump(mode="json")
        db.commit()
    else:
        report = ReadinessReport.model_validate(record.report)
    pdf_bytes = render_readiness_report(report, record.profile or {})
    filename = f"dastaways-readiness-{record.id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/sessions/{session_id}/retrieve", response_model=RetrievalResponse)
def retrieve_for_session(
    request: RetrievalRequest,
    record: ApplicationSession = Depends(require_owned_session),
    db: Session = Depends(get_db),
):
    from app.rag.retrieval import search_applicant_evidence, search_policy

    try:
        results = []
        if request.scope in {"policy", "both"}:
            results.append(search_policy(request.query, DEMO_SCHEME.id))
        if request.scope in {"evidence", "both"}:
            from app.rag.retrieval import index_applicant_document
            saved_documents = db.query(ApplicantDocument).filter_by(session_id=record.id).all()
            for document in saved_documents:
                index_applicant_document(record.id, document.id, document.filename, document.extracted_text)
            results.append(search_applicant_evidence(request.query, record.id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Retrieval is unavailable. Install the Phase 3 dependencies and run policy ingestion first.") from exc
    sources = [source for result in results for source in result["sources"]]
    insufficient = not sources
    message = ("Retrieved source passages are shown below. This module does not generate a model answer."
               if sources else "No sufficiently relevant source passage was found. The system will not guess.")
    return RetrievalResponse(query=request.query, scope=request.scope, insufficient_evidence=insufficient,
                             message=message, sources=sources)


@router.post("/sessions/{session_id}/chat", response_model=ChatResponse)
def chat_with_agent(
    request: ChatRequest,
    record: ApplicationSession = Depends(require_owned_session),
):
    from app.agent.workflow import run_chat

    try:
        result = run_chat(record.id, request.query, DEMO_SCHEME.id)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        from app.config import get_settings
        settings = get_settings()
        if settings.openai_api_key:
            return ChatResponse(answer="The configured AI provider could not complete this request. No AI-generated answer was produced. Check the API key, model, and provider connection.",
                                mode="llm_error", error_info="LLM request failed")
        raise HTTPException(status_code=503, detail="The agent workflow is unavailable. Check the Phase 4 dependencies.") from exc
    return ChatResponse(**result)
