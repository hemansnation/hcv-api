from fastapi import APIRouter

router = APIRouter()


@router.get("/v1/audit/{audit_id}")
async def get_audit(audit_id: str) -> dict:
    return {"detail": "not implemented"}


@router.get("/v1/audit/document/{document_id}")
async def get_audit_by_document(document_id: str) -> dict:
    return {"detail": "not implemented"}
