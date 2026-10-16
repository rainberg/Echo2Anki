# Anki App + Auth Service 交接文档

> 生成日期：2026-05-24 | 更新日期：2026-05-26
> 服务状态：已部署并通过端到端测试

---

## 1. 系统架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                    Oracle Cloud Frankfurt                        │
│                    89.168.93.94                                  │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Nginx      │    │   Nginx      │    │   Nginx      │      │
│  │ anki.3mudi   │    │ auth.3mudi   │    │ anki.3mudi   │      │
│  │  :443        │    │  :443        │    │  :443/ws     │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                    │              │
│  ┌──────▼───────┐    ┌──────▼───────┐    ┌──────▼───────┐      │
│  │  Backend     │    │ Auth Service │    │  Frontend    │      │
│  │  :8000       │◄──►│  :8001       │    │  (dist/)     │      │
│  │  FastAPI     │    │  FastAPI     │    │  Vue/SPA     │      │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┘      │
│         │                   │                                   │
│  ┌──────▼───────┐    ┌──────▼───────┐                          │
│  │  PostgreSQL  │    │  PostgreSQL  │                          │
│  │  db: anki    │    │  db: auth    │                          │
│  └──────────────┘    └──────────────┘                          │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Anki Sync   │    │  Streamlit   │    │  Docker      │      │
│  │  :8080       │    │  :8501       │    │  anki-sync   │      │
│  │  (Docker)    │    │  (V1 legacy) │    │  -standalone │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
└─────────────────────────────────────────────────────────────────┘

