from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.health import HealthResponse


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        environment=settings.environment,
    )
