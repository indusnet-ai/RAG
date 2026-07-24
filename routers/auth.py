# routers/auth.py
 
from fastapi import APIRouter, HTTPException, status, Depends, Response, Cookie
from pydantic import BaseModel,validator
import re
import jwt
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from services.auth_service import AuthService
from db import get_db
from services.metrics import (
    track_login_success, track_login_failure,
    track_token_refresh, track_token_refresh_failure, track_logout,  # ✅ ADD THESE
    track_registration_success, track_registration_failure
)
 
# Load environment variables
load_dotenv()
 
# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT == "production"
 
router = APIRouter(tags=["Authentication"])
 
 
# -----------------------------
# Request/Response Models
# -----------------------------
class LoginValidation(BaseModel):
    email: str
    password: str
 
 
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
 
 
class UserResponse(BaseModel):
    user_id: str
    name: str
    email: str
    role: str
    created_at: str
    last_login: str | None
    tokens: TokenResponse
    
class RegisterValidation(BaseModel):
    name: str
    email: str
    password: str
    confirm_password: str
    
    @validator('name')
    def name_must_not_be_empty(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Name cannot be empty')
        if len(v.strip()) < 2:
            raise ValueError('Name must be at least 2 characters long')
        return v.strip()
    
    @validator('email')
    def email_must_be_valid(cls, v):
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, v):
            raise ValueError('Invalid email format')
        return v.lower().strip()
    
    @validator('password')
    def password_must_be_strong(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one number')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')
        return v
    
    @validator('confirm_password')
    def passwords_must_match(cls, v, values):
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v