客户端 ──HTTPS──► Cloudflare ──► Nginx ──► 各服务
```

### 1.1 服务间调用关系

```
前端 (anki.3mudi.com)
  │
  ├── 注册/登录 ──────────► Auth Service (auth.3mudi.com/api/auth/*)
  │                         返回 JWT (access_token + refresh_token)
  │
  ├── 业务请求 ──────────► Backend (anki.3mudi.com/api/*)
  │   Header: Authorization: Bearer <access_token>
  │                         │
  │                         ├── verify_token() ──► Auth /api/auth/verify
  │                         ├── get_user_info() ─► Auth /api/auth/me
  │                         └── 自动同步本地 users 表
  │
  └── WebSocket ─────────► Backend (anki.3mudi.com/ws/progress?token=xxx)

Backend 内部调用 Auth Service：
  ├── 认证验证:  GET  /api/auth/verify
  ├── 用户信息:  GET  /api/auth/me
  ├── 积分预扣:  POST /api/credits/reserve
  ├── 积分结算:  POST /api/credits/settle
  ├── 积分退还:  POST /api/credits/refund
  ├── 管理员充值: POST /api/admin/users/{id}/add-credits
  └── 管理员禁用: PUT  /api/admin/users/{id}/toggle-active

Backend Anki 推送调用链：
  routers/anki.py → anki_push_router.push_cards_to_server()
    ├── ANKI_PUSH_MODE=sync_client → anki_sync_client_push (Anki 官方同步协议)
    └── ANKI_PUSH_MODE=direct      → anki_sync_push_safe (直接操作 SQLite，需停 Docker)
```

---

## 2. 服务器与基础设施

### 2.1 服务器信息

| 项目 | 值 |
|------|-----|
| 云服务商 | Oracle Cloud Frankfurt |
| 公网 IP | 89.168.93.94 |
| 操作系统 | Ubuntu 22.04 |
| SSH 密钥 | `D:/00_dev/04_key/ssh-key-2026-04-18_Oracle_Frankfurt.key` |
| SSH 用户 | ubuntu |

### 2.2 域名与 SSL

| 域名 | 指向 | SSL 证书 | 用途 |
|------|------|---------|------|
| anki.3mudi.com | 89.168.93.94 | Let's Encrypt | Backend API + Frontend |
| auth.3mudi.com | 89.168.93.94 | Let's Encrypt | Auth Service API |

SSL 证书路径：
- `/etc/letsencrypt/live/anki.3mudi.com/`
- `/etc/letsencrypt/live/auth.3mudi.com/`

### 2.3 数据库

| 数据库 | 用户 | 用途 | 所属服务 |
|--------|------|------|---------|
| anki | anki | 业务数据 | Backend |
| auth | auth | 用户认证数据 | Auth Service |

连接信息在各自 `.env` 文件中。

### 2.4 Python 环境

| 服务 | venv 路径 | Python 版本 |
|------|----------|-------------|
| Backend | /opt/anki-venv | 3.10 |
| Auth Service | /opt/auth-service/.venv | 3.10 |

### 2.5 Docker 容器

| 容器名 | 镜像 | 端口 | 用途 |
|--------|------|------|------|
| anki-sync-standalone | anki-sync-standalone | 8080 | Anki Sync Server（客户端同步协议） |

数据卷：`/var/lib/docker/volumes/anki-cloud_app-data/_data/anki_user/`

---

## 3. Auth Service 详细说明

### 3.1 部署信息

| 项目 | 值 |
|------|-----|
| 安装路径 | /opt/auth-service |
| 服务端口 | 8001 (内部) |
| systemd 服务 | auth-service.service |
| 配置文件 | /opt/auth-service/.env |
| 接口文档 | /opt/auth-service/API_DOC.md |

### 3.2 数据库表结构

```sql
-- auth 数据库
users          -- 用户表 (id, phone, email, password_hash, display_name, role, is_active, credits, credits_reserved)
user_apps      -- 用户-应用关联 (user_id, app_name, app_role, joined_at)
credit_logs    -- 积分变动日志 (user_id, action, amount, balance_after, reserved_after, reference_id, description, operator_id)
sms_send_logs  -- 短信发送记录
alembic_version -- 数据库迁移版本
```

### 3.3 代码结构

```
/opt/auth-service/
├── app/
│   ├── main.py          # FastAPI 入口，lifespan + 路由注册
│   ├── config.py         # pydantic-settings 配置 (AUTH_ 前缀)
│   ├── database.py       # AsyncEngine + session
│   ├── models.py         # SQLAlchemy 模型 (User, UserApp, CreditLog, SmsSendLog)
│   ├── schemas.py        # Pydantic schemas
│   ├── auth.py           # JWT 签发/验证/密码哈希
│   ├── captcha.py        # 滑块验证码生成/校验
│   ├── sms.py            # 短信发送 (阿里云 SMS / 开发模式)
│   └── routers/
│       ├── auth.py       # 认证路由 (注册/登录/验证/刷新/me)
│       ├── credits.py    # 积分路由 (reserve/settle/refund/topup/balance/logs)
│       └── admin.py      # 管理路由 (用户列表/充值/设置积分/禁用/角色)
├── alembic/              # 数据库迁移
├── .env                  # 环境变量
└── requirements.txt
```

### 3.4 核心 API 端点

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | /api/auth/register/email | 无 | 邮箱注册 |
| POST | /api/auth/register/phone | 无 | 手机号注册 |
| POST | /api/auth/login/password | 无 | 密码登录 |
| POST | /api/auth/login/phone | 无 | 手机号验证码登录（自动注册） |
| POST | /api/auth/refresh | 无 | 刷新令牌 |
| GET | /api/auth/verify | JWT | 验证令牌（服务端调用） |
| GET | /api/auth/me | JWT | 获取当前用户信息 |
| PUT | /api/auth/me | JWT | 更新用户信息/修改密码 |
| GET | /api/auth/captcha/generate | 无 | 生成滑块验证码 |
| POST | /api/auth/captcha/verify | 无 | 校验滑块位置 |
| POST | /api/auth/sms/send | 无 | 发送短信验证码 |
| GET | /api/credits/balance | JWT | 查询积分余额 |
| POST | /api/credits/reserve | JWT | 预扣积分 |
| POST | /api/credits/settle | JWT | 结算消费 |
| POST | /api/credits/refund | JWT | 退还积分 |
| POST | /api/credits/topup | JWT | 充值积分 |
| GET | /api/credits/logs | JWT | 查询积分记录 |
| GET | /api/admin/users | Admin JWT | 用户列表 |
| POST | /api/admin/users/{id}/add-credits | Admin JWT | 增加积分 |
| PUT | /api/admin/users/{id}/credits | Admin JWT | 设置积分 |
| PUT | /api/admin/users/{id}/toggle-active | Admin JWT | 启用/禁用用户 |
| PUT | /api/admin/users/{id}/role | Admin JWT | 修改用户角色 |
| GET | /api/admin/users/{id}/credit-logs | Admin JWT | 查看用户积分记录 |
| GET | /api/admin/credit-logs | Admin JWT | 全部积分记录 |

### 3.5 环境变量

```bash
AUTH_DATABASE_URL=postgresql+asyncpg://auth:auth_db_2026_secure@localhost:5432/auth
AUTH_DATABASE_URL_SYNC=postgresql://auth:auth_db_2026_secure@localhost:5432/auth
AUTH_JWT_SECRET=3mudi-auth-jwt-secret-2026-prod
AUTH_JWT_ALGORITHM=HS256
AUTH_JWT_ACCESS_EXPIRE_MINUTES=1440
AUTH_JWT_REFRESH_EXPIRE_DAYS=7
AUTH_SMS_PROVIDER=dev                    # 生产环境改为 aliyun
AUTH_SMS_ACCESS_KEY_ID=                  # 阿里云 SMS 配置
AUTH_SMS_ACCESS_KEY_SECRET=
AUTH_SMS_SIGN_NAME=
AUTH_SMS_TEMPLATE_CODE=100001
AUTH_ALLOWED_APPS=anki,steiner,aktie
AUTH_CORS_ORIGINS=https://anki.3mudi.com,https://steiner.3mudi.com,https://aktie.3mudi.com,http://localhost:5173,http://localhost:3000
```

### 3.6 积分消费流程

```
1. 预扣：POST /api/credits/reserve  { amount, reference_id }
   → credits 不变，credits_reserved 增加

2. 执行业务逻辑（如 AI 翻译）

3a. 结算：POST /api/credits/settle  { reserved_amount, actual_amount, reference_id }
    → credits 减少 actual_amount，credits_reserved 减少 reserved_amount
    → 差额 (reserved - actual) 自动退还

3b. 或业务失败时全额退还：
    POST /api/credits/settle  { reserved_amount=X, actual_amount=0 }
    → 等同于退还全部预扣
```

> **重要**：`reference_id` 全局唯一，重复提交返回 409，实现幂等性。Backend 使用格式 `task:{task_id}` 作为 reference_id，确保同一任务的积分操作不会重复执行。

---

## 4. Backend 详细说明

### 4.1 部署信息

| 项目 | 值 |
|------|-----|
| 安装路径 | /opt/anki-app/backend |
| 服务端口 | 8000 (内部) |
| systemd 服务 | anki-api.service |
| 配置文件 | /opt/anki-app/backend/.env |
| 前端文件 | /opt/anki-app/frontend/dist |

### 4.2 数据库表结构

```sql
-- anki 数据库
users             -- 用户表 (id, email[nullable], phone, display_name, role, credits, credits_reserved, allowed_engines, is_active)
tasks             -- 任务表 (id, user_id, upload_name, file_hash, engine, model_size, stage, progress, credits_charged, credits_reserved, ...)
segments          -- 音频片段 (id, task_id, seq_index, start_time, end_time, german_text, chinese_text, clip_path)
collections       -- 收藏集 (id, user_id, name, description)
collection_items  -- 收藏项 (id, collection_id, segment_id, push_enabled)
tags              -- 标签 (id, user_id, name, color, is_system, tag_type)
task_tags         -- 任务标签关联 (task_id, tag_id)
billing_records   -- 计费记录 (id, user_id, task_id, action, amount, balance_after, duration_sec, description)
engine_pricing    -- 引擎定价 (engine_key, model_size, credits_per_minute)
anki_push_configs -- Anki推送配置 (id, user_id, push_mode, deck_name, sync_username, sync_password_enc, ankiweb_username, ankiweb_password_enc)
push_records      -- 推送记录 (id, user_id, task_id[nullable], collection_id, config_id, push_mode, deck_name, card_count, skipped_count, status, error_message, duration_ms)
push_record_items -- 推送记录明细 (id, push_record_id, segment_id, status[pushed/skipped/failed], created_at)  [2026-05-26 新增]
public_shares     -- 公共库分享 (id, task_id[unique], user_id, title, description, difficulty, category, duration_tier, cover_url, play_count, like_count, collect_count, is_featured, shared_at)  [2026-05-26 新增]
public_likes      -- 公共库点赞 (user_id, share_id, created_at)  [2026-05-26 新增]
public_collects   -- 公共库收藏 (id, user_id, share_id, collection_id, created_at)  [2026-05-26 新增]
```

### 4.3 代码结构

```
/opt/anki-app/backend/
├── app/
│   ├── main.py          # FastAPI 入口，lifespan + 路由注册 + CORS
│   ├── config.py         # pydantic-settings 配置 (ANKI_ 前缀)
│   ├── database.py       # AsyncEngine + session
│   ├── models.py         # SQLAlchemy 模型
│   ├── schemas.py        # Pydantic schemas
│   ├── schemas_push.py   # Anki 推送 Pydantic schemas
│   ├── deps.py           # 依赖注入 (get_current_user, get_admin_user, _sync_local_user)
│   ├── auth_client.py    # Auth Service HTTP 客户端 (async + sync)
│   ├── billing.py        # 积分计费逻辑 (reserve/settle/refund)
│   ├── worker.py         # 任务处理 Worker (线程池)
│   ├── crypto.py         # AES-CBC 凭证加密/解密
│   └── routers/
│       ├── auth.py       # /api/auth/me + /api/admin/* (用户管理/充值/禁用)
│       ├── billing.py    # /api/billing/* (余额/记录/引擎定价/管理员充值)
│       ├── tasks.py      # /api/tasks/* (任务CRUD/重试/取消)
│       ├── segments.py   # /api/segments/* (片段查询/更新)
│       ├── collections.py# /api/collections/* (收藏集CRUD)
│       ├── tags.py       # /api/tags/* (标签CRUD)
│       ├── anki.py       # /api/anki/* (Anki推送配置/推送/记录)
│       ├── public.py     # /api/public/* (公共库：分享/点赞/收藏/分类/搜索)
│       ├── system.py     # /api/system/* (系统信息)
│       └── ws.py         # /ws/progress (WebSocket 任务进度)
├── alembic/              # 数据库迁移
├── .env                  # 环境变量
└── requirements.txt
```

### 4.4 核心 API 端点

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | /api/health | 无 | 健康检查 |
| GET | /api/auth/me | JWT | 获取当前用户（自动同步 Auth Service） |
| GET | /api/billing/balance | JWT | 查询余额 |
| GET | /api/billing/records | JWT | 查询计费记录 |
| GET | /api/billing/engines | JWT | 查询引擎定价 |
| POST | /api/billing/topup/{user_id} | Admin JWT | 管理员充值（调用 Auth Service） |
| POST | /api/tasks | JWT | 创建任务（自动预扣积分） |
| GET | /api/tasks | JWT | 任务列表 |
| GET | /api/tasks/{id} | JWT | 任务详情（含 segment 推送状态） |
| PATCH | /api/tasks/{id} | JWT | 更新任务 |
| DELETE | /api/tasks/{id} | JWT | 删除任务 |
| POST | /api/tasks/{id}/retry | JWT | 重试任务 |
| POST | /api/tasks/{id}/cancel | JWT | 取消任务 |
| POST | /api/anki/configs | JWT | 创建推送配置 |
| GET | /api/anki/configs | JWT | 推送配置列表 |
| PATCH | /api/anki/configs/{id} | JWT | 更新推送配置 |
| DELETE | /api/anki/configs/{id} | JWT | 删除推送配置 |
| POST | /api/anki/push | JWT | 执行推送（写入 push_record_items） |
| GET | /api/anki/records | JWT | 推送记录 |
| GET | /api/admin/users | Admin JWT | 用户列表 |
| POST | /api/admin/users/{id}/topup | Admin JWT | 管理员充值 |
| PUT | /api/admin/users/{id}/engines | Admin JWT | 修改用户引擎权限 |
| PUT | /api/admin/users/{id}/status | Admin JWT | 启用/禁用用户（调用 Auth Service） |
| GET | /ws/progress?token=xxx | WebSocket | 任务进度推送 |

### 4.5 公共库 API 端点 [2026-05-26 新增]

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | /api/public/shares | JWT | 创建分享（快捷/完整） |
| GET | /api/public/shares | 可选 | 分享列表（支持筛选/排序/搜索） |
| GET | /api/public/shares/{id} | 可选 | 分享详情（含句子列表） |
| PATCH | /api/public/shares/{id} | JWT(所有者) | 更新分享信息 |
| DELETE | /api/public/shares/{id} | JWT(所有者) | 取消分享 |
| POST | /api/public/shares/{id}/like | JWT | 点赞 |
| DELETE | /api/public/shares/{id}/like | JWT | 取消点赞 |
| POST | /api/public/shares/{id}/collect | JWT | 收藏到我的收藏集 |
| DELETE | /api/public/shares/{id}/collect | JWT | 取消收藏 |
| POST | /api/public/shares/{id}/play | 无 | 记录播放 |
| GET | /api/public/categories | 无 | 主题分类列表 |
| GET | /api/public/difficulties | 无 | 难度级别列表 |
| GET | /api/public/tasks | 可选 | 公开任务列表（兼容旧接口） |
| GET | /api/public/tasks/{id}/segments | 无 | 公开句子列表（兼容旧接口） |
| GET | /api/public/tags | 无 | 公开标签列表（兼容旧接口） |
| GET | /api/public/search | 可选 | 全文搜索（兼容旧接口） |

### 4.6 环境变量

```bash
ANKI_DATABASE_URL=postgresql+asyncpg://anki:anki_db_2026_secure@localhost:5432/anki
ANKI_JWT_SECRET=anki-jwt-secret-2026-change-in-prod
ANKI_TASK_DIR=/var/lib/anki/tasks
ANKI_UPLOAD_DIR=/var/lib/anki/uploads
ANKI_CREDENTIAL_ENCRYPTION_KEY=anki-enc-key-32-bytes-change-me!!
ANKI_AUTH_SERVICE_URL=https://auth.3mudi.com
```

---

## 5. Anki 推送机制（重点）

### 5.1 推送架构

```
前端 AnkiView.vue
  │
  ├── POST /api/anki/push { collection_id, push_mode, deck_name }
  │
  ▼
routers/anki.py → push_to_anki()
  │
  ├── 查询 Collection + CollectionItem + Segment
  ├── 构建 segments_data: [{audio_filename, german_text, chinese_text, audio_dir}]
  ├── 收集 segment_ids
  ├── 创建 PushRecord (status=pending)
  │
  ├── run_in_executor → _push_self_hosted_sync() 或 _push_ankiweb_sync()
  │   │
  │   ├── self_hosted 模式:
  │   │   ├── 设置环境变量 ANKI_PUSH_MODE=sync_client
  │   │   ├── 设置 ANKI_SYNC_USERNAME / ANKI_SYNC_PASSWORD (从 config 解密)
  │   │   ├── 调用 anki_push_router.push_cards_to_server()
  │   │   │   ├── ANKI_PUSH_MODE=sync_client → anki_sync_client_push
  │   │   │   │   (Anki 官方同步协议，通过 anki Python 包)
  │   │   │   └── ANKI_PUSH_MODE=direct → anki_sync_push_safe
  │   │   │       (直接操作 SQLite，需停 Docker 容器)
  │   │   └── 返回 {success, count, message}
  │   │
  │   └── ankiweb 模式:
  │       └── 调用 ankiweb_push.push_cards_to_ankiweb()
  │
  ├── 推送成功: 写入 PushRecordItem (status=pushed) × N 条
  ├── 推送失败: 写入 PushRecordItem (status=failed) × N 条
  └── 更新 PushRecord (status=done/failed, card_count, error_message)
```

### 5.2 客户端同步推送流程 (sync_client)

当前默认使用 `sync_client` 模式，通过 Anki 官方同步协议推送卡片：

```
1. 创建本地 Collection 缓存 (/var/lib/anki-sync-client-push/collection.anki2)
2. 通过 Anki Sync 协议登录 (sync_login)
3. 同步下载服务端数据 (sync_collection / full_upload_or_download)
4. 本地添加卡片 (col.add_note)
5. 同步上传到服务端 (sync_collection)
6. 同步媒体文件 (sync_media)
```

依赖：`anki` Python 包（已安装在 /opt/anki-venv），需要 `anki.collection.Collection` 类。

### 5.3 推送配置

| 字段 | 说明 |
|------|------|
| push_mode | `self_hosted` (自建 Anki Sync) 或 `ankiweb` (AnkiWeb) |
| deck_name | 目标牌组名称 |
| sync_username | Anki Sync 用户名 (self_hosted 模式) |
| sync_password_enc | AES 加密的同步密码 |
| ankiweb_username | AnkiWeb 用户名 (ankiweb 模式) |
| ankiweb_password_enc | AES 加密的 AnkiWeb 密码 |

### 5.4 推送脚本说明

| 脚本 | 位置 | 说明 |
|------|------|------|
| `anki_push_router.py` | /opt/anki-app/ | 路由层，根据 ANKI_PUSH_MODE 选择推送方式 |
| `anki_sync_client_push.py` | /opt/anki-app/ | 客户端同步推送（推荐，通过 Anki 官方协议） |
| `anki_sync_push_safe.py` | /opt/anki-app/ | 直接操作 SQLite 推送（需停 Docker，风险较高） |
| `ankiweb_push.py` | /opt/anki-app/ | AnkiWeb 推送 |

> **注意**：这些脚本在 `/opt/anki-app/` 目录下，不在 backend 的 Python 路径中。`routers/anki.py` 通过动态添加 `sys.path` 来导入它们。

### 5.5 sys.path 处理

后端工作目录是 `/opt/anki-app/backend`，而推送脚本在 `/opt/anki-app/`。`_push_self_hosted_sync` 和 `_push_ankiweb_sync` 函数在 import 前动态添加路径：

```python
import sys
anki_app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# /opt/anki-app/backend/app/routers/anki.py → 4层 dirname → /opt/anki-app
if anki_app_dir not in sys.path:
    sys.path.insert(0, anki_app_dir)
```

---

## 6. 推送追踪与公共库功能 [2026-05-26 新增]

### 6.1 已推送句子标示

#### 数据模型

`push_record_items` 关联表记录每次推送中包含的具体 segment：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| push_record_id | UUID | 关联推送记录 |
| segment_id | UUID | 关联句子 |
| status | VARCHAR(20) | pushed/skipped/failed |
| created_at | TIMESTAMP | 记录创建时间 |

#### Segment 推送状态

`SegmentResponse` schema 扩展了两个字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| pushed | bool | 是否已被推送到 Anki |
| last_pushed_at | datetime | 最后推送时间 |

后端在 `routers/tasks.py` 的 `get_task` 中通过查询 `push_record_items` 填充这些字段。

#### Streamlit 历史数据迁移

迁移脚本 `scripts/migrate_streamlit_pushes.py`：
1. 扫描 `/var/lib/anki-streamlit-subtitle/tasks/*/manifest.json`
2. 读取 `favorites` 和 `push_excluded`，计算已推送的句子索引
3. 在 Web App 中创建对应的 Task + Segments（如不存在）
4. 创建收藏集"Streamlit 推送历史 - {upload_name}"
5. 创建 PushRecord + PushRecordItems

```bash
# 运行迁移
cd /opt/anki-app
python scripts/migrate_streamlit_pushes.py --user-email <email>
# 试运行（不写入）
python scripts/migrate_streamlit_pushes.py --user-email <email> --dry-run
```

### 6.2 公共库功能

#### 分类体系

| 维度 | 值 | 来源 |
|------|-----|------|
| 难度 | A1, A2, B1, B2, C1, C2 | 分享时手动选择 |
| 主题 | 新闻, 日常对话, 教材, 备考, 播客, 影视, 商务, 文化, 其他 | 系统预设 |
| 时长 | 短句(<30s), 中篇(30s-3min), 长篇(>3min) | 根据音频时长自动计算 |
| 标签 | 用户自定义 | 延续现有 Tag 系统 |

#### 分享流程

- **快捷分享**：任务详情页 → 点击"📤 分享到公共库" → 自动填充标题和时长分类 → 确认
- **完整分享**：弹出表单，填写标题/描述/难度/分类/标签 → 确认

#### 交互功能

- 点赞/取消点赞（冗余计数 `like_count`）
- 收藏到自己的收藏集（自动复制句子到指定收藏集）
- 播放计数
- 精选标记（管理员 `is_featured`）

#### 前端页面

| 页面 | 路径 | 说明 |
|------|------|------|
| 公共库首页 | /public | 精选推荐 + 难度/分类筛选 + 卡片网格 + 点赞/收藏 |
| 公共库详情 | /public/:id | 句子列表 + 音频播放 + 点赞/收藏 |

---

## 7. 认证集成机制

### 7.1 认证流程

```
1. 用户通过 Auth Service 注册/登录 → 获得 JWT (access_token + refresh_token)
2. 前端携带 access_token 请求 Backend API
3. Backend 调用 Auth Service /api/auth/verify 验证令牌
4. 验证通过后，调用 /api/auth/me 获取完整用户信息
5. 自动同步到本地 users 表（首次自动创建，后续更新）
6. 返回本地 User 对象供业务逻辑使用
```

### 7.2 用户自动同步 (deps.py → _sync_local_user)

当用户首次访问 Backend 时，系统根据 Auth Service 返回的信息自动创建本地用户记录：

| 同步字段 | 来源 | 说明 |
|---------|------|------|
| id | Auth Service user_id | UUID，与 Auth Service 一致 |
| email | Auth Service email | 可为空 |
| phone | Auth Service phone | 可为空 |
| display_name | Auth Service display_name | 显示名称 |
| role | Auth Service role | 角色 (user/admin) |
| credits | Auth Service credits | 积分余额 |
| credits_reserved | Auth Service credits_reserved | 预扣积分 |
| is_active | Auth Service is_active | 是否启用 |

> 每次请求都会同步 credits 和 credits_reserved，确保 Backend 本地数据与 Auth Service 一致。

### 7.3 积分操作流程

```
创建任务时:
  routers/tasks.py → billing.reserve_credits() → auth_client.reserve_credits() → Auth /api/credits/reserve
  ↓
  预扣成功 → 记录 BillingRecord → 设置 task.credits_reserved

任务完成时 (Worker 线程):
  worker.py → billing.settle_credits_sync() → auth_client.settle_credits_sync() → Auth /api/credits/settle
  ↓
  结算成功 → 记录 BillingRecord → 清零 task.credits_reserved

任务失败/取消时:
  worker.py → billing.refund_all_reserved_sync() → auth_client.settle_credits_sync(actual=0) → Auth /api/credits/settle
  ↓
  全额退还 → 记录 BillingRecord → 清零 task.credits_reserved
```

### 7.4 Worker 线程与同步调用

Worker 在独立线程中运行任务，无法使用 async httpx。因此 `billing.py` 提供了 `_sync` 版本的函数，使用 `httpx.Client`（同步）调用 Auth Service：

| 异步函数 | 同步函数 | 使用场景 |
|---------|---------|---------|
| reserve_credits | reserve_credits_sync | FastAPI 路由 / Worker |
| settle_credits | settle_credits_sync | Worker |
| refund_all_reserved | refund_all_reserved_sync | Worker |

### 7.5 Admin 操作

管理员操作（充值、禁用用户）需要 Admin JWT 认证，Backend 通过 `credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)` 获取管理员的 access_token，传递给 Auth Service 管理接口。

---

## 8. 运维操作

### 8.1 服务管理

```bash
# 查看服务状态
sudo systemctl status anki-api
sudo systemctl status auth-service

