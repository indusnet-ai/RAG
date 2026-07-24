from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import db
from routers.upload import router as upload_router
from routers.youtube import router as youtube_router
from routers.scrape import router as scrape_router
from routers.rag import router as rag_router
from routers.podcast import router as podcast_router
from routers.auth import router as auth
from routers.collection_create import router as collection_create_router
from routers.document_list import router as document_list_router
from routers.document_delete import router as document_delete_router
from routers.chat_history import router as chat_history_router
from routers.get_collection import router as get_collection_router
from routers.chat_stt import router as chat_stt_router
# from routers import document_content
from routers import collection_summary_api
from routers import web_discovery
from routers.feedback import router as feedback_router
#from routers import audio
from routers.admin_feedback import router as admin_feedback_router
from routers.edit_query import router as edit_query_router
from routers.share_chat import router as share_chat_router
from dotenv import load_dotenv
from db import init_db
from fastapi import BackgroundTasks
from routers.dependencies import get_current_user
import time
import os
import logging
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from starlette.responses import Response
from services.metrics import MetricsService, API_REQUESTS, API_LATENCY
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from services.metrics import track_api_error, track_db_connection_failure
from routers.ragas_metrics import router as ragas_router
from routers import drive_upload
import logging

# ============================================
# CONFIGURE LOGGING FIRST (before anything else)
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S,%f'[:-3]  # Format: 2025-11-26 10:16:19,580
)

metrics_service = MetricsService()

# Get logger for API timing
logger = logging.getLogger("api_timing")


# ============================================
# Initialize DB
# ============================================
init_db()  # <-- creates all tables on startup

load_dotenv()

# -------------------------------------
# FastAPI App
# -------------------------------------
app = FastAPI(
    title="RAG Backend API",
    description="Backend for document upload, YouTube transcription, and web scraping.",
    version="1.0.0"
)
uploaded_files_path = "uploaded_files"
if not os.path.exists(uploaded_files_path):
    os.makedirs(uploaded_files_path)
app.mount("/uploaded_files", StaticFiles(directory=uploaded_files_path), name="uploaded_files")

# -------------------------------------
# API Timing Middleware
# -------------------------------------
@app.middleware("http")
async def log_request_response_time(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    path = request.url.path

    # Logging
    logger.info(f"{request.method} {path} | Status {response.status_code} | {process_time * 1000:.2f} ms")

    # ✅ UPDATE THIS - Track metrics
    if path != "/metrics":
        API_REQUESTS.labels(
            method=request.method,
            endpoint=path,
            status=response.status_code
        ).inc()
        
        API_LATENCY.labels(endpoint=path).observe(process_time)

    return response

# ✅ ADD THIS - Startup event
@app.on_event("startup")
async def startup_event():
    """Build metrics on startup"""
    logger.info("🚀 Building Prometheus metrics...")
    try:
        metrics_service.update_all_metrics()
        logger.info("✅ Metrics built successfully")
    except Exception as e:
        logger.error(f"❌ Failed to build metrics: {str(e)}")


# ============================================
# GLOBAL EXCEPTION HANDLERS
# ============================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    
    # Track API errors (4xx and 5xx)
    if exc.status_code >= 400:
        track_api_error(
            endpoint=request.url.path,
            error_type="HTTPException",
            status_code=exc.status_code
        )
    
    logger.warning(
        f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}"
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": request.url.path
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions"""
    
    error_type = type(exc).__name__
    
    # Track database errors specifically
    if "psycopg2" in str(type(exc)) or "database" in str(exc).lower():
        track_db_connection_failure()
    
    # Track general API error
    track_api_error(
        endpoint=request.url.path,
        error_type=error_type,
        status_code=500
    )
    
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}",
        exc_info=True
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "type": error_type,
            "path": request.url.path
        }
    )


# Database-specific exception handler
from sqlalchemy.exc import SQLAlchemyError

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """Handle SQLAlchemy/database exceptions"""
    
    track_db_connection_failure()
    track_api_error(
        endpoint=request.url.path,
        error_type="DatabaseError",
        status_code=500
    )
    
    logger.error(
        f"Database error on {request.method} {request.url.path}: {str(exc)}",
        exc_info=True
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Database operation failed",
            "type": "DatabaseError",
            "path": request.url.path
        }
    )


# CORS (allows local frontend or localhost access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chatbot.automios.com",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175"
    ],  # adjust later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ROUTERS
app.include_router(auth)
app.include_router(collection_create_router, dependencies=[Depends(get_current_user)])
app.include_router(upload_router, dependencies=[Depends(get_current_user)])
app.include_router(youtube_router, dependencies=[Depends(get_current_user)])
#app.include_router(audio.router, dependencies=[Depends(get_current_user)])
app.include_router(scrape_router, dependencies=[Depends(get_current_user)])
# app.include_router(document_content.router, dependencies=[Depends(get_current_user)])
app.include_router(rag_router, dependencies=[Depends(get_current_user)])
app.include_router(podcast_router, dependencies=[Depends(get_current_user)])
app.include_router(document_list_router, dependencies=[Depends(get_current_user)])
app.include_router(document_delete_router, dependencies=[Depends(get_current_user)])
app.include_router(chat_history_router, dependencies=[Depends(get_current_user)])
app.include_router(get_collection_router, dependencies=[Depends(get_current_user)]) 
app.include_router(chat_stt_router, dependencies=[Depends(get_current_user)])
app.include_router(drive_upload.router, dependencies=[Depends(get_current_user)])
app.include_router(collection_summary_api.router, dependencies=[Depends(get_current_user)])
app.include_router(feedback_router, dependencies=[Depends(get_current_user)])
app.include_router(admin_feedback_router, dependencies=[Depends(get_current_user)])

app.include_router(edit_query_router, dependencies=[Depends(get_current_user)])
app.include_router(share_chat_router)
app.include_router(ragas_router, dependencies=[Depends(get_current_user)])  # ✅ ADD THIS
app.include_router(web_discovery.router, dependencies=[Depends(get_current_user)])

@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# ✅ ADD THIS - Manual refresh endpoint
@app.post("/metrics/refresh")
async def refresh_metrics(background_tasks: BackgroundTasks):
    """Manually refresh metrics"""
    background_tasks.add_task(metrics_service.update_all_metrics)
    return {"message": "Metrics refresh triggered"}


@app.get("/")
def root():
    return {"message": "RAG Backend is running successfully 🚀"}