class ChangePasswordRequest(BaseModel):
    email: str
    current_password: str
    new_password: str
    confirm_new_password: str

    @validator('new_password')
    def new_password_must_be_strong(cls, v):
        if len(v) < 8:
            raise ValueError('New password must be at least 8 characters long')
        if not any(char.isdigit() for char in v):
            raise ValueError('New password must contain at least one number')
        if not any(char.isupper() for char in v):
            raise ValueError('New password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('New password must contain at least one lowercase letter')
        return v

    @validator('confirm_new_password')
    def passwords_must_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('New passwords do not match')
        return v

 
 
# -----------------------------
# LOGIN ENDPOINT
# -----------------------------
@router.post("/login")
async def login(data: LoginValidation, response: Response, db=Depends(get_db)):
    auth = AuthService(db)
    user = auth.authenticate_user(data.email, data.password)
    if not user:
        track_login_failure()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    access = auth.create_access_token(str(user["id"]), user["email"])    
    refresh = auth.create_refresh_token(str(user["id"]), user["email"])

    track_login_success()
   
    # Calculate expiry time
    expires = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    # ---------------------------
    # Set HTTP-only Secure Cookie
    # ---------------------------
    response.set_cookie(
    key="refresh_token",
    value=refresh,
    httponly=True,
    secure=IS_PRODUCTION,
    samesite="none" if IS_PRODUCTION else "lax",
    domain="automios.com" if IS_PRODUCTION else None,
    path="/",
    max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
)
   
   

    return {
        "user_id": str(user["id"]),
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "created_at": str(user["created_at"]) if user["created_at"] else "",
        "last_login": str(user["last_login"]) if user["last_login"] else None,
        "access_token": access,
        "token_type": "bearer"
    }
 
 
# -----------------------------
# REFRESH TOKEN ENDPOINT
# -----------------------------
@router.post("/refresh")  # Changed to POST
async def refresh_token(
    response: Response,
    refresh_token: str = Cookie(None),
    db=Depends(get_db)
):
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing"
        )
 
    try:
        # Decode and verify the refresh token
        payload = jwt.decode(
            refresh_token, 
            JWT_SECRET, 
            algorithms=[JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        email = payload.get("email")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid token payload"
            )
    except jwt.ExpiredSignatureError:
        track_token_refresh_failure()
        print("❌ Refresh token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired"
        )
    except jwt.InvalidTokenError as e:
        track_token_refresh_failure()
        print(f"❌ Invalid refresh token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid refresh token"
        )
    # Create new tokens using AuthService
    auth = AuthService(db)
    new_access = auth.create_access_token(user_id, email)
    new_refresh = auth.create_refresh_token(user_id, email)
    track_token_refresh()
    # Calculate expiry time
    expires = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    # Rotate refresh token (security best practice)
    response.set_cookie(
    key="refresh_token",
    value=new_refresh,
    httponly=True,
    secure=IS_PRODUCTION,
    samesite="none" if IS_PRODUCTION else "lax",
    domain="automios.com" if IS_PRODUCTION else None,
    path="/",
    max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
)
    return {
        "access_token": new_access,
        "token_type": "bearer"
    }
 
 
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterValidation, 
    response: Response, 
    db=Depends(get_db)
):
    """
    Register a new user account with 'user' role only.
    After successful registration, user is automatically logged in.
    """
    auth = AuthService(db)
    
    try:
        # Check if user already exists
        existing_user = auth.get_user_by_email(data.email)
        if existing_user:
            track_registration_failure()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered"
            )
        
        # Create new user with 'user' role
        new_user = auth.create_user(
            name=data.name,
            email=data.email,
            password=data.password,
            role="user"  # Fixed role for registration
        )
        
        if not new_user:
            track_registration_failure()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user account"
            )
        
        # Generate tokens for automatic login
        access_token = auth.create_access_token(str(new_user["id"]), new_user["email"])
        refresh_token = auth.create_refresh_token(str(new_user["id"]), new_user["email"])
        
        track_registration_success()
        
        # Calculate expiry time
        expires = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        # Set refresh token in HTTP-only cookie
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=IS_PRODUCTION,
            samesite="none" if IS_PRODUCTION else "lax",
            domain="automios.com" if IS_PRODUCTION else None,
            path="/",
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
        )
        
        print(f"[OK] New user registered: {new_user['email']}")
        
        return {
            "message": "Registration successful",
            "user_id": str(new_user["id"]),
            "name": new_user["name"],
            "email": new_user["email"],
            "role": new_user["role"],
            "created_at": str(new_user["created_at"]) if new_user.get("created_at") else "",
            "access_token": access_token,
            "token_type": "bearer"
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        track_registration_failure()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        track_registration_failure()
        print(f"[ERROR] Registration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again later."
        )
 
# -----------------------------
# LOGOUT ENDPOINT
# -----------------------------
@router.post("/logout")
async def logout(response: Response):
    track_logout()
    response.delete_cookie(
    key="refresh_token",
    path="/",
    domain="automios.com" if IS_PRODUCTION else None,
    samesite="none" if IS_PRODUCTION else "lax",
    secure=IS_PRODUCTION
)
    print("[OK] User logged out - cookie deleted")
    return {"message": "Logged out successfully"} 


# -----------------------------
# CHANGE PASSWORD ENDPOINT
# -----------------------------
@router.post("/change-password")
async def change_password(data: ChangePasswordRequest, db=Depends(get_db)):
    """
    Change the password for any user account (users or admins table).
    Requires the current password to be verified before updating.
    """
    from sqlalchemy import text as _text
    auth = AuthService(db)

    # ── 1. Look up user in users table first, then admins ──────────────────
    user_row = db.execute(
        _text("""
            SELECT id, email, password, role, 'users' AS tbl
            FROM users
            WHERE email = :email
              AND (is_deleted = FALSE OR is_deleted IS NULL)
        """),
        {"email": data.email.lower().strip()}
    ).fetchone()

    admin_row = None
    if not user_row:
        admin_row = db.execute(
            _text("""
                SELECT id, email_id AS email, password, role, 'admins' AS tbl
                FROM admins
                WHERE email_id = :email
            """),
            {"email": data.email.lower().strip()}
        ).fetchone()

    target = user_row or admin_row
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with that email address"
        )

    # ── 2. Verify current password ─────────────────────────────────────────
    stored_password = target.password
    if stored_password.startswith("$2b$") or stored_password.startswith("$2a$"):
        if not auth.verify_password(data.current_password, stored_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect"
            )
    else:
        if data.current_password != stored_password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect"
            )

    # ── 3. Update password (plain text, matching system convention) ─────────
    if user_row:
        db.execute(
            _text("UPDATE users SET password = :password WHERE email = :email"),
            {"password": data.new_password, "email": data.email.lower().strip()}
        )
    else:
        db.execute(
            _text("UPDATE admins SET password = :password WHERE email_id = :email"),
            {"password": data.new_password, "email": data.email.lower().strip()}
        )

    db.commit()
    print(f"[OK] Password changed for: {data.email}")
    return {"message": "Password changed successfully"}