# 重启服务
sudo systemctl restart anki-api
sudo systemctl restart auth-service

# 健康检查（验证服务是否正常启动）
curl -s http://localhost:8000/api/health     # Backend
curl -s http://localhost:8001/health          # Auth Service

# 查看日志
sudo journalctl -u anki-api -n 100 --no-pager
sudo journalctl -u auth-service -n 100 --no-pager

# 实时跟踪日志
sudo journalctl -u anki-api -f
sudo journalctl -u auth-service -f

# 查看推送错误日志
sudo journalctl -u anki-api --since '10 minutes ago' --no-pager | grep -i -E 'error|fail|push|traceback'
```

### 8.2 数据库操作

```bash
# 连接 anki 数据库
sudo -u postgres psql -d anki

# 连接 auth 数据库
sudo -u postgres psql -d auth

# 查看表结构
sudo -u postgres psql -d anki -c '\d users'
sudo -u postgres psql -d anki -c '\d push_records'
sudo -u postgres psql -d anki -c '\d push_record_items'
sudo -u postgres psql -d anki -c '\d public_shares'
sudo -u postgres psql -d auth -c '\d users'
```

### 8.3 部署更新

```bash
# 1. 本地上传文件 (Windows)
& "C:\Windows\System32\OpenSSH\scp.exe" -i "D:/00_dev/04_key/ssh-key-2026-04-18_Oracle_Frankfurt.key" -o StrictHostKeyChecking=no <local_file> ubuntu@89.168.93.94:/tmp/<filename>

