from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import time

from services.latenz import LATENZ_REPORTS_BUFFER, LATENZ_SETTINGS

router = APIRouter(prefix="/latenz", tags=["Latenz Diagnostic Telemetry"])

class LatenzSettingsUpdate(BaseModel):
    auto_remediate: Optional[bool] = None
    max_token_bound: Optional[int] = None
    active_exporter: Optional[str] = None
    telemetry_enabled: Optional[bool] = None

@router.get("/telemetry")
async def get_latenz_telemetry():
    """
    Exposes real-time Latenz telemetry data, metrics summary, and diagnostic reports for Desktop GUI.
    """
    total_requests = len(LATENZ_REPORTS_BUFFER)
    avg_latency = (
        sum(r.get("total_latency_ms", 0) for r in LATENZ_REPORTS_BUFFER) / total_requests
        if total_requests > 0 else 0.0
    )
    total_tokens_saved = sum(r.get("tokens_saved", 0) for r in LATENZ_REPORTS_BUFFER)
    total_duplicates_stripped = sum(r.get("duplicate_chunks_found", 0) for r in LATENZ_REPORTS_BUFFER)
    
    # Calculate average network timing
    avg_ttft = (
        sum(r.get("ttft_ms", 0) for r in LATENZ_REPORTS_BUFFER if r.get("ttft_ms")) / total_requests
        if total_requests > 0 else 0.0
    )

    return {
        "status": "active",
        "timestamp": time.time(),
        "summary": {
            "total_queries_logged": total_requests,
            "avg_latency_ms": round(avg_latency, 2),
            "avg_ttft_ms": round(avg_ttft, 2),
            "total_tokens_saved": total_tokens_saved,
            "total_duplicates_stripped": total_duplicates_stripped
        },
        "settings": LATENZ_SETTINGS,
        "reports": LATENZ_REPORTS_BUFFER[:20]  # Return top 20 latest reports
    }

@router.post("/settings")
async def update_latenz_settings(update: LatenzSettingsUpdate):
    """
    Update live Latenz settings from Desktop GUI.
    """
    if update.auto_remediate is not None:
        LATENZ_SETTINGS["auto_remediate"] = update.auto_remediate
    if update.max_token_bound is not None:
        LATENZ_SETTINGS["max_token_bound"] = update.max_token_bound
    if update.active_exporter is not None:
        LATENZ_SETTINGS["active_exporter"] = update.active_exporter
    if update.telemetry_enabled is not None:
        LATENZ_SETTINGS["telemetry_enabled"] = update.telemetry_enabled

    return {
        "message": "Latenz settings updated successfully",
        "settings": LATENZ_SETTINGS
    }

@router.post("/clear")
async def clear_latenz_telemetry():
    """
    Clear buffered telemetry data.
    """
    LATENZ_REPORTS_BUFFER.clear()
    return {"message": "Telemetry buffer cleared cleanly"}
