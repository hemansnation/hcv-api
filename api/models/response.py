from typing import Optional

from pydantic import BaseModel


class ArgumentSupport(BaseModel):
    score: float
    flag: str
    message: str


class CitationResult(BaseModel):
    citation_raw: str
    citation_normalized: str
    case_name: str
    exists: bool
    confidence_score: float
    sources_checked: list[str]
    found_in: list[str]
    argument_support: Optional[ArgumentSupport] = None
    audit_id: str
    cached: bool


class VerifyResponse(BaseModel):
    request_id: str
    document_id: Optional[str]
    processed_at: str
    citations_found: int
    processing_time_ms: int
    results: list[CitationResult]
    document_audit_hash: str
    proof_pack_url: Optional[str] = None