# 2. 服务器上复制到目标位置
sudo cp /tmp/<filename> /opt/anki-app/backend/app/<filename>
# 或
sudo cp /tmp/<filename> /opt/auth-service/app/<filename>

# 3. 重启服务
sudo systemctl restart anki-api
# 或
sudo systemctl restart auth-service

# 4. 前端更新（需要重新构建）
sudo cp /tmp/<filename>.vue /opt/anki-app/frontend/src/views/<filename>.vue
cd /opt/anki-app/frontend && npm run build
```

### 8.4 数据库迁移

Auth Service 使用 Alembic：
```bash
cd /opt/auth-service
/opt/auth-service/.venv/bin/alembic upgrade head
```

Backend 当前使用直接 SQL 迁移（无 alembic.ini），迁移脚本示例：
```bash
# 上传 SQL 文件
scp scripts/migration_003.sql ubuntu@89.168.93.94:/tmp/

# 执行迁移
sudo -u postgres psql -d anki -f /tmp/migration_003.sql

# 修复表权限（新表 owner 需改为 anki）
sudo -u postgres psql -d anki -c 'ALTER TABLE <table_name> OWNER TO anki;'
```

> **重要**：通过 `sudo -u postgres` 创建的表 owner 是 `postgres`，需要手动改为 `anki`，否则应用会报 `permission denied` 错误。

### 8.5 SSL 证书续期

```bash
sudo certbot renew
sudo nginx -t && sudo systemctl reload nginx
```

---

## 9. Nginx 配置要点

### 9.1 auth.3mudi.com

- `/api/` → proxy_pass http://127.0.0.1:8001
- `/health` → proxy_pass http://127.0.0.1:8001/health
- `/docs` → proxy_pass http://127.0.0.1:8001/docs (Swagger UI)
- `/` → 返回 404（Auth Service 不提供前端页面）

### 9.2 anki.3mudi.com

- `/api/` → proxy_pass http://127.0.0.1:8000 (Backend API)
- `/` → root /opt/anki-app/frontend/dist (Frontend SPA)
- `/assets/` → 静态资源，缓存 30 天
- `/sync/` `/msync/` → proxy_pass http://127.0.0.1:8080 (Anki Sync Server)
- `/legacy/` → proxy_pass http://127.0.0.1:8501 (Streamlit)
- `/media/` `/v2-media/` → 静态音频文件
- `client_max_body_size 500m` (支持大文件上传)

---

## 10. 已知问题与注意事项

### 10.1 Backend 调用 Auth Service 走外网

当前 `ANKI_AUTH_SERVICE_URL=https://auth.3mudi.com`，Backend 调用 Auth Service 经过 Cloudflare。服务器自身 curl 访问会被 Cloudflare 拦截 (403 error 1010)。

