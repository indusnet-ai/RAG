from fastapi import APIRouter
from typing import List, Dict, Any
import time

from services.latenz import LATENZ_REPORTS_BUFFER

router = APIRouter(prefix="/latenz", tags=["Latenz Diagnostic Telemetry"])

@router.get("/telemetry")
async def get_latenz_telemetry():
    """
    Exposes real-time Latenz telemetry data for Desktop Dashboard.
    """
    total_requests = len(LATENZ_REPORTS_BUFFER)
    avg_latency = (
        sum(r.get("total_latency_ms", 0) for r in LATENZ_REPORTS_BUFFER) / total_requests
        if total_requests > 0 else 0.0
    )
    total_tokens_saved = sum(r.get("tokens_saved", 0) for r in LATENZ_REPORTS_BUFFER)
    
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
            "total_tokens_saved": total_tokens_saved
        },
        "reports": LATENZ_REPORTS_BUFFER[:20]
    }
