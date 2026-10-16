from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PushConfigCreate(BaseModel):
    name: str = ""
    push_mode: str = Field(..., pattern="^(self_hosted|ankiweb)$")
    deck_name: str = "Default"
    sync_username: str = ""
    sync_password: str = ""
    ankiweb_username: str = ""
    ankiweb_password: str = ""


class PushConfigUpdate(BaseModel):
    name: Optional[str] = None
    deck_name: Optional[str] = None
    sync_username: Optional[str] = None
    sync_password: Optional[str] = None
    ankiweb_username: Optional[str] = None
    ankiweb_password: Optional[str] = None


class PushConfigResponse(BaseModel):
    id: UUID
    name: str
    push_mode: str
    deck_name: str
    sync_username: str
    ankiweb_username: str
    has_sync_password: bool
    has_ankiweb_password: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PushRequest(BaseModel):
    collection_id: UUID
    config_ids: List[UUID] = Field(..., min_length=1)
    force: bool = False


class PushStatusItem(BaseModel):
    config_id: UUID
    pushed_count: int
    unpushed_count: int


class PushStatusResponse(BaseModel):
    total_items: int
    configs: List[PushStatusItem]


class PushRecordResponse(BaseModel):
    id: UUID
    collection_id: Optional[UUID] = None
    config_id: Optional[UUID] = None
    push_mode: str
    deck_name: Optional[str] = None
    status: str
    card_count: int = 0
    skipped_count: int = 0
    error_message: str = ""
    duration_ms: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}
