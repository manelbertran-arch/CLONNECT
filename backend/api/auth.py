"""
Authentication module for Clonnect
- JWT-based authentication
- Password hashing with bcrypt
- User registration and login
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import and_
import bcrypt
import jwt

try:
    from api.database import get_db
    from api.models import User, UserCreator, Creator
except:
    from database import get_db
    from models import User, UserCreator, Creator


# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    # Generate a random secret for development (changes on restart)
    import secrets
    JWT_SECRET = secrets.token_urlsafe(32)
    print("⚠️  WARNING: JWT_SECRET not set - using random secret. Tokens will invalidate on restart!")
    print("   Set JWT_SECRET env var for production to persist tokens across restarts.")
elif len(JWT_SECRET) < 32:
    print("⚠️  WARNING: JWT_SECRET is less than 32 characters. Use a longer secret for security.")

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 1 week

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer(auto_error=False)


# Pydantic models
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    is_active: bool
    creators: list


# Password hashing
def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


# JWT token management
def create_access_token(user_id: str) -> str:
    """Create JWT access token"""
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# Dependency to get current user
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


# Optional auth dependency (for endpoints that work with or without auth)
async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user if authenticated, None otherwise"""
    if not credentials:
        return None

    payload = decode_token(credentials.credentials)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


def get_user_creators(db: Session, user_id: str) -> list:
    """Get all creators associated with a user"""
    user_creators = db.query(UserCreator, Creator).join(
        Creator, UserCreator.creator_id == Creator.id
    ).filter(UserCreator.user_id == user_id).all()

    return [
        {
            "id": str(creator.id),
            "name": creator.name,
            "clone_name": creator.clone_name,
            "role": uc.role
        }
        for uc, creator in user_creators
    ]


# Routes
@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if email already exists
    existing = db.query(User).filter(User.email == user_data.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create user
    user = User(
        email=user_data.email.lower(),
        password_hash=hash_password(user_data.password),
        name=user_data.name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create access token
    token = create_access_token(str(user.id))

    return TokenResponse(
        access_token=token,
        user={
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "creators": []
        }
    )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Login and get access token"""
    user = db.query(User).filter(User.email == credentials.email.lower()).first()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    # Get user's creators
    creators = get_user_creators(db, str(user.id))

    # Create access token
    token = create_access_token(str(user.id))

    return TokenResponse(
        access_token=token,
        user={
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "creators": creators
        }
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get current user info"""
    creators = get_user_creators(db, str(current_user.id))

    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        is_active=current_user.is_active,
        creators=creators
    )


@router.post("/link-creator/{creator_name}")
async def link_creator(
    creator_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Link a creator to the current user"""
    # Find creator by name
    creator = db.query(Creator).filter(Creator.name == creator_name).first()
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Creator '{creator_name}' not found"
        )

    # Check if already linked
    existing = db.query(UserCreator).filter(
        and_(UserCreator.user_id == current_user.id, UserCreator.creator_id == creator.id)
    ).first()

    if existing:
        return {"message": "Creator already linked", "creator": creator_name}

    # Create link
    user_creator = UserCreator(
        user_id=current_user.id,
        creator_id=creator.id,
        role="owner"
    )
    db.add(user_creator)
    db.commit()

    return {"message": "Creator linked successfully", "creator": creator_name}


@router.delete("/unlink-creator/{creator_name}")
async def unlink_creator(
    creator_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unlink a creator from the current user"""
    creator = db.query(Creator).filter(Creator.name == creator_name).first()
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Creator '{creator_name}' not found"
        )

    link = db.query(UserCreator).filter(
        and_(UserCreator.user_id == current_user.id, UserCreator.creator_id == creator.id)
    ).first()

    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator not linked to your account"
        )

    db.delete(link)
    db.commit()

    return {"message": "Creator unlinked successfully"}
