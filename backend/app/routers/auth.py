from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    get_current_user,
    get_user_roles,
    verify_password,
)
from app.db import get_session
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: str
    email: str
    full_name: str
    team_roles: dict[str, str]


@router.post("/login", response_model=LoginResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    # OAuth2PasswordRequestForm uses `username` — we treat it as email.
    result = await session.execute(select(User).where(User.email == form.username.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    return LoginResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    roles = await get_user_roles(user, session)
    return MeResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        team_roles={str(team_id): role.value for team_id, role in roles.items()},
    )