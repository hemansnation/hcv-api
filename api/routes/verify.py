import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, Request

from api.db.audit import log_citation_verification
from api.db.connection import get_db_pool
from api.models.request import VerifyRequest
from api.models.response import CitationResult, VerifyResponse
from api.services.extractor import extract_citations, normalize_citation
from api.services.scorer import calculate_confidence_score
from api.services.verifier import verify_all_citations
from api.utils.auth import get_current_client
from api.utils.hashing import generate_document_hash

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_scorer_input(verification: dict) -> list[dict]:
    sources_checked = verification.get("sources_checked") or []
    found_in = set(verification.get("found_in") or [])
    return [{"source": s, "found": s in found_in} for s in sources_checked]


@router.post("/v1/verify", response_model=VerifyResponse)
async def verify_citations(
    request: Request,
    body: VerifyRequest,
    client: Annotated[dict, Depends(get_current_client)],
    pool: Annotated[asyncpg.Pool | None, Depends(get_db_pool)],
) -> VerifyResponse:
    start_ms = time.monotonic()
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    processed_at = datetime.now(timezone.utc).isoformat()

    citations = extract_citations(body.text)

    if not citations:
        return VerifyResponse(
            request_id=request_id,
            document_id=body.document_id,
            processed_at=processed_at,
            citations_found=0,
            processing_time_ms=int((time.monotonic() - start_ms) * 1000),
            results=[],
            document_audit_hash=generate_document_hash([]),
        )

    verifications = await verify_all_citations(citations)

    results: list[CitationResult] = []
    audit_hashes: list[str] = []

    for verification in verifications:
        scorer_input = _build_scorer_input(verification)
        score = calculate_confidence_score(scorer_input)

        audit_id = ""
        if pool is not None:
            try:
                audit_id = await log_citation_verification(
                    db_pool=pool,
                    request_id=request_id,
                    client_id=client["id"],
                    document_id=body.document_id,
                    citation_raw=verification["citation_raw"],
                    citation_normalized=verification.get("citation_normalized"),
                    verification_result=verification,
                    confidence_score=score,
                )
                audit_hashes.append(audit_id)
            except Exception:
                logger.exception(
                    "Audit log write failed for citation %r (request_id=%s)",
                    verification["citation_raw"],
                    request_id,
                )

        results.append(
            CitationResult(
                citation_raw=verification["citation_raw"],
                citation_normalized=verification.get("citation_normalized", ""),
                case_name=verification.get("case_name", ""),
                exists=verification.get("exists", False),
                confidence_score=score,
                sources_checked=verification.get("sources_checked") or [],
                found_in=verification.get("found_in") or [],
                audit_id=f"sha256:{audit_id}" if audit_id else "",
                cached=verification.get("cached", False),
            )
        )

    return VerifyResponse(
        request_id=request_id,
        document_id=body.document_id,
        processed_at=processed_at,
        citations_found=len(results),
        processing_time_ms=int((time.monotonic() - start_ms) * 1000),
        results=results,
        document_audit_hash=(
            f"sha256:{generate_document_hash(audit_hashes)}" if audit_hashes else ""
        ),
    )
