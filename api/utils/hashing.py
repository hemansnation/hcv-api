import hashlib
import json


def generate_record_hash(record: dict) -> str:
    serialized = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def generate_document_hash(citation_hashes: list[str]) -> str:
    combined = "".join(sorted(citation_hashes))
    return hashlib.sha256(combined.encode()).hexdigest()
