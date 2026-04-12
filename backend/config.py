"""
Application-level configuration.
COMPANY_ID is loaded from the environment and validated against the DB at startup.
Use `get_company_id()` as a FastAPI dependency to inject it into routes.
"""
import os
from fastapi import HTTPException, status

# Set at startup by validate_company_id(); None until then.
COMPANY_ID: str | None = None


async def validate_company_id(db) -> str:
    """
    Read COMPANY_ID from env and confirm it exists in db.companies.
    Called once during app lifespan startup. Raises RuntimeError on failure.
    """
    global COMPANY_ID

    company_id = os.environ.get("COMPANY_ID", "").strip()
    if not company_id:
        raise RuntimeError("COMPANY_ID environment variable is required")

    company = await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1, "name": 1})
    if not company:
        raise RuntimeError(
            f"COMPANY_ID '{company_id}' not found in the companies collection. "
            "Create the company via the super-admin API first."
        )

    COMPANY_ID = company_id
    return company_id


def get_company_id() -> str:
    """
    FastAPI dependency — returns the validated company ID.
    Always succeeds after a successful startup.
    """
    if not COMPANY_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Company ID not initialised — server may still be starting up."
        )
    return COMPANY_ID