**建议**：改为 `http://localhost:8001`，避免 Cloudflare 拦截和 SSL 开销。修改步骤：
1. 编辑 `/opt/anki-app/backend/.env`，将 `ANKI_AUTH_SERVICE_URL=https://auth.3mudi.com` 改为 `ANKI_AUTH_SERVICE_URL=http://localhost:8001`
2. 重启 Backend：`sudo systemctl restart anki-api`
3. 验证：`curl -s http://localhost:8000/api/health`

### 10.2 ~~短信服务处于开发模式~~（已切换正式）

短信服务已切换为阿里云正式模式（`AUTH_SMS_PROVIDER=aliyun`），签名：速通互联验证服务。

### 10.3 JWT Secret 安全性

以下 Secret 仍为开发默认值，生产环境应更换：
- `ANKI_JWT_SECRET=anki-jwt-secret-2026-change-in-prod`
- `AUTH_JWT_SECRET=3mudi-auth-jwt-secret-2026-prod`
- `ANKI_CREDENTIAL_ENCRYPTION_KEY=anki-enc-key-32-bytes-change-me!!`

### 10.4 数据库密码

数据库密码在 `.env` 文件中，建议定期更换并使用更安全的密码管理方案。

### 10.5 旧用户迁移

原有 Backend users 表中的用户（注册于 Auth 整合前）没有对应的 Auth Service 账号。这些用户需要重新通过 Auth Service 注册。旧密码已无法使用（password_hash 列已删除）。

