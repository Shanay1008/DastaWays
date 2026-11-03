from datetime import datetime, timezone
import hashlib
import re
from uuid import uuid4

import fitz
from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import ApplicantDocument, ApplicationSession
from app.schemas import ApplicantProfile, DocumentSummary, HealthResponse, ReadinessReport, RequirementResult, RetrievalRequest, RetrievalResponse, SchemeSummary, SessionCreated
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
    profile = record.profile
    requirements: list[RequirementResult] = []
    profile_fields = [
        ("education_level", "Education level"),
        ("course", "Course of study"), ("academic_year", "Academic year"),
    ]
    for field, title in profile_fields:
        value = profile.get(field)
        requirements.append(RequirementResult(id=field, title=title, status="UNCERTAIN" if value else "MISSING",
                                              explanation="Self-reported in the applicant profile; the demo does not independently verify it." if value else "Provide this information in the applicant profile."))
    applicant_name = profile.get("applicant_name", "")
    normalized_name = re.sub(r"[^a-z0-9]", "", applicant_name.casefold())
    name_matches = [
        document for document in docs
        if normalized_name and normalized_name in re.sub(r"[^a-z0-9]", "", document.extracted_text.casefold())
    ]
    if name_matches:
        name_status = "VERIFIED"
        name_explanation = "The applicant name appears in the extracted PDF text. This confirms a text match only; it does not authenticate the PDF or verify the applicant's identity."
    elif docs:
        name_status = "UNCERTAIN"
        name_explanation = "The applicant name was not found in the extracted text of the uploaded PDFs. Check spelling or upload a readable document that includes the name."
    else:
        name_status = "UNCERTAIN"
        name_explanation = "Self-reported in the applicant profile. Upload readable supporting evidence to compare it against document text."
    requirements.insert(0, RequirementResult(id="applicant_name", title="Applicant name", status=name_status,
                                             explanation=name_explanation,
                                             evidence_documents=[d.filename for d in name_matches]))
    # This is a transparent demo heuristic, not official document validation.
    categories = {
        "transcript": ("Academic transcript", ("transcript", "marksheet", "mark sheet", "grade report")),
        "enrollment": ("Proof of enrollment", ("enrollment", "enrolment", "student status", "admission")),
    }
    for key, (title, terms) in categories.items():
        matches = [d for d in docs if any(term in (d.filename + " " + d.extracted_text).lower() for term in terms)]
        if not matches:
            state, explanation = "MISSING", "No uploaded PDF text clearly matched this demo document category."
        else:
            state, explanation = "UNCERTAIN", "A text or filename keyword matched. This only indicates possible evidence; a person must confirm the document is genuine, current, and valid."
        requirements.append(RequirementResult(id=key, title=title, status=state, explanation=explanation,
                                              evidence_documents=[d.filename for d in matches]))
    if profile.get("marks_percentage") is not None:
        requirements.append(RequirementResult(id="marks", title="Academic marks", status="UNCERTAIN",
                                              explanation="Marks were provided, but this synthetic demo defines no official threshold."))
    states = [item.status for item in requirements]
    overall = "NEEDS_ATTENTION" if "MISSING" in states else "REVIEW_REQUIRED" if "UNCERTAIN" in states else "READY_FOR_REVIEW"
    steps = ["Review each uncertain item and confirm the original document is valid.",
             "This synthetic demo has no official policy source; check the relevant authority's current instructions."]
    if "MISSING" in states:
        steps.insert(0, "Complete the missing profile fields or add relevant supporting evidence.")
    report = ReadinessReport(session_id=record.id, scheme_id=DEMO_SCHEME.id, overall_status=overall,
                             disclaimer="Synthetic demo assessment only. Not official eligibility, verification, or approval.",
                             requirements=requirements, next_steps=steps, generated_at=datetime.now(timezone.utc))
    record.report = report.model_dump(mode="json")
    db.commit()
    return report


@router.get("/sessions/{session_id}/report", response_model=ReadinessReport)
def get_report(record: ApplicationSession = Depends(require_owned_session)):
    if not record.report:
        raise HTTPException(status_code=404, detail="No readiness report yet. Run an assessment first.")
    return record.report


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
