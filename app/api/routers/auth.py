from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.security import create_access_token, verify_password, get_password_hash, get_current_user
from app.db.session import get_db
from schemas import UserCreate, User as UserSchema, Token
from app.services.user_service import get_user_by_username, get_user_by_email, create_user
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from app.core.config import settings
from models import User as UserModel

router = APIRouter()

@router.post("/register", response_model=UserSchema)
def register(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    db_user = get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    db_user = get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    try:
        db_user = create_user(db, user=user, commit=False)
        db.commit()
        db.refresh(db_user)
        return UserSchema(
            id=db_user.id,
            username=db_user.username,
            email=db_user.email,
            phone=getattr(db_user, 'phone', None),
            is_active=db_user.is_active,
            role=db_user.role,
            created_at=db_user.created_at,
            updated_at=getattr(db_user, 'updated_at', None)
        )
    except Exception as e:
        db.rollback()
        logger.error(f"用户注册失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="注册失败，请稍后重试"
        )

@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: UserSchema = Depends(get_current_user)):
    # Return JSON serialized user info, avoiding sensitive info disclosure
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active
    }