# Architecture Documentation

# Architecture Specification
## Hallucination Citation Verifier API — v1.0

This document is the source of truth for how the system is built.
Claude Code reads this before making any architectural decision.

---

## System Overview

The HCV API is a stateless, async REST API. It receives text containing legal citations, verifies them against legal databases in parallel, scores confidence, logs an audit trail, and returns structured JSON.

Every request flows through exactly these layers, in order:

```
Request
  → Auth (API key validation)
  → Rate Limiter (per-key, Redis-backed)
  → Request Validator (Pydantic)
  → Citation Extractor (eyecite)
  → Cache Check (Redis — skip verification if seen in last 24h)
  → Parallel Verifier (async, multiple DB sources)
  → Confidence Scorer
  → Audit Logger (PostgreSQL, append-only)
  → Response Builder
Response
```

---

## API Endpoints

### POST /v1/verify

The core endpoint.

**Request:**
```json
{
  "text": "string — the legal document text, max 50,000 chars",
  "document_id": "string — optional, client's own reference ID",
  "tier": "starter | professional | enterprise",
  "options": {
    "check_argument_support": false,
    "generate_proof_pack": false
  }
}
```

**Response:**
```json
{
  "request_id": "uuid",
  "document_id": "string | null",
  "processed_at": "ISO 8601 timestamp",
  "citations_found": 3,
  "processing_time_ms": 143,
  "results": [
    {
      "citation_raw": "576 U.S. 644",
      "citation_normalized": "576 U.S. 644 (2015)",
      "case_name": "Obergefell v. Hodges",
      "exists": true,
      "confidence_score": 0.97,
      "sources_checked": ["courtlistener", "lexisnexis"],
      "found_in": ["courtlistener", "lexisnexis"],
      "argument_support": {
        "score": 0.82,
        "flag": "green",
        "message": "Citation appears to support the stated proposition."
      },
      "audit_id": "sha256:a3f9b2c1...",
      "cached": false
    }
  ],
  "document_audit_hash": "sha256:master_hash_of_all_results",
  "proof_pack_url": null
}
```

**Error responses:**
```json
{ "error": "INVALID_API_KEY", "message": "...", "status": 401 }
{ "error": "RATE_LIMIT_EXCEEDED", "message": "...", "status": 429, "retry_after": 60 }
{ "error": "TEXT_TOO_LONG", "message": "...", "status": 400 }
{ "error": "NO_CITATIONS_FOUND", "message": "...", "status": 200 }
```

### GET /v1/audit/{audit_id}

Retrieve a specific audit record by its hash ID.

### GET /v1/audit/document/{document_id}

Retrieve all audit records for a client's document ID.

### POST /v1/proof-pack/{document_id}

Generate and return a PDF Compliance Proof Pack (Enterprise tier only).

### GET /health

Returns service status, database connectivity, cache status. Used by uptime monitors.

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "cache": "connected",
  "uptime_seconds": 3600
}
```

---

## Data Models

### API Keys Table (PostgreSQL)

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 of the actual key
    client_name VARCHAR(255) NOT NULL,
    client_email VARCHAR(255) NOT NULL,
    tier VARCHAR(20) NOT NULL DEFAULT 'starter',  -- starter | professional | enterprise
    monthly_limit INTEGER NOT NULL DEFAULT 1000,
    requests_this_month INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);
```

### Audit Log Table (PostgreSQL — Append Only)

```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL,
    client_id UUID NOT NULL REFERENCES api_keys(id),
    document_id VARCHAR(500),
    citation_raw TEXT NOT NULL,
    citation_normalized TEXT,
    sources_checked TEXT[] NOT NULL,
    found_in TEXT[],
    exists BOOLEAN NOT NULL,
    confidence_score NUMERIC(5,4),
    argument_flag VARCHAR(10),
    result_json JSONB NOT NULL,
    audit_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Make this table append-only via trigger
CREATE RULE no_update_audit AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE RULE no_delete_audit AS ON DELETE TO audit_log DO INSTEAD NOTHING;

-- Indexes for fast retrieval
CREATE INDEX idx_audit_request ON audit_log(request_id);
CREATE INDEX idx_audit_client ON audit_log(client_id);
CREATE INDEX idx_audit_document ON audit_log(document_id);
CREATE INDEX idx_audit_hash ON audit_log(audit_hash);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);
```