**迁移方案**：对于需要保留的旧用户，管理员可通过 Auth Service 管理接口手动创建账号（`POST /api/admin/users`），并设置初始积分与旧系统一致。

### 10.6 Anki 推送并发限制

Anki 推送使用 `SimpleFileLock` 实现文件锁（`/var/lib/anki-sync-client-push/collection.anki2.lock`），同一时间只能有一个推送操作执行。如果锁超时（默认 120 秒），会抛出 `AnkiSyncClientPushError`。

### 10.7 V1 遗留代码

项目根目录 `/opt/anki-app/` 下存在 V1 版本（Streamlit）的遗留文件，部分仍被 V2 Worker 调用：

| 文件 | 状态 | 说明 |
|------|------|------|
| `anki_push_router.py` | ✅ V2 使用 | 推送路由层 |
| `anki_sync_client_push.py` | ✅ V2 使用 | 客户端同步推送 |
| `anki_sync_push_safe.py` | ✅ V2 使用 | 直接 SQLite 推送 |
| `ankiweb_push.py` | ✅ V2 使用 | AnkiWeb 推送 |
| `align_and_cut.py` | ✅ V2 Worker 调用 | 音频对齐切割 |
| `normalize_audio.py` | ✅ V2 Worker 调用 | 音频标准化 |
| `whisper_timestamps.py` | ✅ V2 Worker 调用 | Whisper 时间戳提取 |
| `openai_whisper_api.py` | ✅ V2 Worker 调用 | OpenAI Whisper API |
| `cohere_asr.py` | ✅ V2 Worker 调用 | Cohere ASR |
| `app.py` / `app_v2.py` | ❌ 废弃 | Streamlit V1/V2 |
| `app_subtitle.py` | ⚠️ 仍可运行 | Streamlit 字幕 beta 版 |

### 10.8 数据库表权限

通过 `sudo -u postgres psql` 创建的新表 owner 是 `postgres`，而应用使用 `anki` 用户连接数据库。每次创建新表后必须执行：

```sql
ALTER TABLE <table_name> OWNER TO anki;
ALTER INDEX <index_name> OWNER TO anki;
```

否则会报 `permission denied for table <table_name>` 错误。

---

## 11. 变更记录

### 2026-05-26 BUG 修复

#### 修复 1：收藏集页面无内容显示

**问题**：`/collections` 页面显示空白，有调试代码残留。

