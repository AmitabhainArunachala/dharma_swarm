"""Truth endpoints for major runtime modules."""

from __future__ import annotations

from fastapi import APIRouter

from api.models import ApiResponse, ModuleTruthOut
from api.module_truth import get_truth_module, list_truth_modules


router = APIRouter(prefix="/api", tags=["modules"])


@router.get("/modules")
async def modules() -> ApiResponse:
    data = [ModuleTruthOut(**module).model_dump() for module in list_truth_modules()]
    return ApiResponse(data=data)


@router.get("/modules/{module_id}")
async def module_detail(module_id: str) -> ApiResponse:
    module = get_truth_module(module_id)
    if module is None:
        return ApiResponse(status="error", error=f"Unknown module: {module_id}")
    return ApiResponse(data=ModuleTruthOut(**module).model_dump())
