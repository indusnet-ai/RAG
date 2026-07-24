# services/auth_service.py

import jwt
import os
from datetime import datetime, timedelta
from passlib.context import CryptContext
from sqlalchemy import text
from dotenv import load_dotenv
import uuid

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:

    def __init__(self, db):
        self.db = db

    # -----------------------------
    # JWT generation
    # -----------------------------
    def create_access_token(self, user_id: str, email: str):
        payload = {
            "sub": user_id,
            "email": email,
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    def create_refresh_token(self, user_id: str, email: str):
        payload = {
            "sub": user_id,
            "email": email,
            "exp": datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # -----------------------------
    # Password hashing + checking
    # -----------------------------
    def hash_password(self, plain_password: str):
        """Hash a plain text password"""
        return pwd_context.hash(plain_password)
    
    def verify_password(self, plain, hashed):
        return pwd_context.verify(plain, hashed)

    # -----------------------------
    # User Registration Methods
    # -----------------------------
    def get_user_by_email(self, email: str):
        """
        Check if user exists by email in both users and admins tables
        """
        # Check users table
        user = self.db.execute(
            text("""
                SELECT id, name, email, role 
                FROM users 
                WHERE email = :email 
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """),
            {"email": email.lower().strip()}
        ).fetchone()
        
        if user:
            return {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": user.role,
                "table": "users"
            }
        
        # Check admins table
        admin = self.db.execute(
            text("""
                SELECT id, name, email_id AS email, role 
                FROM admins 
                WHERE email_id = :email
            """),
            {"email": email.lower().strip()}
        ).fetchone()
        
        if admin:
            return {
                "id": admin.id,
                "name": admin.name,
                "email": admin.email,
                "role": admin.role,
                "table": "admins"
            }
        
        return None

    def create_user(self, name: str, email: str, password: str, role: str = "user"):
        """
        Create a new user account in the users table
        ⚠️ Stores password in plain text (NOT RECOMMENDED for production)
        """
        try:
            # ✅ Generate UUID for new user
            user_id = str(uuid.uuid4())
            
            # ✅ Store password as-is (plain text) - NO HASHING
            plain_password = password
            
            # Insert new user with UUID
            result = self.db.execute(
                text("""
                    INSERT INTO users (id, name, email, password, role, created_at, is_deleted)
                    VALUES (:id, :name, :email, :password, :role, CURRENT_TIMESTAMP, FALSE)
                    RETURNING id, name, email, role, created_at, last_login
                """),
                {
                    "id": user_id,  # ✅ UUID
                    "name": name.strip(),
                    "email": email.lower().strip(),
                    "password": plain_password,
                    "role": role
                }
            )
            
            # Fetch the created user
            user = result.fetchone()

            # Commit the transaction
            self.db.commit()
            
            if user:
                return {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role": user.role,
                    "created_at": user.created_at,
                    "last_login": user.last_login,
                    "table": "users"
                }
            
            return None
            
        except Exception as e:
            self.db.rollback()
            print(f"[ERROR] Error creating user: {str(e)}")
            raise e
        

    # -----------------------------
    # Login Logic
    # -----------------------------
    def authenticate_user(self, email: str, password: str):
        """
        Check user login in users table first,
        then in admins table if not found.
        """

        # --------------------------
        # 1) Try USERS table
        # --------------------------
        user = self.db.execute(
            text("""
                SELECT * FROM users 
                WHERE email = :email 
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """),
            {"email": email}
        ).fetchone()

        if user:
            # Password check
            if user.password.startswith("$2b$") or user.password.startswith("$2a$"):
                if not self.verify_password(password, user.password):
                    return None
            else:
                if password != user.password:
                    return None

            # Update last login
            self.db.execute(
                text("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = :id"),
                {"id": user.id}
            )
            self.db.commit()

            # Return as a unified object
            return {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "created_at": user.created_at,
                "last_login": user.last_login,
                "role": user.role,
                "table": "users"
            }

        # --------------------------
        # 2) Try ADMINS table
        # --------------------------
        admin = self.db.execute(
            text("""
                SELECT id, name, email_id AS email, password, role
                FROM admins
                WHERE email_id = :email
            """),
            {"email": email}
        ).fetchone()

        if admin:
            if admin.password.startswith("$2b$") or admin.password.startswith("$2a$"):
                if not self.verify_password(password, admin.password):
                    return None
            else:
                if password != admin.password:
                    return None

            return {
                "id": admin.id,
                "name": admin.name,
                "email": admin.email,
                "created_at": None,
                "last_login": None,
                "role": admin.role,
                "table": "admins"
            }

        # --------------------------
        # 3) Neither found
        # --------------------------
        return None