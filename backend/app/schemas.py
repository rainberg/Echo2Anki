from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: UUID
    email: Optional[str] = None
    phone: Optional[str] = None
    display_name: Optional[str]
    role: str
    credits: Decimal
    allowed_engines: List[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserResponse(BaseModel):
    id: UUID
    email: Optional[str] = None
    phone: Optional[str] = None
    display_name: Optional[str]
    role: str
    credits: Decimal
    allowed_engines: List[str]
    max_push_configs: int = 4
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


class AdminUpdatePushConfigLimit(BaseModel):
    max_push_configs: int = Field(ge=1, le=50)


class AdminUserListResponse(BaseModel):
    items: List[AdminUserResponse]
    total: int
    page: int
    per_page: int


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str = Field(min_length=6)


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
    user_id: UUID
    upload_name: str
    title: str = ""
    difficulty: str = ""
    category: str = ""
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
    transcription_text: str = ""
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
    collected: bool = False
    pushed: bool = False
    last_pushed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SegmentUpdate(BaseModel):
    chinese_text: Optional[str] = None
    german_text: Optional[str] = None


class TaskUpdate(BaseModel):
    is_public: Optional[bool] = None
    title: Optional[str] = None
    difficulty: Optional[str] = None
    category: Optional[str] = None


class TaskRetry(BaseModel):
    engine: Optional[str] = None
    model_size: Optional[str] = None
    api_key: Optional[str] = None


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class CollectionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None


class CollectionItemAdd(BaseModel):
    segment_ids: List[UUID]


class CollectionItemToggle(BaseModel):
    push_enabled: bool


class CollectionResponse(BaseModel):
    id: UUID
    name: str
    description: str
    item_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CollectionDetailResponse(CollectionResponse):
    items: List["CollectionItemResponse"] = []


class CollectionItemResponse(BaseModel):
    id: UUID
    segment_id: UUID
    push_enabled: bool
    added_at: datetime
    segment: Optional[SegmentResponse] = None

    model_config = {"from_attributes": True}


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = "#4A90D9"


class TagResponse(BaseModel):
    id: UUID
    name: str
    color: str
    is_system: bool = False
    tag_type: str = "custom"
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskTagSet(BaseModel):
    tag_ids: List[UUID]


class PublicShareCreate(BaseModel):
    task_id: UUID
    title: Optional[str] = None
    description: str = ""
    difficulty: Optional[str] = None
    category: Optional[str] = None
    tag_ids: List[UUID] = []


class PublicShareUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    difficulty: Optional[str] = None
    category: Optional[str] = None
    tag_ids: Optional[List[UUID]] = None


class PublicShareResponse(BaseModel):
    id: UUID
    task_id: UUID
    user_id: UUID
    title: str
    description: str
    difficulty: Optional[str]
    category: Optional[str]
    duration_tier: Optional[str]
    cover_url: str
    play_count: int
    like_count: int
    collect_count: int
    is_featured: bool
    shared_at: datetime
    is_liked: bool = False
    is_collected: bool = False
    upload_name: str = ""
    segment_count: int = 0
    file_duration_sec: Optional[Decimal] = None
    tags: List["TagResponse"] = []

    model_config = {"from_attributes": True}


class PublicShareDetailResponse(PublicShareResponse):
    segments: List[SegmentResponse] = []
    sharer_name: Optional[str] = None


class PaginatedPublicShareResponse(BaseModel):
    items: List[PublicShareResponse]
    total: int
    page: int
    per_page: int
