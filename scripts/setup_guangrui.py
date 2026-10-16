#!/usr/bin/env python3
import sys
sys.path.insert(0, "/opt/anki-app/backend")
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models import User
from app.config import settings
from decimal import Decimal

GUANGRUI_USER_ID = "fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f"

engine = create_engine(settings.DATABASE_URL_SYNC)
with Session(engine) as db:
    user = db.execute(select(User).where(User.id == GUANGRUI_USER_ID)).scalar_one_or_none()
    if user:
        user.credits = Decimal("500")
        user.allowed_engines = ["local_whisper", "openai_whisper", "cohere"]
        db.commit()
        print(f"Updated user {user.email}:")
        print(f"  Credits: {user.credits}")
        print(f"  Allowed engines: {user.allowed_engines}")
    else:
        print("User not found!")
