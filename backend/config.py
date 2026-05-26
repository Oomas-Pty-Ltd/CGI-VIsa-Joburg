"""
Application-level configuration.

``COMPANY_ID`` is the default-tenant env var, loaded and validated against
``db.companies`` at startup by ``validate_company_id``. Use
``tenant.get_tenant_id`` (header-aware, validates each request) as the
FastAPI dependency in route handlers. ``COMPANY_ID`` is only the fallback
when no ``X-Company-Id`` header is supplied (single-tenant deployments,
internal services, and webhook helpers that resolve the tenant from the
inbound channel and fall back to default when channel resolution fails).
"""
import os

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
