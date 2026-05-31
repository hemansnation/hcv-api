from pydantic import BaseModel, Field


class VerifyOptions(BaseModel):
    check_argument_support: bool = False
    generate_proof_pack: bool = False


class VerifyRequest(BaseModel):
    text: str = Field(min_length=10, max_length=50000)
    document_id: str | None = None
    options: VerifyOptions | None = None
