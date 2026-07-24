"""
Prometheus Metrics for RAG Chatbot
Production-Ready Metrics Tracking
"""

from prometheus_client import Counter, Gauge, Histogram, Info
from sqlalchemy import text
from typing import Dict
import psutil
import logging


logger = logging.getLogger(__name__)

# ============================================
# 1. BUSINESS METRICS (Most Important)
# ============================================

# Users
TOTAL_USERS = Gauge('total_users', 'Total registered users')
ACTIVE_USERS = Gauge('active_users', 'Users with active collections')

# Collections
TOTAL_COLLECTIONS = Gauge('total_collections', 'Total collections')
COLLECTIONS_CREATED = Counter('collections_created_total', 'Collections created')
COLLECTIONS_DELETED = Counter('collections_deleted_total', 'Collections deleted')

# Documents
TOTAL_DOCUMENTS = Gauge('total_documents', 'Total documents uploaded')
DOCUMENTS_BY_TYPE = Gauge('documents_by_type', 'Documents by type', ['type'])
DOCUMENTS_UPLOADED = Counter('documents_uploaded_total', 'Documents uploaded', ['type'])
DOCUMENTS_DELETED = Counter('documents_deleted_total', 'Documents deleted')

# Queries
TOTAL_QUERIES = Gauge('total_queries', 'Total queries executed')
QUERIES_EXECUTED = Counter('queries_executed_total', 'Queries executed')
QUERY_EDITS = Counter('query_edits_total', 'Query edits')

# Uploads by Source
UPLOADS_BY_SOURCE = Counter('uploads_by_source_total', 'Uploads by source', ['source'])  # file, youtube, web, text

# Authentication
LOGIN_SUCCESS = Counter('login_success_total', 'Successful logins')
LOGIN_FAILURE = Counter('login_failure_total', 'Failed logins')

REGISTRATION_SUCCESS = Counter('registration_success_total', 'Successful user registrations')
REGISTRATION_FAILURE = Counter('registration_failure_total', 'Failed user registrations')

# ============================================
# 2. API METRICS
# ============================================

API_REQUESTS = Counter('http_requests_total', 'API requests', ['method', 'endpoint', 'status'])
API_LATENCY = Histogram('http_latency_seconds', 'API latency', ['endpoint'])
API_ERRORS = Counter('http_errors_total', 'API errors', ['endpoint', 'status'])

# ============================================
# 3. FEATURE METRICS
# ============================================