**根因**：
1. `CollectionsView.vue` 残留调试信息框（黄色背景），影响用户体验
2. `App.vue` 有粉色调试条显示路由和用户信息
3. 缺少"新建收藏集"功能入口

**修复**：
- 移除 `CollectionsView.vue` 调试代码，重构为 `n-card + n-list + n-spin` 布局
- 添加"新建收藏集"按钮和创建 Modal
- 移除 `App.vue` 调试条

**涉及文件**：
- `frontend/src/views/CollectionsView.vue`
- `frontend/src/App.vue`

#### 修复 2：Anki 推送失败

**问题**：推送操作返回"推送失败"。

**根因（多层）**：
1. **字段名不匹配**：`routers/anki.py` 使用 `cards_pushed`、`started_at`、`finished_at`、`error`，但 `PushRecord` 模型实际字段是 `card_count`、`created_at`、`error_message`（无 `finished_at`），导致 `TypeError`
2. **推送方式错误**：原代码通过 `subprocess` 调用 `anki_sync_push.py --cards-file`，但该脚本不支持此参数；应使用 `anki_push_router.push_cards_to_server()` 走客户端同步协议
3. **sys.path 缺失**：后端工作目录 `/opt/anki-app/backend`，推送脚本在 `/opt/anki-app/`，需动态添加 `sys.path`
4. **阻塞事件循环**：同步推送函数在 async 路由中直接调用会阻塞，需 `run_in_executor`
5. **task_id NOT NULL 约束**：`push_records.task_id` 为 NOT NULL，但推送从收藏集发起不一定关联 task

**修复**：
- 修正 `PushRecordResponse` schema 字段名与模型对齐
- 改用 `anki_push_router.push_cards_to_server()` + `ANKI_PUSH_MODE=sync_client`
- 从 config 解密并设置 `ANKI_SYNC_USERNAME` / `ANKI_SYNC_PASSWORD`
- 动态添加 `sys.path`（4 层 dirname → `/opt/anki-app`）
- 使用 `loop.run_in_executor()` 在线程池中执行同步推送
- 数据库修改 `push_records.task_id` 为 nullable
- 前端 `AnkiView.vue` 字段名同步更新

**涉及文件**：
- `backend/app/routers/anki.py`
- `backend/app/schemas_push.py`
- `backend/app/models.py`
- `frontend/src/views/AnkiView.vue`
- 数据库 DDL：`ALTER TABLE push_records ALTER COLUMN task_id DROP NOT NULL`

### 2026-05-26 功能新增：推送追踪 + 公共库

#### 功能 1：已推送句子标示

**需求**：Streamlit 和 Web App 中推送过的句子没有被标示，需要精确追踪推送状态。

**实现**：
- 新增 `push_record_items` 关联表，记录每次推送中每个 segment 的状态
- `SegmentResponse` 扩展 `pushed` + `last_pushed_at` 字段
- 推送时自动写入 `push_record_items`（成功=pushed，失败=failed）
- 任务详情 API 查询推送状态填充 `pushed` 和 `last_pushed_at`
- 前端收藏集详情页显示"已推送"标签
- Streamlit 历史数据迁移脚本 `scripts/migrate_streamlit_pushes.py`

**涉及文件**：
- `backend/app/models.py` — 新增 PushRecordItem 模型
- `backend/app/schemas.py` — SegmentResponse 扩展
- `backend/app/routers/anki.py` — 推送时写入 push_record_items
- `backend/app/routers/tasks.py` — 查询推送状态
- `frontend/src/views/CollectionDetailView.vue` — 推送状态标签
- `scripts/migrate_streamlit_pushes.py` — 迁移脚本

#### 功能 2：公共库

**需求**：构建完整的公共库功能，参考"每日德语听力"APP，支持四维分类、分享、点赞、收藏。

**实现**：
- 新增 `public_shares`、`public_likes`、`public_collects` 三张表
- `tags` 表扩展 `is_system` + `tag_type` 字段
- 四维分类：难度 A1-C2、主题9类、时长3档、用户自定义标签
- 手动+快捷分享双模式
- 点赞/取消点赞、收藏到收藏集、播放计数
- 公共库首页重构（精选推荐 + 分类筛选 + 卡片网格）
- 新增公共库详情页（句子列表 + 音频播放 + 交互）
- 任务详情页新增"分享到公共库"按钮和表单
- 16 个新 API 端点

**涉及文件**：
- `backend/app/models.py` — 新增 PublicShare/PublicLike/PublicCollect 模型，Tag 扩展
- `backend/app/schemas.py` — 新增公共库 Schema
- `backend/app/routers/public.py` — 完整重写，16 个 API 端点
- `backend/alembic/versions/003_push_tracking_and_public.py` — 迁移
- `frontend/src/api/public.js` — 新增 14 个 API 函数
- `frontend/src/views/PublicView.vue` — 重构
- `frontend/src/views/PublicDetailView.vue` — 新增
- `frontend/src/views/TaskDetailView.vue` — 分享功能
- `frontend/src/router/index.js` — 新增路由

**数据库迁移**：`scripts/migration_003.sql`

---

## 12. 端到端测试验证

以下测试已在服务器上执行并通过：

| 步骤 | 测试项 | 结果 |
|------|--------|------|
| 1 | Auth Service 邮箱注册 | ✅ 返回 JWT + 用户信息 |
| 2 | Auth Service 密码登录 | ✅ 返回 JWT |
| 3 | Auth Service Token 验证 | ✅ 返回 user_id, credits |
| 4 | Backend /api/auth/me 用户同步 | ✅ 自动创建本地用户 |
| 5 | Backend /api/billing/balance | ✅ 返回余额信息 |
| 6 | Auth Service 积分充值 (topup 100) | ✅ credits=100.00 |
| 7 | Auth Service 积分预扣 (reserve 5) | ✅ credits=100, reserved=5 |
| 8 | Auth Service 积分结算 (settle 3) | ✅ credits=97, refund=2 |
| 9 | Auth Service 积分退还 (refund 1) | ✅ credits=98 |
| 10 | Backend /api/auth/me 积分同步 | ✅ credits 与 Auth Service 一致 |
| 11 | 收藏集页面显示 | ✅ 列表和新建功能正常 |
| 12 | Anki 推送 (sync_client) | ✅ 通过 Anki 官方同步协议推送 |
| 13 | 公共库分类 API | ✅ 返回 9 个分类 + 6 个难度级别 |
| 14 | 公共库分享列表 API | ✅ 返回空列表（正常） |
| 15 | 前端公共库页面 | ✅ HTTP 200 |

