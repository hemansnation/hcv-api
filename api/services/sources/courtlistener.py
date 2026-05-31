import logging

import httpx

from api.config import settings

logger = logging.getLogger(__name__)

_COURTLISTENER_URL = f"{settings.courtlistener_base_url}/citation-lookup/"


async def verify_citation_courtlistener(citation_raw: str) -> dict:
    headers = (
        {"Authorization": f"Token {settings.courtlistener_token}"}
        if settings.courtlistener_token
        else {}
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _COURTLISTENER_URL,
                data={"text": citation_raw},
                headers=headers,
            )
            response.raise_for_status()
            clusters = response.json()

            if not clusters:
                return {"source": "courtlistener", "found": False}

            first = clusters[0]
            return {
                "source": "courtlistener",
                "found": True,
                "case_name": first.get("case_name", ""),
                "court": first.get("court", ""),
                "date": first.get("date_filed", ""),
                "url": first.get("absolute_url", ""),
            }

    except httpx.TimeoutException:
        logger.warning("Timeout calling CourtListener for: %r", citation_raw)
        return {"source": "courtlistener", "found": False, "error": "timeout"}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"source": "courtlistener", "found": False}
        logger.error("HTTP %s from CourtListener", e.response.status_code)
        return {
            "source": "courtlistener",
            "found": False,
            "error": f"http_{e.response.status_code}",
        }
    except Exception as e:
        logger.error("Unexpected error calling CourtListener: %s", e)
        return {"source": "courtlistener", "found": False, "error": "unexpected"}