# RAG
RAG_QUERY_DURATION = Histogram(
    'rag_query_duration_seconds',
    'RAG query processing time',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# Speech-to-Text
STT_REQUESTS = Counter('stt_requests_total', 'STT requests')
STT_DURATION = Histogram('stt_duration_seconds', 'STT processing time', buckets=[0.5, 1.0, 2.0, 5.0])
STT_FAILURES = Counter('stt_failures_total', 'STT failures')

# Podcast
PODCAST_REQUESTS = Counter('podcast_requests_total', 'Podcast generation requests')
PODCAST_DURATION = Histogram('podcast_duration_seconds', 'Podcast generation time', buckets=[30, 60, 120, 300, 600])
PODCAST_FAILURES = Counter('podcast_failures_total', 'Podcast failures')

# Share
SHARES_CREATED = Counter('shares_created_total', 'Share links created')
SHARE_VIEWS = Counter('share_views_total', 'Share views', ['status'])  # success, password_fail, expired
PDF_EXPORTS = Counter('pdf_exports_total', 'PDF exports', ['type'])  # own, shared

# ============================================
# 4. SYSTEM METRICS
# ============================================

CPU_USAGE = Gauge('cpu_usage_percent', 'CPU usage percentage')
MEMORY_USAGE = Gauge('memory_usage_percent', 'Memory usage percentage')
MEMORY_BYTES = Gauge('memory_usage_bytes', 'Memory usage in bytes')
DISK_USAGE = Gauge('disk_usage_percent', 'Disk usage percentage')

# ============================================
# 5. DATABASE METRICS
# ============================================

DB_CONNECTIONS_ACTIVE = Gauge('db_connections_active', 'Active DB connections')
DB_QUERY_DURATION = Histogram('db_query_duration_seconds', 'DB query time', buckets=[0.01, 0.05, 0.1, 0.5, 1.0])
DB_ERRORS = Counter('db_errors_total', 'Database errors')

# ============================================
# 6. ERROR TRACKING
# ============================================

TOTAL_ERRORS = Counter('errors_total', 'Total errors', ['type', 'endpoint'])
UPLOAD_FAILURES = Counter('upload_failures_total', 'Upload failures', ['type', 'reason'])

# ============================================
# 7. STORAGE METRICS
# ============================================

TOTAL_CHUNKS = Gauge('chunks_total', 'Total chunks in vector store')
EMBEDDINGS_GENERATED = Counter('embeddings_generated_total', 'Embeddings generated')
# ============================================
# MISSING BUSINESS METRICS
# ============================================

# Text Paste
TEXT_PASTE_TOTAL = Counter('text_paste_total', 'Text pasted via paste endpoint')

# Document Operations
DOCUMENTS_RESTORED = Counter('documents_restored_total', 'Documents restored')

# Share Operations
SHARES_DEACTIVATED = Counter('shares_deactivated_total', 'Share links deactivated')
SHARE_LIST_REQUESTS = Counter('share_list_requests_total', 'Requests to list shares')

# Collection Operations
COLLECTION_LIST_REQUESTS = Counter('collection_list_requests_total', 'Requests to list collections')

# Document Listing
DOCUMENT_LIST_REQUESTS = Counter('document_list_requests_total', 'Requests to list documents')

# Chat History
CHAT_HISTORY_REQUESTS = Counter('chat_history_requests_total', 'Chat history retrieval requests')

# Web Crawl Types
WEB_CRAWL_REQUESTS = Counter('web_crawl_requests_total', 'Web crawl requests', ['crawl_type'])

# Authentication Extended
TOKEN_REFRESH_TOTAL = Counter('token_refresh_total', 'Token refresh requests')
TOKEN_REFRESH_FAILURES = Counter('token_refresh_failures_total', 'Token refresh failures')
LOGOUT_TOTAL = Counter('logout_total', 'User logouts')


# Add these new metrics
RAGAS_FAITHFULNESS = Gauge('ragas_faithfulness', 'Average faithfulness score (0-1)')
RAGAS_ANSWER_RELEVANCY = Gauge('ragas_answer_relevancy', 'Average answer relevancy (0-1)')
RAGAS_CONTEXT_PRECISION = Gauge('ragas_context_precision', 'Average context precision (0-1)')
RAGAS_CONTEXT_RECALL = Gauge('ragas_context_recall', 'Average context recall (0-1)')
RAGAS_EVALUATIONS_TOTAL = Counter('ragas_evaluations_total', 'Total RAGAs evaluations run')
RAGAS_EVAL_DURATION = Histogram('ragas_eval_duration_seconds', 'RAGAs evaluation duration')


# ============================================
# MISSING PERFORMANCE METRICS
# ============================================

# Upload Processing Time
UPLOAD_DURATION = Histogram(
    'upload_processing_duration_seconds',
    'Upload processing time by type',
    ['upload_type'],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

# Embedding Generation Time
EMBEDDING_DURATION = Histogram(
    'embedding_generation_duration_seconds',
    'Embedding generation time',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# PDF Export Duration
PDF_EXPORT_DURATION = Histogram(
    'pdf_export_duration_seconds',
    'PDF export time',
    ['export_type'],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0]
)

# ============================================
# MISSING ERROR TRACKING
# ============================================

# API Errors Detailed
API_ERRORS_BY_TYPE = Counter(
    'http_errors_by_type_total',
    'API errors by type',
    ['endpoint', 'error_type', 'status_code']
)

# Database Connection Failures
DB_CONNECTION_FAILURES = Counter('db_connection_failures_total', 'Database connection failures')

# External Service Failures
EXTERNAL_SERVICE_FAILURES = Counter(
    'external_service_failures_total',
    'External service failures',
    ['service']  # openai, sarvam, youtube_api
)

# ============================================
# MISSING DATA QUALITY METRICS
# ============================================

# Chunks per Document
AVG_CHUNKS_PER_DOCUMENT = Gauge(
    'avg_chunks_per_document',
    'Average chunks per document',
    ['doc_type']
)

# Sources per Query
SOURCES_PER_QUERY = Histogram(
    'sources_per_query',
    'Number of sources retrieved per query',
    buckets=[1, 3, 5, 10, 20, 50]
)

# Query Length Categories
QUERY_DURATION_BY_LENGTH = Histogram(
    'query_duration_by_length_seconds',
    'Query duration by query length category',
    ['query_length_bucket'],  # short, medium, long
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0]
)

# ============================================
# MISSING USER BEHAVIOR METRICS
# ============================================

# Active Sessions
ACTIVE_SESSIONS = Gauge('active_sessions', 'Currently active user sessions')

# Queries per User
QUERIES_PER_USER = Gauge('queries_per_user', 'Queries per user', ['user_name'])

# ============================================
# MISSING STORAGE METRICS
# ============================================

# Collection Size Distribution
COLLECTION_SIZE_DOCS = Histogram(
    'collection_size_documents',
    'Number of documents per collection',
    buckets=[1, 5, 10, 25, 50, 100, 200]
)

# ============================================
# APP INFO
# ============================================

APP_INFO = Info('app_info', 'Application information')
APP_INFO.info({
    'version': '1.0.0',
    'name': 'RAG Chatbot',
    'environment': 'production'
})

# ============================================
# METRICS SERVICE
# ============================================

class MetricsService:
    """Service to update metrics from database"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def update_all_metrics(self):  # ← KEEP ONLY THIS ONE
        """Update all gauge metrics from database"""
        try:
            from db import get_db
            db = next(get_db())
            
            self._update_business_metrics(db)
            self._update_system_metrics()
            self._update_data_quality_metrics(db)  # ✅ This is the complete version
            
            self.logger.info("✅ Metrics updated successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Error updating metrics: {str(e)}")
    
    def _update_business_metrics(self, db):
        """Update business metrics from database"""
        try:
            # Users
            users = db.execute(text("SELECT COUNT(*) FROM users WHERE is_deleted = FALSE OR is_deleted IS NULL")).scalar()
            TOTAL_USERS.set(users or 0)
            
            active = db.execute(text("SELECT COUNT(DISTINCT user_id) FROM collections WHERE is_deleted = FALSE OR is_deleted IS NULL")).scalar()
            ACTIVE_USERS.set(active or 0)
            
            # Collections
            collections = db.execute(text("SELECT COUNT(*) FROM collections WHERE is_deleted = FALSE OR is_deleted IS NULL")).scalar()
            TOTAL_COLLECTIONS.set(collections or 0)
            
            # Documents
            docs = db.execute(text("SELECT COUNT(*) FROM documents WHERE is_deleted = FALSE OR is_deleted IS NULL")).scalar()
            TOTAL_DOCUMENTS.set(docs or 0)
            
            # Documents by type
            doc_types = db.execute(text("""
                SELECT file_type, COUNT(*) as count
                FROM documents
                WHERE is_deleted = FALSE OR is_deleted IS NULL
                GROUP BY file_type
            """)).fetchall()
            
            for row in doc_types:
                DOCUMENTS_BY_TYPE.labels(type=row.file_type or 'unknown').set(row.count)
            
            # Queries
            queries = db.execute(text("SELECT COUNT(*) FROM queries WHERE is_deleted = FALSE OR is_deleted IS NULL")).scalar()
            TOTAL_QUERIES.set(queries or 0)
            
            # Chunks
            chunks = db.execute(text("SELECT COUNT(*) FROM chunks WHERE is_deleted = FALSE OR is_deleted IS NULL")).scalar()
            TOTAL_CHUNKS.set(chunks or 0)
            
            self.logger.info(f"📊 Business: Users={users}, Collections={collections}, Docs={docs}, Queries={queries}")
            
        except Exception as e:
            self.logger.error(f"Error updating business metrics: {str(e)}")
    
    def _update_system_metrics(self):
        """Update system resource metrics"""
        try:
            CPU_USAGE.set(psutil.cpu_percent(interval=1))
            
            memory = psutil.virtual_memory()
            MEMORY_USAGE.set(memory.percent)
            MEMORY_BYTES.set(memory.used)
            
            disk = psutil.disk_usage('/')
            DISK_USAGE.set(disk.percent)
            
        except Exception as e:
            self.logger.error(f"Error updating system metrics: {str(e)}")


    # ADD THIS METHOD to MetricsService class (after _update_storage_metrics)
    def _update_data_quality_metrics(self, db):
        """Update data quality metrics"""
        try:
            # Average chunks per document by type
            chunk_stats = db.execute(text("""
                SELECT d.file_type, AVG(d.chunk_count) as avg_chunks
                FROM documents d
                WHERE d.is_deleted = FALSE OR d.is_deleted IS NULL
                GROUP BY d.file_type
            """)).fetchall()
            
            for row in chunk_stats:
                if row.file_type and row.avg_chunks:
                    AVG_CHUNKS_PER_DOCUMENT.labels(doc_type=row.file_type).set(row.avg_chunks)
            
            # Queries per user
            query_stats = db.execute(text("""
                SELECT u.name, COUNT(q.id) as query_count
                FROM users u
                LEFT JOIN queries q ON u.id = q.user_id
                    AND (q.is_deleted = FALSE OR q.is_deleted IS NULL)
                WHERE u.is_deleted = FALSE OR u.is_deleted IS NULL
                GROUP BY u.id, u.name
            """)).fetchall()
            
            for row in query_stats:
                QUERIES_PER_USER.labels(user_name=row.name).set(row.query_count)
            
            self.logger.info(f"📊 Data quality metrics updated")
            
        except Exception as e:
            self.logger.error(f"Error updating data quality metrics: {str(e)}")

# ADD THIS to update_all_metrics method (after _update_storage_metrics)
    def update_all_metrics(self):
        """Update all gauge metrics from database"""
        try:
            from db import get_db
            db = next(get_db())
            
            self._update_business_metrics(db)
            self._update_system_metrics()
            
            self._update_data_quality_metrics(db)  # ✅ ADD THIS LINE
            
            self.logger.info("✅ Metrics updated successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Error updating metrics: {str(e)}")

# Helper functions
def track_ragas_metrics(scores: Dict[str, float]):
    """Update Prometheus with latest RAGAs scores"""
    if scores.get('faithfulness') is not None:
        RAGAS_FAITHFULNESS.set(scores['faithfulness'])
    if scores.get('answer_relevancy') is not None:
        RAGAS_ANSWER_RELEVANCY.set(scores['answer_relevancy'])
    if scores.get('context_precision') is not None:
        RAGAS_CONTEXT_PRECISION.set(scores['context_precision'])
    if scores.get('context_recall') is not None:
        RAGAS_CONTEXT_RECALL.set(scores['context_recall'])
    RAGAS_EVALUATIONS_TOTAL.inc()

def track_ragas_duration(duration: float):
    """Track RAGAs evaluation duration"""
    RAGAS_EVAL_DURATION.observe(duration)

# ============================================
# TRACKING FUNCTIONS - ADD TO EXISTING ONES
# ============================================

# Text Paste
def track_text_paste():
    TEXT_PASTE_TOTAL.inc()

# Document Restore
def track_document_restore():
    DOCUMENTS_RESTORED.inc()

# Share Operations
def track_share_deactivated():
    SHARES_DEACTIVATED.inc()

def track_share_list_request():
    SHARE_LIST_REQUESTS.inc()

# Collection Operations
def track_collection_list_request():
    COLLECTION_LIST_REQUESTS.inc()

# Document Listing
def track_document_list_request():
    DOCUMENT_LIST_REQUESTS.inc()

# Chat History
def track_chat_history_request():
    CHAT_HISTORY_REQUESTS.inc()

# Web Crawl
def track_web_crawl(crawl_type: str):  # scrape, crawl, recursive
    WEB_CRAWL_REQUESTS.labels(crawl_type=crawl_type).inc()

# Authentication
def track_token_refresh():
    TOKEN_REFRESH_TOTAL.inc()

def track_token_refresh_failure():
    TOKEN_REFRESH_FAILURES.inc()

def track_logout():
    LOGOUT_TOTAL.inc()

# Performance - Upload Duration
def track_upload_duration(upload_type: str, duration: float):
    UPLOAD_DURATION.labels(upload_type=upload_type).observe(duration)

# Performance - Embedding Duration
def track_embedding_duration(duration: float):
    EMBEDDING_DURATION.observe(duration)

# Performance - PDF Export Duration
def track_pdf_export_duration(export_type: str, duration: float):
    PDF_EXPORT_DURATION.labels(export_type=export_type).observe(duration)

# Errors
def track_api_error(endpoint: str, error_type: str, status_code: int):
    API_ERRORS_BY_TYPE.labels(
        endpoint=endpoint,
        error_type=error_type,
        status_code=str(status_code)
    ).inc()

def track_db_connection_failure():
    DB_CONNECTION_FAILURES.inc()

def track_external_service_failure(service: str):
    EXTERNAL_SERVICE_FAILURES.labels(service=service).inc()

# Data Quality
def track_sources_count(count: int):
    SOURCES_PER_QUERY.observe(count)

def track_query_duration_by_length(query_length: int, duration: float):
    if query_length < 50:
        bucket = "short"
    elif query_length < 200:
        bucket = "medium"
    else:
        bucket = "long"
    QUERY_DURATION_BY_LENGTH.labels(query_length_bucket=bucket).observe(duration)

def track_collection_size(doc_count: int):
    COLLECTION_SIZE_DOCS.observe(doc_count)

# ============================================
# TRACKING FUNCTIONS (Use these in routers)
# ============================================

# Authentication
def track_login_success():
    LOGIN_SUCCESS.inc()

def track_login_failure():
    LOGIN_FAILURE.inc()
    

# Authentication
def track_login_success():
    LOGIN_SUCCESS.inc()

def track_login_failure():
    LOGIN_FAILURE.inc()

# ✅ ADD THESE TWO FUNCTIONS:
def track_registration_success():
    """Track successful user registration"""
    REGISTRATION_SUCCESS.inc()

def track_registration_failure():
    """Track failed user registration"""
    REGISTRATION_FAILURE.inc()

# Collections
def track_collection_created():
    COLLECTIONS_CREATED.inc()

def track_collection_deleted():
    COLLECTIONS_DELETED.inc()

# Documents
def track_document_upload(doc_type: str):
    DOCUMENTS_UPLOADED.labels(type=doc_type).inc()
    UPLOADS_BY_SOURCE.labels(source=doc_type).inc()

def track_document_deleted():
    DOCUMENTS_DELETED.inc()

# Queries
def track_query_executed():
    QUERIES_EXECUTED.inc()

def track_query_edit():
    QUERY_EDITS.inc()

def track_rag_duration(duration: float):
    RAG_QUERY_DURATION.observe(duration)

# STT
def track_stt_request(duration: float):
    STT_REQUESTS.inc()
    STT_DURATION.observe(duration)

def track_stt_failure():
    STT_FAILURES.inc()

# Podcast
def track_podcast_request():
    PODCAST_REQUESTS.inc()

def track_podcast_duration(duration: float):
    PODCAST_DURATION.observe(duration)

def track_podcast_failure():
    PODCAST_FAILURES.inc()

# Share
def track_share_created():
    SHARES_CREATED.inc()

def track_share_view(status: str):  # success, password_fail, expired
    SHARE_VIEWS.labels(status=status).inc()

def track_pdf_export(export_type: str):  # own, shared
    PDF_EXPORTS.labels(type=export_type).inc()

# Errors
def track_error(error_type: str, endpoint: str):
    TOTAL_ERRORS.labels(type=error_type, endpoint=endpoint).inc()

def track_upload_failure(upload_type: str, reason: str):
    UPLOAD_FAILURES.labels(type=upload_type, reason=reason).inc()

def track_db_error():
    DB_ERRORS.inc()

# Embeddings
def track_embeddings_generated(count: int):
    EMBEDDINGS_GENERATED.inc(count)