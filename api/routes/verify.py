from fastapi import APIRouter

router = APIRouter()


@router.post("/v1/verify")
async def verify_citations() -> dict:
    return {"detail": "not implemented"}
