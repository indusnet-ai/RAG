# auth/dependencies.py

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from sqlalchemy import text
from db import get_db
from services.auth_service import JWT_SECRET, JWT_ALGORITHM
import logging

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S,%f'[:-3]  # Format: 2025-11-26 10:16:19,580
)

logger = logging.getLogger(__name__)

security = HTTPBearer()

async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db=Depends(get_db)
):
    token = creds.credentials
    
    try:
        logger.debug("Validating access token")
        
        # Decode and validate token
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id: str = payload.get("sub")

            if user_id is None:
                logger.warning("Token payload missing 'sub' field")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload"
                )
            
            logger.debug(f"Token decoded successfully for user: {user_id}")
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired"
            )
        except jwt.InvalidTokenError as token_error:
            logger.warning(f"Invalid token: {str(token_error)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid access token"
            )

        # Fetch user from database
        try:
            user = db.execute(
                text("""
                    SELECT id, name, email 
                    FROM users 
                    WHERE id = :id 
                    AND (is_deleted = FALSE OR is_deleted IS NULL)
                """),
                {"id": user_id}
            ).fetchone()
        except Exception as db_error:
            logger.error(f"Database error while fetching user {user_id}: {str(db_error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error accessing user data"
            )

        if not user:
            logger.warning(f"User not found in database: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")

        logger.debug(f"User validated successfully: {user.email}")
        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_current_user: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error occurred"
        )