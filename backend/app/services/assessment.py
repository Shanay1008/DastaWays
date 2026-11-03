from datetime import datetime, timezone
import re

from app.schemas import ReadinessReport, RequirementResult


def evaluate_readiness(session_id: str, scheme_id: str, profile: dict, docs: list) -> ReadinessReport:
    requirements: list[RequirementResult] = []
    for field, title in [("education_level", "Education level"), ("course", "Course of study"),
                         ("academic_year", "Academic year")]:
        value = profile.get(field)
        requirements.append(RequirementResult(
            id=field, title=title, status="UNCERTAIN" if value else "MISSING",
            explanation="Self-reported in the applicant profile; the demo does not independently verify it."
            if value else "Provide this information in the applicant profile.",
        ))

    applicant_name = profile.get("applicant_name", "")
    normalized_name = re.sub(r"[^a-z0-9]", "", applicant_name.casefold())
    name_matches = [doc for doc in docs if normalized_name and normalized_name in
                    re.sub(r"[^a-z0-9]", "", doc.extracted_text.casefold())]
    if name_matches:
        name_status = "VERIFIED"
        name_explanation = ("The applicant name appears in the extracted PDF text. This confirms a text match only; "
                            "it does not authenticate the PDF or verify the applicant's identity.")
    elif docs:
        name_status = "UNCERTAIN"
        name_explanation = ("The applicant name was not found in the extracted text of the uploaded PDFs. "
                            "Check spelling or upload a readable document that includes the name.")
    else:
        name_status = "UNCERTAIN"
        name_explanation = ("Self-reported in the applicant profile. Upload readable supporting evidence "
                            "to compare it against document text.")
    requirements.insert(0, RequirementResult(id="applicant_name", title="Applicant name", status=name_status,
                                             explanation=name_explanation,
                                             evidence_documents=[doc.filename for doc in name_matches]))

    categories = {
        "transcript": ("Academic transcript", ("transcript", "marksheet", "mark sheet", "grade report")),
        "enrollment": ("Proof of enrollment", ("enrollment", "enrolment", "student status", "admission")),
    }
    for key, (title, terms) in categories.items():
        matches = [doc for doc in docs if any(term in (doc.filename + " " + doc.extracted_text).lower() for term in terms)]
        if not matches:
            state, explanation = "MISSING", "No uploaded PDF text clearly matched this demo document category."
        else:
            state = "UNCERTAIN"
            explanation = ("A text or filename keyword matched. This only indicates possible evidence; a person "
                           "must confirm the document is genuine, current, and valid.")
        requirements.append(RequirementResult(id=key, title=title, status=state, explanation=explanation,
                                              evidence_documents=[doc.filename for doc in matches]))
    if profile.get("marks_percentage") is not None:
        requirements.append(RequirementResult(id="marks", title="Academic marks", status="UNCERTAIN",
                                              explanation="Marks were provided, but this synthetic demo defines no official threshold."))

    states = [item.status for item in requirements]
    overall = "NEEDS_ATTENTION" if "MISSING" in states else "REVIEW_REQUIRED" if "UNCERTAIN" in states else "READY_FOR_REVIEW"
    steps = ["Review each uncertain item and confirm the original document is valid.",
             "This synthetic demo has no official policy source; check the relevant authority's current instructions."]
    if "MISSING" in states:
        steps.insert(0, "Complete the missing profile fields or add relevant supporting evidence.")
    return ReadinessReport(session_id=session_id, scheme_id=scheme_id, overall_status=overall,
                           disclaimer="Synthetic demo assessment only. Not official eligibility, verification, or approval.",
                           requirements=requirements, next_steps=steps, generated_at=datetime.now(timezone.utc))
