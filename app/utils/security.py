"""
FastAPI Security Module for API Authentication.
Supports X-API-Key header, query param api_key, and X-Admin-Password header.
"""
from fastapi import Security, HTTPException, status, Request
from fastapi.security import APIKeyHeader
from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(request: Request, api_key: str = Security(api_key_header)):
    """Validates incoming requests against X-API-Key header, query param, or X-Admin-Password."""
    query_key = request.query_params.get("api_key")
    admin_pass = request.headers.get("X-Admin-Password")

    provided_key = api_key or query_key

    if provided_key == settings.API_KEY or admin_pass == settings.STAFF_ADMIN_PASSWORD:
        return provided_key or admin_pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing X-API-Key or Staff Admin Password",
    )
