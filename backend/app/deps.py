import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_client import get_user_info, verify_token
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer()

_FK_TABLES = [
    ("tasks", "user_id"),
    ("collections", "user_id"),
    ("tags", "user_id"),
    ("billing_records", "user_id"),
    ("anki_push_configs", "user_id"),
    ("push_records", "user_id"),
]


async def _migrate_user_uuid(db: AsyncSession, old_id: UUID, new_id: UUID, email: str):
    tmp_email = f"{email}._migrating_"
    await db.execute(
        text("UPDATE users SET email = :tmp_email WHERE id = :old_id"),
        {"tmp_email": tmp_email, "old_id": old_id},
    )
    await db.execute(
        text(
            "INSERT INTO users (id, email, phone, display_name, role, credits, credits_reserved, allowed_engines, is_active, created_at, updated_at) "
            "SELECT :new_id, :email, phone, display_name, role, credits, credits_reserved, allowed_engines, is_active, created_at, updated_at "
            "FROM users WHERE id = :old_id"
        ),
        {"new_id": new_id, "email": email, "old_id": old_id},
    )
    for tbl, col in _FK_TABLES:
        await db.execute(
            text(f"UPDATE {tbl} SET {col} = :new_id WHERE {col} = :old_id"),
            {"new_id": new_id, "old_id": old_id},
        )
    await db.execute(
        text("DELETE FROM users WHERE id = :old_id"),
        {"old_id": old_id},
    )
    await db.commit()
    logger.info("Migrated user UUID: %s -> %s", old_id, new_id)


async def _sync_local_user(db: AsyncSession, auth_user: dict, credits: Optional[str] = None, credits_reserved: Optional[str] = None) -> User:
    user_id = UUID(auth_user["user_id"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None and auth_user.get("email"):
        result = await db.execute(select(User).where(User.email == auth_user["email"]))
        existing_by_email = result.scalar_one_or_none()
        if existing_by_email is not None and existing_by_email.id != user_id:
            await _migrate_user_uuid(db, existing_by_email.id, user_id, auth_user["email"])
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=user_id,
            email=auth_user.get("email"),
            phone=auth_user.get("phone"),
            display_name=auth_user.get("display_name", ""),
            role=auth_user.get("role", "user"),
            credits=Decimal(credits) if credits is not None else Decimal("0"),
            credits_reserved=Decimal(credits_reserved) if credits_reserved is not None else Decimal("0"),
            allowed_engines=["local_whisper"],
            is_active=auth_user.get("is_active", True),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("Auto-created local user %s from auth service", user_id)
    else:
        changed = False
        if auth_user.get("email") is not None and user.email != auth_user["email"]:
            user.email = auth_user["email"]
            changed = True
        if auth_user.get("phone") is not None and user.phone != auth_user["phone"]:
            # Clear phone from any other user that has it to avoid unique constraint violation
            new_phone = auth_user["phone"]
            if new_phone:
                conflict = await db.execute(select(User).where(User.phone == new_phone, User.id != user.id))
                conflict_user = conflict.scalar_one_or_none()
                if conflict_user:
                    conflict_user.phone = None
                    logger.warning("Cleared phone '%s' from conflicting user %s to assign to %s", new_phone, conflict_user.id, user.id)
            user.phone = new_phone
            changed = True
        if auth_user.get("display_name") and user.display_name != auth_user["display_name"]:
            user.display_name = auth_user["display_name"]
            changed = True
        if auth_user.get("role") and user.role != auth_user["role"]:
            user.role = auth_user["role"]
            changed = True
        if not auth_user.get("is_active", True) and user.is_active:
            user.is_active = False
            changed = True
        if credits is not None and user.credits != Decimal(credits):
            user.credits = Decimal(credits)
            changed = True
        if credits_reserved is not None and user.credits_reserved != Decimal(credits_reserved):
            user.credits_reserved = Decimal(credits_reserved)
            changed = True
        if changed:
            await db.commit()
            await db.refresh(user)

    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials

    verify_result = await verify_token(token)
    if verify_result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    if not verify_result.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    user_info = await get_user_info(token)
    if user_info is None:
        auth_user = {
            "user_id": verify_result["user_id"],
            "role": verify_result.get("role", "user"),
            "is_active": verify_result.get("is_active", True),
        }
        credits = verify_result.get("credits")
        credits_reserved = verify_result.get("credits_reserved")
    else:
        auth_user = {
            "user_id": verify_result["user_id"],
            "email": user_info.get("email"),
            "phone": user_info.get("phone"),
            "display_name": user_info.get("display_name"),
            "role": user_info.get("role", "user"),
            "is_active": user_info.get("is_active", True),
        }
        credits = user_info.get("credits", verify_result.get("credits"))
        credits_reserved = user_info.get("credits_reserved", verify_result.get("credits_reserved"))

    user = await _sync_local_user(db, auth_user, credits, credits_reserved)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    return user


async def get_admin_user(
    user: User = Depends(get_current_user),
) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
