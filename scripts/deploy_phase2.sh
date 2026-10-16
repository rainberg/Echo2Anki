#!/bin/bash
set -e

echo "=== Phase 2: Deploy Backend + Frontend ==="

echo "[1/6] Uploading backend files..."

sudo mkdir -p /opt/anki-app/backend/app/routers

cat > /opt/anki-app/backend/app/schemas.py << 'PYEOF'
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    display_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: Optional[str]
    role: str
    credits: Decimal
    allowed_engines: List[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: Optional[str]
    role: str
    credits: Decimal
    allowed_engines: List[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminTopup(BaseModel):
    amount: Decimal = Field(gt=0)
    description: Optional[str] = None


class AdminUpdateEngines(BaseModel):
    allowed_engines: List[str]


class AdminUpdateStatus(BaseModel):
    is_active: bool


class AdminUserListResponse(BaseModel):
    items: List[AdminUserResponse]
    total: int
    page: int
    per_page: int


class BillingBalance(BaseModel):
    credits: Decimal
    total_used: Decimal
    total_tasks: int
    total_duration_sec: Decimal


class BillingRecordResponse(BaseModel):
    id: UUID
    action: str
    amount: Decimal
    balance_after: Decimal
    duration_sec: Optional[Decimal]
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class BillingRecordListResponse(BaseModel):
    items: List[BillingRecordResponse]
    total: int
    page: int
    per_page: int


class EngineInfo(BaseModel):
    engine_key: str
    engine_name: str
    credits_per_minute: Decimal
    model_sizes: Optional[List[str]] = None


class SystemHealth(BaseModel):
    status: str
    version: str


class TaskCreate(BaseModel):
    engine: str = "local_whisper"
    model_size: str = "small"
    api_key: Optional[str] = None


class TaskResponse(BaseModel):
    id: UUID
    upload_name: str
    file_hash: str
    file_duration_sec: Optional[Decimal]
    file_size_bytes: Optional[int]
    engine: str
    model_size: str
    stage: str
    progress: Decimal
    stage_message: str
    error: str
    segment_count: int
    credits_charged: Decimal
    credits_reserved: Decimal
    is_public: bool
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    items: List[TaskResponse]
    total: int
    page: int
    per_page: int


class TaskDetailResponse(TaskResponse):
    segments: List["SegmentResponse"] = []


class SegmentResponse(BaseModel):
    id: UUID
    task_id: UUID
    seq_index: int
    start_time: Decimal
    end_time: Decimal
    german_text: str
    chinese_text: str
    clip_path: Optional[str]

    model_config = {"from_attributes": True}


class SegmentUpdate(BaseModel):
    chinese_text: Optional[str] = None
    german_text: Optional[str] = None


class TaskUpdate(BaseModel):
    is_public: Optional[bool] = None


class TaskRetry(BaseModel):
    engine: Optional[str] = None
    model_size: Optional[str] = None
    api_key: Optional[str] = None
PYEOF

echo "[2/6] Uploading task router..."
# This will be uploaded separately via pscp

echo "[3/6] Uploading segment router..."
# This will be uploaded separately via pscp

echo "[4/6] Uploading worker..."
# This will be uploaded separately via pscp

echo "[5/6] Uploading main.py..."
# This will be uploaded separately via pscp

echo "[6/6] Restarting API service..."
sudo systemctl restart anki-api.service
sleep 3
sudo systemctl status anki-api.service --no-pager | head -10

echo "Backend deploy complete!"
