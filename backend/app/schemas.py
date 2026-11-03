from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    app: str


class SchemeSummary(BaseModel):
    id: str
    name: str
    label: str
    description: str


class SessionCreated(BaseModel):
    session_id: str
    access_token: str
    token_type: str = "bearer"
    created_at: datetime


class ApplicantProfile(BaseModel):
    applicant_name: str = Field(min_length=1, max_length=120)
    education_level: str = Field(min_length=1, max_length=80)
    course: str = Field(min_length=1, max_length=160)
    academic_year: str = Field(min_length=1, max_length=40)
    marks_percentage: float | None = Field(default=None, ge=0, le=100)


class DocumentSummary(BaseModel):
    id: str
    filename: str
    page_count: int
    status: str
    text_characters: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RequirementResult(BaseModel):
    id: str
    title: str
    status: str
    explanation: str
    evidence_documents: list[str] = Field(default_factory=list)


class ReadinessReport(BaseModel):
    session_id: str
    scheme_id: str
    overall_status: str
    disclaimer: str
    requirements: list[RequirementResult]
    next_steps: list[str]
    generated_at: datetime


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    scope: str = Field(default="policy", pattern="^(policy|evidence|both)$")


class RetrievedSource(BaseModel):
    document: str
    page: int | None = None
    section: str | None = None
    excerpt: str
    distance: float


class RetrievalResponse(BaseModel):
    query: str
    scope: str
    insufficient_evidence: bool
    message: str
    sources: list[RetrievedSource]


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class ToolActivity(BaseModel):
    tool: str
    status: str
    summary: str


class ChatResponse(BaseModel):
    answer: str
    mode: str
    tool_activity: list[ToolActivity] = Field(default_factory=list)
    citations: list[RetrievedSource] = Field(default_factory=list)
    requirement_assessment: dict | None = None
    error_info: str | None = None
