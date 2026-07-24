import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db
from routers.dependencies import get_current_user

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Feedback"])

# --- The "Universal" Admin Guard ---

def require_admin(current_user=Depends(get_current_user)):
    """
    Extracts role regardless of whether current_user is a Row, Tuple, Dict, or Object.
    """
    role = None

    # 1. Try Mapping (If it's a SQLAlchemy Row with column names)
    if hasattr(current_user, "_mapping"):
        role = current_user._mapping.get("role")
    
    # 2. Try Attribute (If it's a Pydantic model or ORM object)
    if role is None:
        role = getattr(current_user, "role", None)

    # 3. Try Dict (If it's a standard dictionary)
    if role is None and isinstance(current_user, dict):
        role = current_user.get("role")

    # 4. Try Index Fallback (Your logs show: index 0=UUID, index 1=Role, index 2=Email)
    if role is None and (isinstance(current_user, (tuple, list)) or "sqlalchemy.engine.row.Row" in str(type(current_user))):
        try:
            role = current_user[1]
        except (IndexError, TypeError):
            role = None

    # Final Verification
    if not role or str(role).strip().lower() != "admin":
        logger.warning(f"Access Denied. Extracted role: '{role}' from user: {current_user}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return current_user

# --- Routes ---

@router.get("/users")
async def list_all_users(
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    try:
        # Fetching all users with 'User' role
        result = db.execute(text("""
            SELECT id, name, email, created_at, last_login 
            FROM users 
            WHERE role = 'User' 
            ORDER BY created_at DESC
        """))
        
        # .mappings() ensures results are easy to turn into JSON
        users = [dict(row) for row in result.mappings()]

        return {
            "count": len(users),
            "users": users
        }

    except Exception as e:
        logger.error(f"Internal Error in list_all_users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/users/{user_id}/feedback")
async def list_feedback_by_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    try:
        result = db.execute(text("""
            SELECT id, message, screenshot_path, allow_contact, created_at 
            FROM feedback 
            WHERE user_id = :uid 
            ORDER BY created_at DESC
        """), {"uid": user_id})
        
        feedback_list = [dict(row) for row in result.mappings()]

        return {
            "user_id": user_id,
            "count": len(feedback_list),
            "feedback": feedback_list
        }

    except Exception as e:
        logger.error(f"Internal Error in list_feedback_by_user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")