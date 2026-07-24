"""
Chat Share Service
Handles creating, validating, and managing shared chat links
"""

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


class ChatShareService:
    """Service for managing shared chats"""
    
    @staticmethod
    def generate_share_token(length: int = 32) -> str:
        """
        Generate a cryptographically secure URL-safe token
        
        Args:
            length: Length of token in bytes (default 32 = 64 char hex string)
            
        Returns:
            URL-safe token string
        """
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using SHA-256
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password string
        """
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        Verify a password against its hash
        
        Args:
            password: Plain text password to verify
            password_hash: Stored hash to compare against
            
        Returns:
            True if password matches, False otherwise
        """
        return hashlib.sha256(password.encode()).hexdigest() == password_hash
    
    @staticmethod
    def create_share_link(
        db,
        user_id: str,
        collection_id: str,
        share_title: Optional[str] = None,
        password: Optional[str] = None,
        expires_in_days: Optional[int] = None,
        max_views: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a shareable link for a chat collection
        
        Args:
            db: Database session
            user_id: User ID who owns the chat
            collection_id: Collection ID to share
            share_title: Optional custom title for the share
            password: Optional password to protect the share
            expires_in_days: Optional number of days until expiration
            max_views: Optional maximum number of views allowed
            
        Returns:
            Dictionary with share details including token
        """
        try:
            # Verify collection exists and belongs to user
            collection = db.execute(text("""
                SELECT id, collection_name, chat_title
                FROM collections
                WHERE id = :cid AND user_id = :uid
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """), {"cid": collection_id, "uid": user_id}).fetchone()
            
            if not collection:
                raise ValueError("Collection not found or unauthorized")
            
            # Generate unique token
            share_token = ChatShareService.generate_share_token()
            
            # Calculate expiration date
            expires_at = None
            if expires_in_days:
                expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
            
            # Hash password if provided
            password_hash = None
            is_public = True
            if password:
                password_hash = ChatShareService.hash_password(password)
                is_public = False
            
            # Use share_title or fallback to chat_title or collection_name
            final_title = share_title or collection.chat_title or collection.collection_name
            
            # Insert share record
            result = db.execute(text("""
                INSERT INTO shared_chats (
                    user_id,
                    collection_id,
                    share_token,
                    share_title,
                    is_public,
                    access_password_hash,
                    expires_at,
                    max_views
                )
                VALUES (
                    :uid,
                    :cid,
                    :token,
                    :title,
                    :public,
                    :pwd_hash,
                    :expires,
                    :max_views
                )
                RETURNING id, share_token, created_at
            """), {
                "uid": user_id,
                "cid": collection_id,
                "token": share_token,
                "title": final_title,
                "public": is_public,
                "pwd_hash": password_hash,
                "expires": expires_at,
                "max_views": max_views
            }).fetchone()
            
            db.commit()
            
            logger.info(f"Created share link for collection {collection_id}")
            
            return {
                "share_id": str(result.id),
                "share_token": result.share_token,
                "share_title": final_title,
                "is_public": is_public,
                "has_password": password is not None,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "max_views": max_views,
                "created_at": result.created_at.isoformat(),
                "share_url": f"/share/{result.share_token}"  # Frontend will prepend base URL
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating share link: {str(e)}")
            raise
    
    @staticmethod
    def get_shared_chat(
        db,
        share_token: str,
        password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieve a shared chat by token
        
        Args:
            db: Database session
            share_token: Share token from URL
            password: Optional password for protected shares
            
        Returns:
            Dictionary with chat data and metadata
            
        Raises:
            ValueError: If share not found, expired, or password incorrect
        """
        try:
            # Get share record
            share = db.execute(text("""
                SELECT 
                    sc.*,
                    c.collection_name,
                    c.chat_title as collection_chat_title
                FROM shared_chats sc
                JOIN collections c ON sc.collection_id = c.id
                WHERE sc.share_token = :token
                AND sc.is_active = TRUE
                AND (c.is_deleted = FALSE OR c.is_deleted IS NULL)
            """), {"token": share_token}).fetchone()
            
            if not share:
                raise ValueError("Share link not found or has been deactivated")
            
            # Check expiration
            if share.expires_at and datetime.utcnow() > share.expires_at:
                raise ValueError("This share link has expired")
            
            # Check max views
            if share.max_views and share.view_count >= share.max_views:
                raise ValueError("This share link has reached its maximum view limit")
            
            # Check password if required
            if not share.is_public:
                if not password:
                    raise ValueError("This share link is password protected")
                if not ChatShareService.verify_password(password, share.access_password_hash):
                    raise ValueError("Incorrect password")
            
            # Increment view count and update last accessed
            db.execute(text("""
                UPDATE shared_chats
                SET 
                    view_count = view_count + 1,
                    last_accessed_at = CURRENT_TIMESTAMP
                WHERE id = :sid
            """), {"sid": share.id})
            db.commit()
            
            # Get chat history
            messages = db.execute(text("""
                SELECT 
                    query_text,
                    response_text,
                    sources_used,
                    created_at,
                    reference_map
                FROM queries
                WHERE collection_id = :cid
                AND (is_deleted = FALSE OR is_deleted IS NULL)
                ORDER BY created_at ASC
            """), {"cid": share.collection_id}).fetchall()
            
            chat_history = [dict(m._mapping) for m in messages]
            
            logger.info(f"Shared chat accessed: {share_token}, views: {share.view_count + 1}")
            
            return {
                "share_title": share.share_title,
                "collection_name": share.collection_name,
                "messages": chat_history,
                "message_count": len(chat_history),
                "created_at": share.created_at.isoformat(),
                "view_count": share.view_count + 1,
                "is_public": share.is_public
            }
            
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error retrieving shared chat: {str(e)}")
            raise ValueError(f"Error accessing shared chat: {str(e)}")
    
    @staticmethod
    def list_user_shares(db, user_id: str) -> list:
        """
        List all shares created by a user
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            List of share records
        """
        try:
            shares = db.execute(text("""
                SELECT 
                    sc.id,
                    sc.share_token,
                    sc.share_title,
                    sc.is_public,
                    sc.is_active,
                    sc.created_at,
                    sc.last_accessed_at,
                    sc.view_count,
                    sc.max_views,
                    sc.expires_at,
                    c.collection_name
                FROM shared_chats sc
                JOIN collections c ON sc.collection_id = c.id
                WHERE sc.user_id = :uid
                ORDER BY sc.created_at DESC
            """), {"uid": user_id}).fetchall()
            
            return [dict(s._mapping) for s in shares]
            
        except Exception as e:
            logger.error(f"Error listing user shares: {str(e)}")
            raise
    
    @staticmethod
    def deactivate_share(db, share_id: str, user_id: str) -> bool:
        """
        Deactivate a share link
        
        Args:
            db: Database session
            share_id: Share ID to deactivate
            user_id: User ID (for authorization)
            
        Returns:
            True if successful
        """
        try:
            result = db.execute(text("""
                UPDATE shared_chats
                SET is_active = FALSE
                WHERE id = :sid AND user_id = :uid
            """), {"sid": share_id, "uid": user_id})
            
            db.commit()
            
            if result.rowcount == 0:
                raise ValueError("Share not found or unauthorized")
            
            logger.info(f"Deactivated share: {share_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error deactivating share: {str(e)}")
            raise