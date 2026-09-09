"""Phase 4 API: trained-model status and guarded image inference."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from ai.detection.preprocessing import ImagePreprocessingError
from ai.detection.service import (
    ModelDependencyError,
    ModelNotTrainedError,
    get_detection_service,
)
from ai.intensity.service import get_intensity_service
from app.config import get_settings


router = APIRouter(prefix="/api/ai", tags=["ai detection"])
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class DetectionStatusResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    model_version: str | None = None
    architecture: str | None = None
    dataset_version: str | None = None
    reason: str | None = None


class DetectionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    prediction: str | None = None
    confidence: float | None = None
    cyclone_probability: float | None = None
    no_cyclone_probability: float | None = None
    model_version: str | None = None
    architecture: str | None = None
    dataset_version: str | None = None
    inference_timestamp_utc: datetime | None = None
    observation_id: str | None = None
    source: str | None = None
    reason: str | None = None


class IntensityStatusResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    dataset_status: str
    model_version: str | None = None
    architecture: str | None = None
    dataset_version: str | None = None
    reason: str | None = None


class IntensityResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    category: str | None = None
    confidence: float | None = None
    class_probabilities: dict[str, float] | None = None
    wind_speed_kmh: float | None = None
    central_pressure_hpa: float | None = None
    model_version: str | None = None
    architecture: str | None = None
    dataset_version: str | None = None
    inference_timestamp_utc: datetime | None = None
    observation_id: str | None = None
    source: str | None = None
    reason: str | None = None


@router.get("/detection/status", response_model=DetectionStatusResponse)
async def detection_status() -> DetectionStatusResponse:
    """Report detector readiness without fabricating a prediction."""
    return DetectionStatusResponse(**get_detection_service().status().__dict__)


@router.post("/detection", response_model=DetectionResponse)
async def detect_cyclone(
    request: Request,
    source: str = Query(..., min_length=1, max_length=128),
    observation_id: str | None = Query(None, max_length=128),
) -> DetectionResponse | JSONResponse:
    """Run a real checkpoint on a supplied image byte stream.

    The endpoint accepts only raw JPEG, PNG, or WebP bytes. It deliberately
    does not accept arbitrary local paths or persist uploads.
    """
    service = get_detection_service()
    readiness = service.status()
    if readiness.status != "READY":
        return JSONResponse(
            status_code=503,
            content=DetectionResponse(**readiness.__dict__).model_dump(mode="json"),
        )

    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG, and WebP images are accepted.")

    max_bytes = get_settings().ai_max_image_mb * 1024 * 1024
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the configured upload size limit.")
    image_bytes = await request.body()
    if len(image_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the configured upload size limit.")

    try:
        result = service.predict_image(image_bytes, source=source, observation_id=observation_id)
    except ImagePreprocessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelNotTrainedError as exc:
        return JSONResponse(
            status_code=503,
            content=DetectionResponse(status="MODEL_NOT_TRAINED", reason=str(exc)).model_dump(mode="json"),
        )
    except ModelDependencyError as exc:
        return JSONResponse(
            status_code=503,
            content=DetectionResponse(status="DEPENDENCY_UNAVAILABLE", reason=str(exc)).model_dump(mode="json"),
        )

    return DetectionResponse(**result.__dict__)


@router.get("/intensity/status", response_model=IntensityStatusResponse)
async def intensity_status() -> IntensityStatusResponse:
    """Report intensity-model readiness and dataset availability without inference."""
    return IntensityStatusResponse(**get_intensity_service().status().__dict__)


@router.post("/intensity", response_model=IntensityResponse)
async def estimate_intensity(
    request: Request,
    source: str = Query(..., min_length=1, max_length=128),
    observation_id: str | None = Query(None, max_length=128),
) -> IntensityResponse | JSONResponse:
    """Run a trained intensity checkpoint against raw validated image bytes."""
    service = get_intensity_service()
    readiness = service.status()
    if readiness.status != "READY":
        return JSONResponse(
            status_code=503,
            content=IntensityResponse(
                status=readiness.status,
                reason=readiness.reason,
            ).model_dump(mode="json"),
        )

    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG, and WebP images are accepted.")
    max_bytes = get_settings().ai_max_image_mb * 1024 * 1024
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the configured upload size limit.")
    image_bytes = await request.body()
    if len(image_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the configured upload size limit.")
    try:
        result = service.predict_image(image_bytes, source=source, observation_id=observation_id)
    except ImagePreprocessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelNotTrainedError as exc:
        return JSONResponse(status_code=503, content=IntensityResponse(status="MODEL_NOT_TRAINED", reason=str(exc)).model_dump(mode="json"))
    except ModelDependencyError as exc:
        return JSONResponse(status_code=503, content=IntensityResponse(status="DEPENDENCY_UNAVAILABLE", reason=str(exc)).model_dump(mode="json"))
    except Exception:
        return JSONResponse(
            status_code=500,
            content=IntensityResponse(status="INFERENCE_ERROR", reason="Intensity inference failed.").model_dump(mode="json"),
        )
    return IntensityResponse(**result.__dict__)
