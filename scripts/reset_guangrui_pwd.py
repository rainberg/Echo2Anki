#!/usr/bin/env python3
import sys
sys.path.insert(0, "/opt/anki-app/backend")
from app.auth import hash_password
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models import User
from app.config import settings

GUANGRUI_USER_ID = "fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f"
NEW_PASSWORD = "Guangrui2026"

engine = create_engine(settings.DATABASE_URL_SYNC)
with Session(engine) as db:
    user = db.execute(select(User).where(User.id == GUANGRUI_USER_ID)).scalar_one_or_none()
    if user:
        user.password_hash = hash_password(NEW_PASSWORD)
        db.commit()
        print(f"Password reset for {user.email} ({user.display_name})")
    else:
        print("User not found!")
