# 功能设计文档：已推送句子标示 & 公共库功能

> 版本：v1.0  
> 日期：2026-05-26  
> 状态：待实施

---

## 目录

1. [功能1：已推送句子标示](#1-功能1已推送句子标示)
2. [功能2：公共库功能](#2-功能2公共库功能)
3. [实施优先级](#3-实施优先级)
4. [数据库迁移清单](#4-数据库迁移清单)

---

## 1. 功能1：已推送句子标示

### 1.1 需求背景

Streamlit 字幕版（`app_subtitle.py`）中已经推送了大量 Anki 卡片，但这些句子在 Web App 中没有被标示为"已推送"。同时，Web App 自身的推送记录（`push_records`）只追踪到收藏集级别，无法知道具体哪些句子被推送过。

### 1.2 目标

- 精确追踪每个 Segment 的推送状态（segment 级别）
- 统一标示 Streamlit 推送 + Web App 推送的句子
- 前端界面展示句子的推送状态

### 1.3 数据模型变更

#### 1.3.1 新增 `push_record_items` 关联表

记录每次推送中包含的具体 segment 及其推送结果：

```sql
CREATE TABLE push_record_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    push_record_id UUID NOT NULL REFERENCES push_records(id) ON DELETE CASCADE,
    segment_id  UUID NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    status      VARCHAR(20) NOT NULL DEFAULT 'pushed',  -- pushed / skipped / failed
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(push_record_id, segment_id)
);

CREATE INDEX idx_push_record_items_segment ON push_record_items(segment_id);
CREATE INDEX idx_push_record_items_record ON push_record_items(push_record_id);
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `push_record_id` | UUID | 关联推送记录 |
| `segment_id` | UUID | 关联句子 |
| `status` | VARCHAR(20) | pushed=成功推送, skipped=跳过, failed=失败 |
| `created_at` | TIMESTAMP | 记录创建时间 |

#### 1.3.2 SegmentResponse Schema 扩展

```python
class SegmentResponse(BaseModel):
    id: UUID
    task_id: UUID
    seq_index: int
    start_time: Decimal
    end_time: Decimal
    german_text: str
    chinese_text: str
    clip_path: Optional[str]
    collected: bool = False          # 已有：是否在收藏集中
    pushed: bool = False             # 新增：是否已被推送到Anki
    last_pushed_at: Optional[datetime] = None  # 新增：最后推送时间

    model_config = {"from_attributes": True}
```

### 1.4 后端逻辑变更

#### 1.4.1 推送时写入 push_record_items

修改 `routers/anki.py` 中的 `push_to_anki` 函数：

```
推送流程（修改后）：
1. 获取收藏集中 push_enabled 的 items
2. 构建 segments_data（现有逻辑）
3. 创建 PushRecord（现有逻辑）
4. 执行推送（现有逻辑）
5. 【新增】推送完成后，逐条写入 push_record_items：
   - 推送成功的 segment → status='pushed'
   - 跳过的 segment → status='skipped'
   - 失败的 segment → status='failed'
6. 更新 PushRecord 状态（现有逻辑）
```

#### 1.4.2 Segment 推送状态查询

在返回 SegmentResponse 时，通过子查询填充 `pushed` 和 `last_pushed_at`：

```python
# 在 tasks.py 或 segments.py 的查询中
from app.models import PushRecordItem

# 子查询：获取每个 segment 的推送状态
push_subq = (
    select(
        PushRecordItem.segment_id,
        func.max(PushRecordItem.created_at).label("last_pushed_at"),
    )
    .group_by(PushRecordItem.segment_id)
    .subquery()
)

# 主查询中 LEFT JOIN
query = select(Segment, push_subq.c.last_pushed_at).outerjoin(
    push_subq, Segment.id == push_subq.c.segment_id
)
```

### 1.5 Streamlit 历史数据迁移

#### 1.5.1 迁移脚本设计

编写一次性迁移脚本 `scripts/migrate_streamlit_pushes.py`：

```
迁移流程：
1. 扫描 /var/lib/anki-streamlit-subtitle/tasks/*/manifest.json
2. 对每个 manifest：
   a. 读取 favorites 和 push_excluded 列表
   b. 推送过的句子 = favorites - push_excluded
   c. 检查 Web App 数据库中是否已有对应的 Task（通过 file_hash 匹配）
   d. 如果没有 Task → 创建 Task + Segments
   e. 创建收藏集"Streamlit 推送历史 - {upload_name}"
   f. 将推送过的句子加入收藏集
   g. 创建 PushRecord + PushRecordItems
3. 输出迁移统计报告
```

#### 1.5.2 Streamlit 推送后回写（P3 优先级）

修改 `app_subtitle.py` 的推送逻辑，推送成功后调用 Web App API：

```python
# 推送成功后
if result.get("success"):
    # 调用 Web App API 记录推送
    import requests
    requests.post("http://localhost:8000/api/anki/streamlit-push-callback", json={
        "task_id": task_id,
        "pushed_indices": push_indices,
        "deck_name": st.session_state.subtitle_deck_name,
    })
```

新增 API 端点：

```
POST /api/anki/streamlit-push-callback
Body: {
    "task_id": "str",          # Streamlit task ID
    "pushed_indices": [int],   # 推送的句子索引列表
    "deck_name": "str"         # 目标牌组名
}
```

### 1.6 前端变更

#### 1.6.1 任务详情页 - 句子列表

在 `TaskDetailView.vue` 的句子列表中，增加推送状态标示：

- 已推送句子：显示 ✅ 图标 + 最后推送时间
- 未推送句子：无特殊标示
- 收藏集推送按钮旁：显示"已推送 N 句"

#### 1.6.2 收藏集详情页

在 `CollectionDetailView.vue` 中：

- 每个 CollectionItem 增加"已推送"标签
- 显示推送历史（从 push_record_items 查询）

---

## 2. 功能2：公共库功能

### 2.1 需求背景

现有公共库功能（`public.py` + `PublicView.vue`）仅有基础的列表+搜索+播放，缺少分类体系、分享机制和用户交互。需要参考"每日德语听力"APP 的交互模式，构建完整的公共库功能。

### 2.2 目标

- 四维分类体系：难度 A1-C2、主题/频道、音频时长、用户自定义标签
- 手动+快捷分享机制
- 用户交互：点赞、收藏到自己的收藏集
- 参考"每日德语听力"的浏览体验

### 2.3 数据模型变更

#### 2.3.1 新增 `public_shares` 表

```sql
CREATE TABLE public_shares (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE UNIQUE,
    user_id         UUID NOT NULL REFERENCES users(id),
    title           VARCHAR(200) NOT NULL,
    description     TEXT DEFAULT '',
    difficulty      VARCHAR(5),              -- A1/A2/B1/B2/C1/C2
    category        VARCHAR(50),             -- 主题分类
    duration_tier   VARCHAR(20),             -- short/medium/long
    cover_url       VARCHAR(500) DEFAULT '',
    play_count      INTEGER DEFAULT 0,
    like_count      INTEGER DEFAULT 0,
    collect_count   INTEGER DEFAULT 0,
    is_featured     BOOLEAN DEFAULT FALSE,
    shared_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_public_shares_user ON public_shares(user_id);
CREATE INDEX idx_public_shares_difficulty ON public_shares(difficulty);
CREATE INDEX idx_public_shares_category ON public_shares(category);
CREATE INDEX idx_public_shares_duration ON public_shares(duration_tier);
CREATE INDEX idx_public_shares_featured ON public_shares(is_featured) WHERE is_featured = TRUE;
CREATE INDEX idx_public_shares_shared_at ON public_shares(shared_at DESC);
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | UUID | 关联任务（UNIQUE，一个任务只能分享一次） |
| `user_id` | UUID | 分享者 |
| `title` | VARCHAR(200) | 分享标题（默认=upload_name，可编辑） |
| `description` | TEXT | 分享描述 |
| `difficulty` | VARCHAR(5) | CEFR难度级别：A1/A2/B1/B2/C1/C2 |
| `category` | VARCHAR(50) | 主题分类（见2.4分类体系） |
| `duration_tier` | VARCHAR(20) | 时长分类：short(<30s)/medium(30s-3min)/long(>3min) |
| `cover_url` | VARCHAR(500) | 封面图URL（可选） |
| `play_count` | INTEGER | 播放次数 |
| `like_count` | INTEGER | 点赞数（冗余计数，避免每次COUNT） |
| `collect_count` | INTEGER | 被收藏次数（冗余计数） |
| `is_featured` | BOOLEAN | 是否精选（管理员标记） |
| `shared_at` | TIMESTAMP | 分享时间 |

#### 2.3.2 新增 `public_likes` 表

```sql
CREATE TABLE public_likes (
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    share_id    UUID NOT NULL REFERENCES public_shares(id) ON DELETE CASCADE,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, share_id)
);
```

#### 2.3.3 新增 `public_collects` 表

用户从公共库收藏到自己的收藏集：

```sql
CREATE TABLE public_collects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    share_id        UUID NOT NULL REFERENCES public_shares(id) ON DELETE CASCADE,
    collection_id   UUID REFERENCES collections(id) ON DELETE SET NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, share_id, collection_id)
);

CREATE INDEX idx_public_collects_user ON public_collects(user_id);
CREATE INDEX idx_public_collects_share ON public_collects(share_id);
```

**说明**：`collection_id` 可为 NULL，表示用户收藏了但未指定收藏集（后续可移动）。

#### 2.3.4 扩展 `tags` 表

```sql
ALTER TABLE tags ADD COLUMN is_system BOOLEAN DEFAULT FALSE;
ALTER TABLE tags ADD COLUMN tag_type VARCHAR(20) DEFAULT 'custom';
-- tag_type: 'category' / 'difficulty' / 'custom'
```

### 2.4 分类体系

#### 2.4.1 难度级别

| 级别 | 说明 | 典型特征 |
|------|------|----------|
| A1 | 入门 | 简单日常用语，短句，慢速 |
| A2 | 初级 | 基础对话，常用词汇 |
| B1 | 中级 | 日常交流无障碍，中等语速 |
| B2 | 中高级 | 复杂话题，较快语速 |
| C1 | 高级 | 学术/专业内容，接近母语语速 |
| C2 | 精通 | 高级学术/文学，母语级别 |

#### 2.4.2 主题分类

| 分类键值 | 显示名称 | 说明 |
|----------|----------|------|
| `news` | 新闻 | 新闻报道、时事 |
| `daily` | 日常对话 | 日常生活场景 |
| `textbook` | 教材 | 教科书配套音频 |
| `exam` | 备考 | TestDaF/DSH/Goethe备考 |
| `podcast` | 播客 | 德语播客节目 |
| `movie` | 影视 | 电影/剧集片段 |
| `business` | 商务 | 职场/商务德语 |
| `culture` | 文化 | 文化/历史/艺术 |
| `other` | 其他 | 不属于以上分类 |

#### 2.4.3 时长分类

| 分类键值 | 显示名称 | 时长范围 |
|----------|----------|----------|
| `short` | 短句 | < 30秒 |
| `medium` | 中篇 | 30秒 - 3分钟 |
| `long` | 长篇 | > 3分钟 |

时长分类根据 `Task.file_duration_sec` 自动计算，分享时无需手动选择。

### 2.5 API 设计

#### 2.5.1 分享相关

```
POST   /api/public/shares
  请求体: {
    "task_id": "UUID",
    "title": "str (可选，默认=upload_name)",
    "description": "str (可选)",
    "difficulty": "str (可选, A1-C2)",
    "category": "str (可选, 见分类表)",
    "tag_ids": ["UUID"] (可选)
  }
  快捷分享: 只传 task_id，其他为空
  完整分享: 填写所有字段
  响应: PublicShareResponse

GET    /api/public/shares
  参数: page, per_page, difficulty, category, duration_tier, tag, q, sort
  sort: newest / popular / most_collected
  响应: PaginatedPublicShareResponse

GET    /api/public/shares/{share_id}
  响应: PublicShareDetailResponse (含句子列表)

PATCH  /api/public/shares/{share_id}
  请求体: { title?, description?, difficulty?, category?, tag_ids? }
  响应: PublicShareResponse

DELETE /api/public/shares/{share_id}
  响应: 204
```

#### 2.5.2 交互相关

```
POST   /api/public/shares/{share_id}/like
  响应: { "liked": true, "like_count": N }

DELETE /api/public/shares/{share_id}/like
  响应: { "liked": false, "like_count": N }

POST   /api/public/shares/{share_id}/collect
  请求体: { "collection_id": "UUID (可选)" }
  响应: { "collected": true, "collect_count": N }
  说明: 如果提供 collection_id，将公共库的句子复制到用户收藏集

DELETE /api/public/shares/{share_id}/collect
  请求体: { "collection_id": "UUID (可选)" }
  响应: { "collected": false, "collect_count": N }
```

#### 2.5.3 分类相关

```
GET    /api/public/categories
  响应: [{ "key": "news", "name": "新闻", "count": N }, ...]

GET    /api/public/difficulties
  响应: [{ "key": "A1", "name": "入门", "count": N }, ...]
```

#### 2.5.4 播放计数

```
POST   /api/public/shares/{share_id}/play
  说明: 记录一次播放，play_count + 1
  响应: { "play_count": N }
```

### 2.6 Schema 定义

```python
class PublicShareCreate(BaseModel):
    task_id: UUID
    title: Optional[str] = None
    description: str = ""
    difficulty: Optional[str] = None  # A1-C2
    category: Optional[str] = None    # 见分类表
    tag_ids: List[UUID] = []

class PublicShareUpdate(BaseModel):
    title: Optional[str] = None
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
    is_liked: bool = False       # 当前用户是否已点赞
    is_collected: bool = False   # 当前用户是否已收藏
    # 关联信息
    upload_name: str             # 来自 Task
    segment_count: int           # 来自 Task
    file_duration_sec: Optional[Decimal]  # 来自 Task
    tags: List[TagResponse] = []
    model_config = {"from_attributes": True}

class PublicShareDetailResponse(PublicShareResponse):
    segments: List[SegmentResponse] = []
    sharer_name: Optional[str] = None  # 分享者名称

class PaginatedPublicShareResponse(BaseModel):
    items: List[PublicShareResponse]
    total: int
    page: int
    per_page: int
```

### 2.7 前端设计

#### 2.7.1 公共库首页重构

**布局结构**（参考"每日德语听力"）：

```
┌─────────────────────────────────────────────────┐
│ 顶部搜索栏                                       │
│ [🔍 搜索德文/中文...]              [筛选 ▼]      │
├─────────────────────────────────────────────────┤
│ 精选推荐（横向滚动卡片）                           │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐            │
│ │ 📌   │ │ 📌   │ │ 📌   │ │ 📌   │  →         │
│ │ 标题  │ │ 标题  │ │ 标题  │ │ 标题  │            │
│ │ B1·新闻│ │ A2·日常│ │ C1·播客│ │ B2·备考│            │
│ │ ▶2:30 │ │ ▶0:45 │ │ ▶15:00│ │ ▶3:20 │            │
│ │ ❤️12  │ │ ❤️8   │ │ ❤️25  │ │ ❤️15  │            │
│ └──────┘ └──────┘ └──────┘ └──────┘            │
├─────────────────────────────────────────────────┤
│ 难度筛选（横向标签）                               │
│ [A1] [A2] [B1] [B2] [C1] [C2] [全部]           │
├─────────────────────────────────────────────────┤
│ 主题分类（横向标签）                               │
│ [📰新闻] [💬日常] [📖教材] [📝备考] [🎙️播客]     │
│ [🎬影视] [💼商务] [🎭文化] [📌其他]               │
├─────────────────────────────────────────────────┤
│ 排序方式                                         │
│ [最新] [最热] [最多收藏]                          │
├─────────────────────────────────────────────────┤
│ 分享列表（卡片网格）                               │
│ ┌──────────────┐ ┌──────────────┐               │
│ │ 📌 标题       │ │ 📌 标题       │               │
│ │ B1 · 新闻     │ │ A2 · 日常     │               │
│ │ ▶ 2:30       │ │ ▶ 0:45       │               │
│ │ 12句          │ │ 8句           │               │
│ │ ❤️ 12  ⭐ 3   │ │ ❤️ 8   ⭐ 1   │               │
│ │ [收藏] [点赞] │ │ [收藏] [点赞] │               │
│ └──────────────┘ └──────────────┘               │
│ ┌──────────────┐ ┌──────────────┐               │
│ │ ...          │ │ ...          │               │
│ └──────────────┘ └──────────────┘               │
├─────────────────────────────────────────────────┤
│ 加载更多...                                      │
└─────────────────────────────────────────────────┘
```

#### 2.7.2 公共库详情页

```
┌─────────────────────────────────────────────────┐
│ ← 返回公共库                                     │
├─────────────────────────────────────────────────┤
│ 标题：德国每日新闻摘要                             │
│ 分享者：user@example.com                         │
│ B1 · 新闻 · 中篇(2:30) · 12句                    │
│ 📝 这是每日德国新闻的德语听力练习...                │
│ 标签：[时事] [慢速] [B1]                          │
├─────────────────────────────────────────────────┤
│ ▶ 播放全部    ❤️ 12 点赞    ⭐ 收藏到我的收藏集    │
├─────────────────────────────────────────────────┤
│ 句子列表                                         │
│ 1. ▶ Die Bundesregierung hat heute...    00:00  │
│    联邦政府今天...                                │
│ 2. ▶ Die Verhandlungen über...           00:15  │
│    关于...的谈判                                  │
│ 3. ▶ ...                                        │
├─────────────────────────────────────────────────┤
│ 播放次数：156  ·  收藏次数：23  ·  分享时间：2026-05-20│
└─────────────────────────────────────────────────┘
```

#### 2.7.3 分享触发 UI

**任务详情页** — 新增"分享到公共库"按钮：

```
快捷分享：
  [📤 分享到公共库]  → 一键分享，自动填充标题和时长分类

完整分享：
  [📤 分享到公共库] → 弹出表单
  ┌─────────────────────────────────┐
  │ 分享到公共库                      │
  ├─────────────────────────────────┤
  │ 标题: [德国每日新闻摘要         ] │
  │ 描述: [这是每日德国新闻的...     ] │
  │ 难度: [B1 ▼]                    │
  │ 分类: [新闻 ▼]                   │
  │ 标签: [+添加标签]                │
  ├─────────────────────────────────┤
  │        [取消]  [确认分享]         │
  └─────────────────────────────────┘
```

**任务列表页** — 在每个任务卡片上增加分享图标按钮。

### 2.8 后端路由变更

#### 2.8.1 修改 `routers/public.py`

现有端点保留（向后兼容），新增端点：

```python
# 新增路由
@router.post("/shares", response_model=PublicShareResponse, status_code=201)
@router.get("/shares", response_model=PaginatedPublicShareResponse)
@router.get("/shares/{share_id}", response_model=PublicShareDetailResponse)
@router.patch("/shares/{share_id}", response_model=PublicShareResponse)
@router.delete("/shares/{share_id}", status_code=204)
@router.post("/shares/{share_id}/like")
@router.delete("/shares/{share_id}/like")
@router.post("/shares/{share_id}/collect")
@router.delete("/shares/{share_id}/collect")
@router.post("/shares/{share_id}/play")
@router.get("/categories")
@router.get("/difficulties")
```

#### 2.8.2 修改 `routers/tasks.py`

在任务详情 API 中增加分享状态：

```python
# TaskDetailResponse 扩展
class TaskDetailResponse(TaskResponse):
    segments: List[SegmentResponse] = []
    public_share: Optional[PublicShareResponse] = None  # 新增
```

### 2.9 前端路由变更

```javascript
// router/index.js 新增
{
  path: '/public',
  name: 'Public',
  component: () => import('../views/PublicView.vue')  // 重构
},
{
  path: '/public/:id',
  name: 'PublicDetail',
  component: () => import('../views/PublicDetailView.vue')  // 新增
},
```

---

## 3. 实施优先级

### P0 — 核心功能（立即实施）

| 序号 | 任务 | 涉及文件 |
|------|------|----------|
| 1 | 创建 `push_record_items` 表 + Alembic 迁移 | `models.py`, `alembic/versions/` |
| 2 | 推送时写入 `push_record_items` | `routers/anki.py` |
| 3 | Segment 推送状态查询填充 | `routers/tasks.py` 或 `routers/segments.py` |
| 4 | SegmentResponse 扩展 `pushed` + `last_pushed_at` | `schemas.py` |
| 5 | Streamlit 历史数据迁移脚本 | `scripts/migrate_streamlit_pushes.py` |

### P1 — 公共库核心（第二批实施）

| 序号 | 任务 | 涉及文件 |
|------|------|----------|
| 6 | 创建 `public_shares` + `public_likes` + `public_collects` 表 | `models.py`, `alembic/versions/` |
| 7 | 扩展 `tags` 表（is_system, tag_type） | `models.py`, `alembic/versions/` |
| 8 | 分享 API（CRUD + 快捷/完整分享） | `routers/public.py` |
| 9 | 公共库首页重构（分类筛选+卡片布局） | `PublicView.vue` |
| 10 | 分享触发 UI（任务详情页） | `TaskDetailView.vue` |

### P2 — 交互增强（第三批实施）

| 序号 | 任务 | 涉及文件 |
|------|------|----------|
| 11 | 点赞/收藏交互 API + UI | `routers/public.py`, `PublicView.vue` |
| 12 | 公共库详情页 | `PublicDetailView.vue` (新建) |
| 13 | 精选推荐 + 播放计数 | `routers/public.py`, `PublicView.vue` |
| 14 | 前端句子推送状态标示 | `TaskDetailView.vue`, `CollectionDetailView.vue` |

### P3 — 长期优化（后续迭代）

| 序号 | 任务 | 涉及文件 |
|------|------|----------|
| 15 | Streamlit 推送后自动回写 Web App | `app_subtitle.py`, `routers/anki.py` |
| 16 | 管理员精选管理界面 | 新增 admin 路由 |
| 17 | 公共库推荐算法（基于用户偏好） | 后端逻辑 |

---

## 4. 数据库迁移清单

### 迁移003：push_record_items

```sql
CREATE TABLE push_record_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    push_record_id UUID NOT NULL REFERENCES push_records(id) ON DELETE CASCADE,
    segment_id  UUID NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    status      VARCHAR(20) NOT NULL DEFAULT 'pushed',
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(push_record_id, segment_id)
);
CREATE INDEX idx_push_record_items_segment ON push_record_items(segment_id);
CREATE INDEX idx_push_record_items_record ON push_record_items(push_record_id);
```

### 迁移004：public_shares + public_likes + public_collects + tags扩展

```sql
-- public_shares
CREATE TABLE public_shares (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE UNIQUE,
    user_id         UUID NOT NULL REFERENCES users(id),
    title           VARCHAR(200) NOT NULL,
    description     TEXT DEFAULT '',
    difficulty      VARCHAR(5),
    category        VARCHAR(50),
    duration_tier   VARCHAR(20),
    cover_url       VARCHAR(500) DEFAULT '',
    play_count      INTEGER DEFAULT 0,
    like_count      INTEGER DEFAULT 0,
    collect_count   INTEGER DEFAULT 0,
    is_featured     BOOLEAN DEFAULT FALSE,
    shared_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_public_shares_user ON public_shares(user_id);
CREATE INDEX idx_public_shares_difficulty ON public_shares(difficulty);
CREATE INDEX idx_public_shares_category ON public_shares(category);
CREATE INDEX idx_public_shares_duration ON public_shares(duration_tier);
CREATE INDEX idx_public_shares_featured ON public_shares(is_featured) WHERE is_featured = TRUE;
CREATE INDEX idx_public_shares_shared_at ON public_shares(shared_at DESC);

-- public_likes
CREATE TABLE public_likes (
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    share_id    UUID NOT NULL REFERENCES public_shares(id) ON DELETE CASCADE,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, share_id)
);

-- public_collects
CREATE TABLE public_collects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    share_id        UUID NOT NULL REFERENCES public_shares(id) ON DELETE CASCADE,
    collection_id   UUID REFERENCES collections(id) ON DELETE SET NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, share_id, collection_id)
);
CREATE INDEX idx_public_collects_user ON public_collects(user_id);
CREATE INDEX idx_public_collects_share ON public_collects(share_id);

-- tags 扩展
ALTER TABLE tags ADD COLUMN is_system BOOLEAN DEFAULT FALSE;
ALTER TABLE tags ADD COLUMN tag_type VARCHAR(20) DEFAULT 'custom';

-- 预设系统标签
INSERT INTO tags (id, user_id, name, color, is_system, tag_type) VALUES
    (gen_random_uuid(), '00000000-0000-0000-0000-000000000000', '新闻', '#E74C3C', TRUE, 'category'),
    (gen_random_uuid(), '00000000-0000-0000-0000-000000000000', '日常对话', '#3498DB', TRUE, 'category'),
    (gen_random_uuid(), '00000000-0000-0000-0000-000000000000', '教材', '#2ECC71', TRUE, 'category'),
    (gen_random_uuid(), '00000000-0000-0000-0000-000000000000', '备考', '#F39C12', TRUE, 'category'),
    (gen_random_uuid(), '00000000-0000-0000-0000-000000000000', '播客', '#9B59B6', TRUE, 'category'),
    (gen_random_uuid(), '00000000-0000-0000-0000-000000000000', '影视', '#1ABC9C', TRUE, 'category'),
    (gen_random_uuid(), '00000000-0000-0000-0000-000000000000', '商务', '#34495E', TRUE, 'category'),
    (gen_random_uuid(), '00000000-0000-0000-0000-000000000000', '文化', '#E67E22', TRUE, 'category');
```

---

## 附录A：现有数据模型关系图（变更后）

```
users
  ├── tasks (1:N)
  │     ├── segments (1:N)
  │     │     ├── collection_items (1:N)  ──→ collections
  │     │     └── push_record_items (1:N) ──→ push_records
  │     ├── task_tags (N:M) ──→ tags
  │     └── public_shares (1:1)  [新增]
  ├── collections (1:N)
  │     └── collection_items (1:N) ──→ segments
  ├── anki_push_configs (1:N)
  ├── push_records (1:N)
  │     └── push_record_items (1:N)  [新增] ──→ segments
  ├── public_shares (1:N)  [新增]
  ├── public_likes (N:M)  [新增] ──→ public_shares
  └── public_collects (1:N)  [新增] ──→ public_shares + collections
```

## 附录B：API 端点汇总（新增）

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | /api/public/shares | 创建分享 | 必须 |
| GET | /api/public/shares | 分享列表 | 可选 |
| GET | /api/public/shares/{id} | 分享详情 | 可选 |
| PATCH | /api/public/shares/{id} | 更新分享 | 必须(所有者) |
| DELETE | /api/public/shares/{id} | 取消分享 | 必须(所有者) |
| POST | /api/public/shares/{id}/like | 点赞 | 必须 |
| DELETE | /api/public/shares/{id}/like | 取消点赞 | 必须 |
| POST | /api/public/shares/{id}/collect | 收藏 | 必须 |
| DELETE | /api/public/shares/{id}/collect | 取消收藏 | 必须 |
| POST | /api/public/shares/{id}/play | 记录播放 | 可选 |
| GET | /api/public/categories | 分类列表 | 无 |
| GET | /api/public/difficulties | 难度列表 | 无 |
| POST | /api/anki/streamlit-push-callback | Streamlit推送回写 | 内部 |