测试脚本位置：`d:\00_dev\anki-app\scripts\e2e_test.py`

---

## 13. 本地开发指南

### 13.1 代码仓库

| 项目 | 本地路径 |
|------|---------|
| Backend | d:\00_dev\anki-app\backend |
| Auth Service | d:\00_dev\anki-app\auth-service |
| Frontend | d:\00_dev\anki-app\frontend |
| 推送脚本 | d:\00_dev\anki-app (根目录) |

### 13.2 本地开发环境

```bash
# Backend
cd d:\00_dev\anki-app\backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Auth Service
cd d:\00_dev\anki-app\auth-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# Frontend
cd d:\00_dev\anki-app\frontend
npm install
npm run dev
```

### 13.3 关键配置项

Backend 需要配置 `ANKI_AUTH_SERVICE_URL` 指向 Auth Service：
- 本地开发：`http://localhost:8001`
- 生产环境：`https://auth.3mudi.com`（或 `http://localhost:8001` 同服务器部署）

---

## 附录 A：服务端口映射

| 端口 | 服务 | 外部访问 |
|------|------|---------|
| 80/443 | Nginx | ✅ 通过域名 |
| 8000 | Backend (uvicorn) | ❌ 仅 Nginx 代理 |
| 8001 | Auth Service (uvicorn) | ❌ 仅 Nginx 代理 |
| 8080 | Anki Sync Server (Docker) | ❌ 仅 Nginx 代理 |
| 8501 | Streamlit | ❌ 仅 Nginx 代理 |

## 附录 B：systemd 服务清单

| 服务名 | 描述 | 自动启动 |
|--------|------|---------|
| anki-api.service | Backend FastAPI | ✅ enabled |
| auth-service.service | Auth Service | ✅ enabled |
| anki-streamlit-v2.service | Streamlit UI (V1 legacy) | ✅ enabled |

## 附录 C：关键文件路径

| 文件 | 路径 |
|------|------|
| Backend .env | /opt/anki-app/backend/.env |
| Auth .env | /opt/auth-service/.env |
| Nginx anki 配置 | /etc/nginx/sites-enabled/anki.3mudi.com |
| Nginx auth 配置 | /etc/nginx/sites-enabled/auth.3mudi.com.conf |
| Backend systemd | /etc/systemd/system/anki-api.service |
| Auth systemd | /etc/systemd/system/auth-service.service |
| SSL 证书 anki | /etc/letsencrypt/live/anki.3mudi.com/ |
| SSL 证书 auth | /etc/letsencrypt/live/auth.3mudi.com/ |
| 任务文件目录 | /var/lib/anki/tasks |
| 上传文件目录 | /var/lib/anki/uploads |
| 前端静态文件 | /opt/anki-app/frontend/dist |
| Anki Sync 数据卷 | /var/lib/docker/volumes/anki-cloud_app-data/_data/anki_user/ |
| 推送客户端缓存 | /var/lib/anki-sync-client-push/ |
| 数据库迁移 SQL | /opt/anki-app/scripts/migration_003.sql |
| Streamlit 迁移脚本 | /opt/anki-app/scripts/migrate_streamlit_pushes.py |

## 附录 D：推送数据格式

推送脚本期望的卡片数据格式：

```python
sentences = [
    {
        "audio_filename": "clip_001.mp3",   # 音频文件名（在 audio_dir 中）
        "german_text": "Ich liebe Deutsch",  # 德语文本
        "chinese_text": "我爱德语",           # 中文翻译
    }
]
```

Anki 卡片格式（Basic 笔记类型）：
- Front: `[sound:clip_001.mp3]`
- Back: `Ich liebe Deutsch\n\n我爱德语`

或（Audio/German/Chinese 笔记类型）：
- Audio: `[sound:clip_001.mp3]`
- German: `Ich liebe Deutsch`
- Chinese: `我爱德语`

## 附录 E：公共库分类体系

### 难度级别

| 键值 | 显示名 | 说明 |
|------|--------|------|
| A1 | 入门 | 简单日常用语，短句，慢速 |
| A2 | 初级 | 基础对话，常用词汇 |
| B1 | 中级 | 日常交流无障碍，中等语速 |
| B2 | 中高级 | 复杂话题，较快语速 |
| C1 | 高级 | 学术/专业内容，接近母语语速 |
| C2 | 精通 | 高级学术/文学，母语级别 |

### 主题分类

| 键值 | 显示名 |
|------|--------|
| news | 新闻 |
| daily | 日常对话 |
| textbook | 教材 |
| exam | 备考 |
| podcast | 播客 |
| movie | 影视 |
| business | 商务 |
| culture | 文化 |
| other | 其他 |

### 时长分类

| 键值 | 显示名 | 范围 |
|------|--------|------|
| short | 短句 | < 30秒 |
| medium | 中篇 | 30秒 - 3分钟 |
| long | 长篇 | > 3分钟 |

## 附录 F：数据模型关系图

```
users
  ├── tasks (1:N)
  │     ├── segments (1:N)
  │     │     ├── collection_items (1:N)  ──→ collections
  │     │     └── push_record_items (1:N) ──→ push_records
  │     ├── task_tags (N:M) ──→ tags
  │     └── public_shares (1:1)
  ├── collections (1:N)
  │     └── collection_items (1:N) ──→ segments
  ├── anki_push_configs (1:N)
  ├── push_records (1:N)
  │     └── push_record_items (1:N) ──→ segments
  ├── public_shares (1:N)
  ├── public_likes (N:M) ──→ public_shares
  └── public_collects (1:N) ──→ public_shares + collections
```