---

## Citation Extraction Logic

Using eyecite. The extraction is deterministic — same text always produces same citations.

Supported citation types (Phase 1):
- Full case citations: `Bush v. Gore, 531 U.S. 98, 99-100 (2000)`
- Short case citations: `531 U.S. 98`
- Statute citations: `42 U.S.C. § 1983` (Phase 2)
- Regulatory citations: `45 C.F.R. § 164.502` (Phase 2)

NOT supported in Phase 1:
- `id.` and `supra` reference citations
- Non-US jurisdictions (MENA added in Phase 3)

---

## Verification Engine Logic

Each citation goes through parallel async verification:

**Phase 1 (MVP) — Sources:**
1. CourtListener (free, US, instant)
2. Justia (free, US Supreme Court + federal circuits)

**Phase 2 — Sources added:**
3. LexisNexis (paid, comprehensive)

**Phase 3 — Sources added:**
4. MENA database connectors (custom)

**Parallel execution:**
```python
results = await asyncio.gather(
    check_courtlistener(citation),
    check_justia(citation),
    return_exceptions=True  # Never let one failure kill others
)
```

**Cache check before verification:**
- Key: `verify:{sha256(normalized_citation)}`
- TTL: 24 hours
- On cache hit: skip verification, still log audit record with `cached: true`

---

## Confidence Scoring Algorithm

```
base_score = confirmed_sources / total_sources_checked

# Bonus for authoritative paid source confirmation
if found in (lexisnexis OR westlaw):
    base_score = min(1.0, base_score + 0.15)

# Penalty for recency risk (case < 30 days old — may not be in all databases yet)
if case_date > (today - 30 days):
    base_score = max(0.0, base_score - 0.10)

# Penalty if jurisdiction not fully covered
if citation.jurisdiction NOT IN covered_jurisdictions:
    base_score = max(0.0, base_score - 0.20)
    flag: "jurisdiction_partial_coverage"

final_score = round(base_score, 4)
```

Score thresholds:
- 0.90–1.00: High confidence — verified
- 0.70–0.89: Medium confidence — review recommended
- 0.50–0.69: Low confidence — manual verification required
- 0.00–0.49: Not verified — citation may not exist

---

## Caching Strategy

Redis cache with two key types:

**Citation cache** (24hr TTL):
```
verify:{sha256(normalized_citation)} → JSON result
```

**Rate limit counter** (60s window):
```
ratelimit:{api_key_hash}:{unix_minute} → integer count
```

**Never cache:**
- Audit log entries (always written fresh)
- API key lookups (security concern)

---

## Authentication

All endpoints except `/health` require an API key.

```
Header: X-API-Key: hcv_live_xxxxxxxxxxxxxxxx
```

Key format: `hcv_{env}_{32_random_chars}`
- env: `live` for production, `test` for sandbox

Storage: Only store SHA-256 hash of the key in the database. Never store plaintext.

**Key validation flow:**
1. Extract key from header
2. SHA-256 hash the incoming key
3. Look up hash in `api_keys` table
4. Check `is_active = true`
5. Check monthly quota not exceeded
6. Update `last_used_at`

---

## Rate Limiting

Per API key, enforced in Redis:

| Tier | Requests/minute | Requests/month |
|---|---|---|
| Starter | 10 | 1,000 |
| Professional | 60 | 10,000 |
| Enterprise | 500 | Unlimited |

Return 429 with `Retry-After` header when exceeded.

---

## Performance Requirements

| Metric | Target |
|---|---|
| Latency (single citation) | < 200ms p95 |
| Latency (50 citations, batch) | < 3s p95 |
| Database write (audit log) | < 20ms |
| Cache read | < 5ms |
| Uptime | 99.9% |

---

## Security Requirements

- All traffic over HTTPS only (enforce in production)
- API keys hashed before storage
- No legal document content stored — only citation strings and metadata
- Audit logs are append-only (enforced at database level)
- Rate limiting prevents abuse
- Input sanitized and length-limited before processing
- `.env` never committed
- Dependency scanning via `pip-audit` before every release