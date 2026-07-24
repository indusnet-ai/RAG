"""
Chat Share Router
API endpoints for sharing chats via link or PDF export
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy import text
from db import get_db
from routers.dependencies import get_current_user
from services.share_service import ChatShareService
from services.pdf_generator import ChatPDFGenerator
from datetime import datetime
import logging
import json
from services.metrics import (
    track_share_created, track_share_view, track_pdf_export,
    track_share_deactivated, track_share_list_request,  # ✅ ADD THESE
    track_pdf_export_duration  # ✅ ADD THIS
)
import time
logger = logging.getLogger(__name__)

import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")


router = APIRouter(prefix="/api/share", tags=["Chat Sharing"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class CreateShareRequest(BaseModel):
    """Request model for creating a share link"""
    collection_name: str = Field(..., description="Collection name to share")
    share_title: Optional[str] = Field(None, description="Custom title for the share")
    password: Optional[str] = Field(None, description="Optional password protection")
    expires_in_days: Optional[int] = Field(None, ge=10, le=365, description="Days until expiration (1-365)")
    max_views: Optional[int] = Field(None, ge=10, description="Maximum number of views allowed")


class CreateShareResponse(BaseModel):
    """Response model for share creation"""
    share_id: str
    share_token: str
    share_url: str
    share_title: str
    is_public: bool
    has_password: bool
    expires_at: Optional[str]
    max_views: Optional[int]
    created_at: str
    copy_link_text: str  # Ready-to-copy full URL


class AccessSharedChatRequest(BaseModel):
    """Request model for accessing password-protected shares"""
    password: Optional[str] = Field(None, description="Password for protected shares")


# ============================================================================
# SHARE LINK ENDPOINTS
# ============================================================================

@router.post("/create", response_model=CreateShareResponse)
async def create_share_link(
    request: CreateShareRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Create a shareable link for a chat collection
    
    - **collection_name**: Name of the collection to share
    - **share_title**: Optional custom title (defaults to chat title)
    - **password**: Optional password for access control
    - **expires_in_days**: Optional expiration (1-365 days)
    - **max_views**: Optional view limit
    
    Returns a shareable URL and token
    """
    try:
        user_id = str(current_user.id)
        
        # Get collection ID
        collection = db.execute(text("""
            SELECT id, collection_name, chat_title
            FROM collections
            WHERE collection_name = :cname AND user_id = :uid
            AND (is_deleted = FALSE OR is_deleted IS NULL)
        """), {"cname": request.collection_name, "uid": user_id}).fetchone()
        
        if not collection:
            raise HTTPException(404, "Collection not found")
        
        # Create share link
        share_data = ChatShareService.create_share_link(
            db=db,
            user_id=user_id,
            collection_id=str(collection.id),
            share_title=request.share_title,
            password=request.password,
            expires_in_days=request.expires_in_days,
            max_views=request.max_views
        )
        track_share_created()
        
        # ✅ UPDATE: Generate full URLs for both
        full_url = f"{BASE_URL}/share/{share_data['share_token']}"
        share_data['share_url'] = full_url  # ✅ ADD THIS LINE

        logger.info(f"Created share link for collection: {request.collection_name}")
        
        return CreateShareResponse(
            **share_data,
            copy_link_text=full_url
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating share link: {str(e)}")
        raise HTTPException(500, f"Error creating share link: {str(e)}")


@router.get("/view/{share_token}")
async def view_shared_chat(
    share_token: str,
    password: Optional[str] = Query(None, description="Password for protected shares"),
    db=Depends(get_db)
):
    """
    View a shared chat (PUBLIC ENDPOINT - No authentication required)
    
    - **share_token**: Unique token from share URL
    - **password**: Optional password for protected shares
    
    Returns complete chat history
    """
    try:
        # Get shared chat data
        chat_data = ChatShareService.get_shared_chat(
            db=db,
            share_token=share_token,
            password=password
        )
        track_share_view("success")
        logger.info(f"Shared chat accessed: {share_token}")
        
        return {
            "status": "success",
            **chat_data
        }
        
    except ValueError as e:
        # These are expected errors (wrong password, expired, etc.)
        # ✅ ADD THESE LINES
        if "password" in str(e).lower():
            track_share_view("password_fail")
        elif "expired" in str(e).lower():
            track_share_view("expired")
        else:
            track_share_view("not_found")
        raise HTTPException(403, str(e))
    except Exception as e:
        logger.error(f"Error viewing shared chat: {str(e)}")
        raise HTTPException(500, f"Error accessing shared chat: {str(e)}")


@router.get("/list")
async def list_my_shares(
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    List all share links created by the current user
    
    Returns list of shares with metadata
    """
    track_share_list_request()
    try:
        user_id = str(current_user.id)
        
        shares = ChatShareService.list_user_shares(db, user_id)
        
        # Enrich with full URLs
        
        for share in shares:
            share['share_url'] = f"{BASE_URL}/share/{share['share_token']}"
            share['is_expired'] = (
                share['expires_at'] and 
                datetime.fromisoformat(str(share['expires_at'])) < datetime.utcnow()
            ) if share.get('expires_at') else False
            share['is_view_limited'] = (
                share['max_views'] and 
                share['view_count'] >= share['max_views']
            ) if share.get('max_views') else False
        
        logger.info(f"Listed {len(shares)} shares for user {user_id}")
        
        return {
            "status": "success",
            "shares": shares,
            "total": len(shares)
        }
        
    except Exception as e:
        logger.error(f"Error listing shares: {str(e)}")
        raise HTTPException(500, f"Error listing shares: {str(e)}")


@router.delete("/deactivate/{share_id}")
async def deactivate_share(
    share_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Deactivate (disable) a share link
    
    - **share_id**: ID of the share to deactivate
    
    The link will no longer be accessible but record is preserved
    """
    try:
        user_id = str(current_user.id)
        
        ChatShareService.deactivate_share(db, share_id, user_id)
        track_share_deactivated()
        
        logger.info(f"Deactivated share: {share_id}")
        
        return {
            "status": "success",
            "message": "Share link deactivated successfully"
        }
        
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error(f"Error deactivating share: {str(e)}")
        raise HTTPException(500, f"Error deactivating share: {str(e)}")


# ============================================================================
# PDF EXPORT ENDPOINTS
# ============================================================================

@router.get("/pdf/{collection_name}")
async def export_chat_as_pdf(
    collection_name: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Export user's own chat as PDF (requires authentication)
    
    - **collection_name**: Collection name to export
    
    Returns PDF file for download
    """
    pdf_start_time = time.time()
    try:
        user_id = str(current_user.id)
        
        # Get collection
        collection = db.execute(text("""
            SELECT id, collection_name, chat_title
            FROM collections
            WHERE collection_name = :cname AND user_id = :uid
            AND (is_deleted = FALSE OR is_deleted IS NULL)
        """), {"cname": collection_name, "uid": user_id}).fetchone()
        
        if not collection:
            raise HTTPException(404, "Collection not found")
        
        # Get chat history
        messages = db.execute(text("""
            SELECT 
                query_text,
                response_text,
                sources_used,
                created_at,
                reference_map
            FROM queries
            WHERE collection_id = :cid AND user_id = :uid
            AND (is_deleted = FALSE OR is_deleted IS NULL)
            ORDER BY created_at ASC
        """), {"cid": collection.id, "uid": user_id}).fetchall()
        
        chat_history = [dict(m._mapping) for m in messages]
        
        if not chat_history:
            raise HTTPException(404, "No messages found in this chat")
        
        # Generate PDF
        pdf_generator = ChatPDFGenerator()
        pdf_buffer = pdf_generator.generate_pdf(
            chat_title=collection.chat_title or collection_name,
            messages=chat_history,
            metadata={'message_count': len(chat_history)}
        )
        track_pdf_export("own")
        track_pdf_export_duration("own", time.time() - pdf_start_time)
        # Generate filename
        safe_filename = collection_name.replace(' ', '_').replace('/', '_')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"chat_{safe_filename}_{timestamp}.pdf"
        
        logger.info(f"Generated PDF for collection: {collection_name}")
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        raise HTTPException(500, f"Error generating PDF: {str(e)}")


@router.get("/pdf/shared/{share_token}")
async def export_shared_chat_as_pdf(
    share_token: str,
    password: Optional[str] = Query(None, description="Password for protected shares"),
    db=Depends(get_db)
):
    """
    Export shared chat as PDF (PUBLIC ENDPOINT - No authentication required)
    
    - **share_token**: Unique token from share URL
    - **password**: Optional password for protected shares
    
    Returns PDF file for download
    """
    pdf_start_time = time.time()
    try:
        # Get shared chat data
        chat_data = ChatShareService.get_shared_chat(
            db=db,
            share_token=share_token,
            password=password
        )
        
        if not chat_data.get('messages'):
            raise HTTPException(404, "No messages found in this shared chat")
        
        # Generate PDF
        pdf_generator = ChatPDFGenerator()
        pdf_buffer = pdf_generator.generate_pdf_from_shared_chat(chat_data)
        track_pdf_export("shared")  # ✅ ADD THIS LINE
        track_pdf_export_duration("shared", time.time() - pdf_start_time)  # ✅ ADD THIS
        # Generate filename
        safe_title = chat_data['share_title'].replace(' ', '_').replace('/', '_')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"shared_chat_{safe_title}_{timestamp}.pdf"
        
        logger.info(f"Generated PDF for shared chat: {share_token}")
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except ValueError as e:
        raise HTTPException(403, str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating PDF for shared chat: {str(e)}")
        raise HTTPException(500, f"Error generating PDF: {str(e)}")


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@router.get("/check/{share_token}")
async def check_share_status(
    share_token: str,
    db=Depends(get_db)
):
    """
    Check if a share link is valid and get basic info (PUBLIC ENDPOINT)
    
    - **share_token**: Token to check
    
    Returns status without requiring password or incrementing view count
    """
    try:
        share = db.execute(text("""
            SELECT 
                is_active,
                is_public,
                expires_at,
                max_views,
                view_count,
                share_title
            FROM shared_chats
            WHERE share_token = :token
        """), {"token": share_token}).fetchone()
        
        if not share:
            return {
                "valid": False,
                "reason": "Share link not found"
            }
        
        if not share.is_active:
            return {
                "valid": False,
                "reason": "Share link has been deactivated"
            }
        
        if share.expires_at and datetime.utcnow() > share.expires_at:
            return {
                "valid": False,
                "reason": "Share link has expired"
            }
        
        if share.max_views and share.view_count >= share.max_views:
            return {
                "valid": False,
                "reason": "Share link has reached maximum views"
            }
        
        return {
            "valid": True,
            "requires_password": not share.is_public,
            "share_title": share.share_title,
            "views_remaining": (share.max_views - share.view_count) if share.max_views else None
        }
        
    except Exception as e:
        logger.error(f"Error checking share status: {str(e)}")
        raise HTTPException(500, f"Error checking share: {str(e)}")