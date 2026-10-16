# Anki 德语听力平台 — Code Wiki

> 最后更新：2026-10-13（基于当前代码库重新梳理，替代 2026-05 旧版）

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构](#2-整体架构)
3. [仓库目录结构](#3-仓库目录结构)
4. [后端 backend（FastAPI）](#4-后端-backendfastapi)
5. [音频处理管线（根目录 Python 模块）](#5-音频处理管线根目录-python-模块)
6. [Anki 推送子系统](#6-anki-推送子系统)
7. [前端 frontend（Vue 3 SPA）](#7-前端-frontendvue-3-spa)
8. [移动端 anki-swipe-app（Expo React Native）](#8-移动端-anki-swipe-appexpo-react-native)
9. [遗留 Streamlit 应用](#9-遗留-streamlit-应用)
10. [数据模型](#10-数据模型)
11. [关键业务流程](#11-关键业务流程)
12. [外部依赖关系](#12-外部依赖关系)
13. [运行与部署](#13-运行与部署)
14. [测试与运维脚本](#14-测试与运维脚本)

---

## 1. 项目概述

这是一个**德语听力学习平台**：用户上传德语音频 → ASR 转写为带时间戳的句子 → 自动切割音频片段并翻译成中文 → 用户挑选句子组成收藏集 → 一键推送为 Anki 卡片（含音频）。平台还包含：

- **积分计费系统**：按音频时长 + 引擎费率扣费，余额/钱包托管在外部 auth-service
- **公共分享社区**：任务可公开分享，支持播放/点赞/收藏/全文搜索
- **滑动复习（Swipe）**：类 Tinder 的卡片流学习，带自适应难度算法（Web 移动端 + Expo App）
- **后台管理**：用户管理、充值审核、引擎定价、帮助文章管理

### 技术栈一览

| 层 | 技术 |
|---|---|
| 后端 | FastAPI 2.0 + SQLAlchemy 2 (async) + PostgreSQL 16 + Alembic |
| 后台任务 | 进程内线程池 Worker（`TaskWorkerV2` / `TranscribeWorker`） |
| ASR | faster-whisper（本地）、OpenAI Whisper API、Cohere ASR |
| 翻译 | deep-translator（Google 翻译 de→zh-CN） |
| Web 前端 | Vue 3 + Vite + Naive UI + Pinia + Vue Router + axios |
| 移动端 | Expo SDK 56 / React Native 0.85 + expo-router + zustand + reanimated |
| Anki 集成 | anki (anki-rs Python 绑定) 直连 collection + sync server / AnkiWeb |
| 部署 | Docker Compose（db / backend / frontend-nginx）+ systemd + Nginx |

### 生产环境

- 站点：`https://anki.3mudi.com`
- 外部认证/钱包服务：`https://auth.3mudi.com`（独立部署的 auth-service，本仓库不含其代码）

---

## 2. 整体架构

```
┌────────────────────────────────────────────────────────────────────┐
│                          客户端层                                   │
│  Vue 3 SPA (frontend/dist)      Expo App / Web (anki-swipe-app)    │
│  由 backend 直接托管            web build 托管在 /swipe 路径         │
└──────────────┬───────────────────────────────┬─────────────────────┘
               │ HTTPS /api (+/ws 进度推送)     │
┌──────────────▼───────────────────────────────▼─────────────────────┐
│                backend (FastAPI, uvicorn)                           │
│  routers: auth/tasks/segments/collections/tags/billing/recharge/    │
│           public/anki/help/swipe/transcribe/system/email/ws         │
│                                                                     │
│  进程内 Worker 线程池:                                              │
│   ├─ TaskWorkerV2  (本地队列 + 远程队列, 各 max_workers=2)          │
│   │    └─ 管线: normalize → ASR → align_and_cut → 翻译 → 落库       │
│   └─ TranscribeWorker (单线程 FIFO, 纯文本转写, Cohere)             │
└───────┬──────────────────┬──────────────────────┬──────────────────┘
        │ asyncpg          │ httpx                │ subprocess/本地库
┌───────▼───────┐  ┌───────▼────────┐   ┌─────────▼──────────────────┐
│ PostgreSQL 16 │  │ auth-service   │   │ 处理管线 (仓库根目录)       │
│ (tasks,       │  │ auth.3mudi.com │   │ normalize_audio.py (ffmpeg)│
│  segments,    │  │ - 认证/JWT     │   │ whisper_timestamps.py      │
│  billing...)  │  │ - 积分钱包     │   │ cohere_asr.py              │
└───────────────┘  │ - 邮件验证码   │   │ openai_whisper_api.py      │
                   └────────────────┘   │ align_and_cut.py (pydub)   │
                                        │ anki_sync_client_push.py   │
                   ┌────────────────┐   │ ankiweb_push.py            │
                   │ Anki 同步目标  │◄──┤ (anki 库直连 collection)   │
                   │ - 自建 sync    │   └────────────────────────────┘
                   │ - AnkiWeb      │
                   └────────────────┘
```

**关键架构决策**

- **认证与钱包外置**：本系统不存密码、不扣自己的积分账。所有 token 校验、积分预扣/结算/退款、邮件发送都通过 `auth_client.py` / `email_service.py` 调用外部 auth-service，本地 `users` 表只是镜像（首次访问时自动同步创建，见 `deps._sync_local_user`）。
- **Worker 进程内嵌**：不用 Celery/Redis，任务队列就是 Python 线程 + list；重启时通过 lifespan 扫描 `stage IN (pending/normalizing/transcribing/translating)` 的任务自动恢复。
- **取消机制**：在任务目录写入 `cancel.json` 标记文件，worker 各阶段轮询检查。
- **进度推送**：worker 线程通过 `asyncio.run_coroutine_threadsafe` 把进度发到 FastAPI 事件循环上的 WebSocket（`routers/ws.py`）。

---

## 3. 仓库目录结构

```
g:\95_dev\anki-app
├── backend/                  # FastAPI 后端（核心，见 §4）
│   ├── app/
│   │   ├── main.py           # 应用入口、lifespan、路由注册、SPA 托管
│   │   ├── config.py         # Settings（ANKI_ 前缀环境变量）
│   │   ├── database.py       # async engine / session
│   │   ├── models.py         # 全部 SQLAlchemy 模型（21 张表）
│   │   ├── schemas*.py       # Pydantic 模型（主/push/swipe/help）
│   │   ├── deps.py           # 认证依赖、本地用户同步
│   │   ├── auth_client.py    # 外部 auth-service HTTP 客户端
│   │   ├── billing.py        # 计费编排（估价/预扣/结算/退款/扣费）
│   │   ├── worker.py         # TaskWorkerV2：音频任务管线执行器
│   │   ├── transcribe_worker.py  # 单线程纯转写 worker（Cohere）
│   │   ├── crypto.py         # AES 加密（Anki 凭据落库）
│   │   ├── email_service.py  # 邮件验证码（代理到 auth-service）
│   │   └── routers/          # 16 个路由模块（见 §4.3）
│   ├── alembic/              # 4 个迁移版本
│   ├── tests/                # pytest（模型/路由/计费/加密/邮件/swipe）
│   └── scripts/              # seed_help_articles、fix_orphan_reserves
│
├── frontend/                 # Vue 3 SPA（见 §7）
│   ├── src/{views,api,stores,router,components}
│   ├── nginx.conf  Dockerfile  vite.config.js  vitest.config.js
│
├── anki-swipe-app/           # Expo RN 滑动学习 App（见 §8）
│   ├── app/                  # expo-router 页面（swipe/login/settings/stats）
│   ├── components/           # SwipeDeck/SwipeCard/AudioProgressBar...
│   ├── services/             # api.ts / auth.ts / audioCache.ts
│   └── store/swipeStore.ts   # zustand 状态
│
├── 音频处理管线（根目录，被 backend worker 以 subprocess/import 调用）
│   ├── normalize_audio.py    # ffmpeg 标准化为 16k mono mp3
│   ├── whisper_timestamps.py # faster-whisper 词级时间戳提取
│   ├── cohere_asr.py         # Cohere ASR 封装
│   ├── openai_whisper_api.py # OpenAI Whisper API 封装
│   └── align_and_cut.py      # 静音检测、文本对齐、句子级音频切割
│
├── Anki 推送（根目录，被 routers/anki.py 在线程池调用）
│   ├── anki_sync_client_push.py  # 自建 sync server 模式
│   ├── ankiweb_push.py           # AnkiWeb 模式
│   └── anki_sync_push*.py, anki_api.py  # 旧版/直连工具
│
├── 遗留 Streamlit 应用（见 §9）
│   ├── app.py  app_v2.py  app_subtitle.py  task_worker.py
│
├── scripts/                  # 部署/迁移/验证 shell + python 脚本
├── tools/                    # TTS 任务构建等一次性工具
├── docs/                     # 设计文档（V2 重构方案、交接文档等）
├── models/                   # faster-whisper 模型缓存
├── docker-compose.yml        # db + backend + frontend 三服务
├── nginx-anki-merged.conf    # 生产 nginx 配置
└── exports/ output/ backups/ # 数据导出/输出/备份
```

---

## 4. 后端 backend（FastAPI）

### 4.1 入口与生命周期 — `backend/app/main.py`

- 应用：`FastAPI(title="Anki Audio Processing API", version="2.0.0")`
- **lifespan 启动流程**：
  1. 创建 `TASK_DIR` / `UPLOAD_DIR`
  2. `CREATE EXTENSION pg_trgm` + `Base.metadata.create_all` + 为 `segments.german_text/chinese_text` 建 trigram GIN 索引（支撑公共库全文搜索）
  3. 记录主事件循环到 `settings._async_loop`（供 worker 线程回投 WS 消息）
  4. **恢复未完成任务**：扫描处于中间态的 Task → 重置为 pending → 清除 `cancel.json` → 重新提交给 worker
- **静态托管**：`/api/audio` → 任务音频目录；`/assets` + catch-all → 前端 SPA（`FRONTEND_DIST`）
- CORS 白名单：`anki.3mudi.com`、`auth.3mudi.com`、localhost:3000/5173

### 4.2 配置 — `backend/app/config.py`

`Settings`（pydantic-settings，环境变量前缀 `ANKI_`）：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` / `DATABASE_URL_SYNC` | postgresql(+asyncpg)://... | 异步/同步双连接串（worker 线程用同步） |
| `JWT_*` | HS256, 1440min | JWT 参数（实际校验在 auth-service） |
| `TASK_DIR` / `UPLOAD_DIR` | /var/lib/anki/{tasks,uploads} | 任务产物/上传目录 |
| `WORKER_MAX` | 2 | 本地与远程队列各自的并发线程数 |
| `CREDENTIAL_ENCRYPTION_KEY` | — | Anki 凭据 AES 密钥（`crypto.py`） |
| `AUTH_SERVICE_URL` | https://auth.3mudi.com | 外部认证/计费服务 |
| `SYNC_*` / `PUSH_MODE` | 127.0.0.1:8080 / sync_client | 默认 Anki 同步目标 |
| `FRONTEND_DIST` | /opt/anki-app/frontend/dist | SPA 构建产物路径 |
| `COHERE_DEVICE` | cpu | Cohere ASR 运行设备 |

### 4.3 路由模块（全部挂在 `/api` 下）

| 模块 | 前缀 | 职责与主要端点 |
|---|---|---|
| `routers/auth.py` | `/auth` + `/admin` | `GET /auth/me`；管理员：用户列表、充值、引擎授权、启停号、推送配置上限于 |
| `routers/tasks.py` | `/tasks` | **核心入口**：`POST /tasks`（上传+查重+估价+余额校验+提交 worker）、列表/详情/编辑/删除/`retry`/`cancel` |
| `routers/segments.py` | `/segments` | 片段列表、文本修改、`POST /{id}/translate`（Google 翻译单句重译） |
| `routers/collections.py` | `/collections` | 收藏集 CRUD、批量删除、集内句子增删、`push_enabled` 开关 |
| `routers/tags.py` | `/tags` | 标签 CRUD、任务打标/查询 |
| `routers/billing.py` | `/billing` | 余额查询（代理 auth-service）、账单流水、引擎定价表、管理员 topup |
| `routers/recharge.py` | `/recharge` | 线下充值：付款码图、上传凭证（hash 去重）、我的申请、管理员审核 |
| `routers/public.py` | `/public` | 公开库：分享 CRUD、分页/分类/难度过滤、点赞/收藏/播放计数、**trigram 全文搜索** `/public/search` |
| `routers/anki.py` | `/anki` | 推送配置 CRUD（上限 `user.max_push_configs`）、**`POST /anki/push`**（按收藏集推送卡片，按 config 去重已推送片段）、`push-status` 探测、`records` 推送历史 |
| `routers/swipe.py` | `/swipe` | 滑动学习：`GET /feed`（自适应难度喂卡）、`POST /rate`、`POST /collect`、`GET /stats` |
| `routers/transcribe.py` | `/transcribe` | 纯文本转写（上传→`TranscribeWorker`→轮询结果） |
| `routers/system.py` | `/system` | 引擎列表/定价管理、系统设置（如系统级 OpenAI key）、健康检查 |
| `routers/help.py` | `/help` + `/admin/help` | 帮助文章：公开按分类/slug 阅读；管理员 CRUD |
| `routers/email.py` | `/email` | 发送/校验邮件验证码 |
| `routers/ws.py` | `/ws/progress` | WebSocket：按 user_id 推送任务进度（`ConnectionManager`） |

### 4.4 核心服务模块

#### `deps.py` — 认证与用户同步

- `get_current_user`：Bearer token → `auth_client.verify_token` → `get_user_info` → `_sync_local_user` 把 auth-service 的用户镜像到本地 `users` 表（含 **UUID 迁移**逻辑：同邮箱旧 UUID 用户整体换绑到新 UUID，级联更新 6 张外键表）
- `get_admin_user`：要求 `role == "admin"`
- `get_optional_user`：匿名友好（public/swipe 用）

#### `auth_client.py` — 外部服务客户端

对 auth-service 的全部 HTTP 调用，每个函数都有 async + sync 双版本（sync 版供 worker 线程）：

- 认证：`verify_token`、`get_user_info`、`reset_password`
- 积分：`reserve_credits` / `settle_credits` / `refund_credits` / `charge_credits`（= reserve+settle 同额）/ `get_credits_balance`
- 管理：`admin_add_credits`、`admin_toggle_active`
- 402 → 解析为"余额不足"业务错误；网络错误返回 `None`（上层降级为"计费服务暂不可用"）

#### `billing.py` — 计费编排

两种模式并存：

- **旧模式（reserve/settle）**：`reserve_credits*`（提交任务时预扣）→ `settle_credits*`（完工按实际时长结算，多退）→ `refund_all_reserved*`（失败/取消全退）
- **新模式（check + charge）**：`check_balance` + `estimate_cost`（提交前预估校验）→ `charge_credits*`（完工后按 `file_duration_sec × credits_per_minute` 直接扣）
- 费率来自 `engine_pricing` 表（缺省 1.0 积分/分钟）；金额按分钟向上取整到 0.01
- 每次变动都写 `billing_records`（action: reserve/settle/refund/charge/topup）

#### `worker.py` — 音频任务执行器（核心）

- `TaskWorkerV2`：**双队列线程池**——本地引擎（local_whisper/cohere）与远程引擎（openai_whisper）各占 `WORKER_MAX` 个线程，互不挤占
- `_run_pipeline(task_id, ...)` 管线：
  1. `normalizing`：subprocess 调 `normalize_audio.py`（ffmpeg → 16kHz mono 96k mp3）；`skip_normalize` 时建软链
  2. `transcribing`：`_build_transcriber` 按引擎选 ASR → whisper 系走 `align_and_cut.process_pipeline` 得句子+切割 clips；cohere 只出全文（不切割不翻译）
  3. `translating`：`deep_translator.GoogleTranslator` de→zh-CN 批量翻译，写入 `segments`
  4. `done`：pydub 测时长 → 先退旧预扣 → 按新模式 `charge_credits_sync` 扣实际费用
- **取消**：任务目录出现 `cancel.json` 即抛 `_CancelRequested`（含 ffmpeg 子进程终止）
- **进度广播**：`_broadcast_progress` → `run_coroutine_threadsafe` → WS
- 各异常分支都会尝试退还残留预扣款

#### `transcribe_worker.py` — 纯文本转写

单线程 FIFO（队列上限 10），懒加载 Cohere ASR 模型，结果写 `transcriptions` 表，完成后删除临时文件。

#### `crypto.py` / `email_service.py`

- `crypto`：SHA256 派生密钥 + AES-CBC，加解密 AnkiWeb/sync 密码（`AnkiPushConfig.*_password_enc`）
- `email_service`：调 auth-service 内部 API（`http://127.0.0.1:9000`，SERVICE_KEY 鉴权）发验证码

---

## 5. 音频处理管线（根目录 Python 模块）

被 `backend/app/worker.py` 通过 `sys.path` 注入项目根后 import / subprocess 调用。

| 模块 | 关键类/函数 | 说明 |
|---|---|---|
| `normalize_audio.py` | CLI `--input --output --sample-rate 16000 --bitrate 96k --mono` | ffmpeg 封装，统一音频格式 |
| `whisper_timestamps.py` | `WhisperTimestampExtractor(model_size, device, compute_type)` | faster-whisper 词级时间戳转写 |
| `openai_whisper_api.py` | `OpenAIWhisperAPI(api_key)` | OpenAI Whisper API 远程转写（key 可由用户提交或系统设置兜底） |
| `cohere_asr.py` | `CohereASR(device)` | Cohere ASR，仅全文转写 |
| `align_and_cut.py` | `process_pipeline(audio, subs, transcriber, clips_dir, ...)`、`detect_speech_chunks` | **对齐与切割核心**：静音检测分块（5–45s）→ ASR → SequenceMatcher 文本对齐 → 句子级时间轴 → pydub 切出 `clip_NNN.mp3` |

另有 `audio_normalize.py` / `normalize.py` / `normalize_gui.py`（+ `音频标准化工具.spec`）：独立的 PyInstaller 桌面音频标准化小工具，与主管线无关。

---

## 6. Anki 推送子系统

`routers/anki.py` 的 `POST /api/anki/push` 流程：

1. 校验收藏集归属，取 `push_enabled` 的 CollectionItem → 组装 segment 数据（音频路径、德/中文本）
2. 每个推送配置（`AnkiPushConfig`）独立推送；**去重**：查 `PushRecord(status=done)` + `PushRecordItem(status=pushed)`，已推过的句子跳过（`force=true` 强制重推）
3. 在线程池执行推送（同步阻塞 IO），按 `push_mode` 分流：

| 模式 | 实现 | 机制 |
|---|---|---|
| `self_hosted` | `anki_sync_client_push.py` | `anki` Python 库直接打开本地缓存的 `collection.anki2` → 写入笔记 + 拷贝媒体 → 走 anki-rs `SyncStatus` 与自建 sync server（`SYNC_ENDPOINT`）全量/媒体同步；`SimpleFileLock` 防并发写库 |
| `ankiweb` | `ankiweb_push.py` | 同样本地写 collection，再用 AnkiWeb 账号（AES 解密凭据）登录官方同步 |

4. 结果写 `PushRecord`（卡片数/跳过数/耗时/状态）+ `PushRecordItem`（逐句记录）

旧版脚本：`anki_sync_push.py` / `anki_sync_push_safe.py` / `anki_api.py` / `anki_push_router.py` / `deploy_multi_push.py`（早期直连与多配置推送实验）；`direct_reimport_35_cards.py`、`reimport_latest_35_from_export.py` 为一次性数据修复脚本。

---

## 7. 前端 frontend（Vue 3 SPA）

- 技术：Vue 3 + Vite 5 + Naive UI + Pinia + Vue Router 4 + axios；marked + highlight.js 渲染帮助文章
- 开发代理：`/api → http://127.0.0.1:8000`（`vite.config.js`）
- 测试：vitest + @vue/test-utils + axios-mock-adapter（`tests/`）

### 路由（`src/router/index.js`）

| 路径 | 视图 | 权限 |
|---|---|---|
| `/login` `/register` | LoginView / RegisterView | guest（含滑块验证码组件 `CaptchaSliderDialog`） |
| `/` | PublicView | 公开库首页 |
| `/public/:id` | PublicDetailView | 分享详情（字幕播放器 `SubtitlePlayer`） |
| `/help[/:slug]` | HelpView | 帮助中心 |
| `/dashboard` `/tasks` `/tasks/:id` | Dashboard/Tasks/TaskDetailView | 登录 |
| `/collections[/:id]` | Collections/CollectionDetailView | 登录 |
| `/billing` `/transcribe` `/anki` `/settings` | 对应 View | 登录 |
| `/admin` | AdminView | admin |

### API 封装（`src/api/`）

`client.js`（axios 实例 + token 拦截）+ 按域拆分：`auth/tasks/segments/collections/tags/billing/recharge/anki/public/system/help/transcribe/admin` + `ws.js`（任务进度 WebSocket 封装）。状态：`stores/auth.js`（登录态、用户信息）。

---

## 8. 移动端 anki-swipe-app（Expo React Native）

- 名称"德语滑动学习"（scheme `ankiswipe`，web basePath `/swipe`）
- 技术：Expo SDK 56 / RN 0.85 / React 19 + expo-router + zustand + react-native-gesture-handler + reanimated + expo-av + expo-secure-store

### 页面（`app/`，expo-router 文件路由）

| 文件 | 功能 |
|---|---|
| `_layout.tsx` | 根布局 |
| `index.tsx` | 入口/引导 |
| `login.tsx` | 登录（token 存 SecureStore） |
| `swipe.tsx` | **主界面**：卡片滑动学习 |
| `settings.tsx` | 设置（难度、音源 mine/public 等） |
| `stats.tsx` | 学习统计 |

### 核心逻辑

- `store/swipeStore.ts`：zustand store——拉取 `/api/swipe/feed`、当前卡片切换、`rate`（easy/hard）、`collect`、feed 将尽时自动加载更多
- `components/SwipeDeck.tsx` + `SwipeCard.tsx`：手势滑动卡组（左滑 hard / 右滑 easy，见 `RatingOverlay`）
- `components/AudioProgressBar.tsx`：句子音频播放（expo-av）
- `services/api.ts`（后端调用）、`auth.ts`（认证）、`audioCache.ts`（音频缓存）

---

## 9. 遗留 Streamlit 应用

V1 时代的单体应用，仍可用但已被 V2（FastAPI+Vue）取代：

| 文件 | 说明 |
|---|---|
| `app.py` | 初代全链路：上传→Whisper 转写切割→逐句勾选→翻译→genanki 导出 .apkg（端口 8501） |
| `app_v2.py` | 异步化版本：后台处理 + 进度 ETA + 任务浏览 + 推送 Anki（端口 8502），配 `task_worker.py`（独立 worker 进程）与 `anki-streamlit-v2.service` systemd 单元 |
| `app_subtitle.py` | 字幕优先版本：整音频播放器 + 双语字幕高亮 + 句子收集（`subtitle_component/index.html` 前端组件） |

根目录大量 `check_*.sql/py`、`fix_*.py/sh`、`debug_*.py`、`test_*`、`tmp_*` 为历次生产排障与计费数据修复的一次性脚本（如 `fix_unsettled_billing*.py`、`fix_charge_*.py` 处理预扣未结算遗留）。

---

## 10. 数据模型

全部定义于 `backend/app/models.py`（PostgreSQL，UUID 主键），Alembic 迁移 4 个版本（`001_initial` → `004_reserve_reference_id`）。

### 实体关系

```
users ──┬─< tasks ──┬─< segments ──< collection_items >── collections >──┐
        │           ├─< task_tags >── tags                                │
        │           └─< public_shares (1:1) ─┬─< public_likes             │
        │                                    └─< public_collects          │
        ├─< billing_records                users (上）─────────────────────┘
        ├─< anki_push_configs
        ├─< push_records ──< push_record_items >── segments
        ├─< recharge_requests
        ├─< segment_ratings >── segments        (swipe 标注)
        └─< transcriptions                      (纯文本转写)

system_settings (key/value)   engine_pricing (engine_key+model_size)
help_articles                  email_verification_codes
```

### 核心表说明

| 表 | 关键字段 | 说明 |
|---|---|---|
| `users` | email/phone（唯一）、role、credits（镜像）、allowed_engines、max_push_configs | 本地镜像，权威数据在 auth-service |
| `tasks` | file_hash、engine/model_size、stage、progress、source/normalized_path、clips_dir、is_public、credits_charged/reserved | `(user_id, file_hash, engine)` 唯一 → 上传查重；stage ∈ pending/normalizing/transcribing/translating/done/failed/cancelled |
| `segments` | seq_index、start/end_time、german_text、chinese_text、clip_path | `(task_id, seq_index)` 唯一；德/中文本建 trigram GIN 索引 |
| `collections` / `collection_items` | push_enabled | 收藏集与句子多对多，`push_enabled` 控制是否推送 |
| `engine_pricing` | credits_per_minute | 引擎费率（任务计费依据） |
| `billing_records` | action、amount、balance_after、duration_sec | 账单流水 |
| `anki_push_configs` | push_mode、sync_endpoint/username/password_enc、ankiweb_*、deck_name、note_type | 推送目标配置（密码 AES 加密） |
| `push_records` / `push_record_items` | status、card_count、skipped_count | 推送审计 + 按 config 的去重依据 |
| `public_shares` | title、difficulty、category、play/like/collect_count、is_featured | 公开分享（task_id 唯一） |
| `segment_ratings` | rating(easy/hard)、is_collected | swipe 标注，自适应难度算法的输入 |
| `recharge_requests` | amount、credits_amount、coefficient、payment_image、image_hash、status | 线下充值审核流 |

---

## 11. 关键业务流程

### 11.1 音频任务全流程

```
用户上传 (POST /api/tasks)
  → 校验引擎授权/模型 → 落盘 uploads/ → sha256 查重(命中直接返回旧任务)
  → 估算时长(file_size/16000*1.2) → estimate_cost → check_balance(402 拒绝)
  → 拷贝到 TASK_DIR/<user>/<task>/ → TaskWorkerV2.submit
      ├─ normalizing: normalize_audio.py (ffmpeg 16k mono)
      ├─ transcribing: ASR 引擎转写 → align_and_cut 切句子 clips
      ├─ translating: Google 翻译 de→zh，写 segments
      └─ done: 测时长 → charge_credits(实际时长) → credits_charged 落库
  全程: cancel.json 检查点取消 / WS 实时进度 / 异常自动退预扣款
```

### 11.2 推送 Anki 流程

收藏集 → push_enabled 句子 → 按 config 过滤已推送 → 线程池写本地 collection.anki2 + 媒体 → sync（自建 server 或 AnkiWeb）→ PushRecord/Item 落账。

### 11.3 Swipe 自适应难度

`_get_user_level`：无标注→A1；总 easy 数 // 3 定基础级，最近 5 次标注 easy 多升一级 / hard 多降一级（A1–C2）。`GET /feed`：约 80% 当前及以下难度 + 20% 更高难度，排除已标注，支持 `source=public|mine`。

### 11.4 认证流程

前端持有 auth-service 签发的 JWT → 后端 `verify_token` 远程校验 → 本地镜像用户（自动注册/UUID 迁移）→ 业务接口。积分全部走 auth-service，本地 `billing_records` 只记账。

---

## 12. 外部依赖关系

### 服务依赖

| 依赖 | 用途 | 接入点 |
|---|---|---|
| auth-service (`auth.3mudi.com`) | JWT 校验、用户资料、积分钱包、管理操作、邮件发送 | `auth_client.py` / `email_service.py`（httpx） |
| PostgreSQL 16 | 主数据库（需 `pg_trgm` 扩展） | `database.py`（asyncpg）/ worker（psycopg2） |
| ffmpeg | 音频标准化、切割 | `normalize_audio.py` subprocess / pydub |
| Google 翻译 | de→zh-CN 句子翻译 | `deep_translator`（worker、segments 路由） |
| OpenAI Whisper API | 远程 ASR 引擎 | `openai_whisper_api.py` |
| Anki sync server / AnkiWeb | 卡片同步目标 | `anki` Python 包（根目录推送脚本） |

### 关键 Python 包

- backend：`fastapi uvicorn sqlalchemy[asyncio] asyncpg psycopg2-binary alembic pydantic-settings python-jose passlib cryptography httpx`
- 管线（根 `requirements.txt`）：`faster-whisper torch transformers librosa pydub deep-translator genanki anki streamlit`

### 关键 npm 包

- frontend：`vue vue-router pinia naive-ui axios marked highlight.js`；dev：`vite vitest`
- swipe-app：`expo expo-router expo-av expo-secure-store react-native-gesture-handler react-native-reanimated zustand`

---

## 13. 运行与部署

### 13.1 Docker Compose（推荐）

```bash
docker compose up -d   # 启动 db(postgres:16) + backend + frontend(nginx:80/443)
```

- backend 镜像：`backend/Dockerfile`；环境文件 `.env`（`ANKI_*` 前缀）
- frontend 镜像：`frontend/Dockerfile`（构建 SPA + nginx，挂载 Let's Encrypt 证书目录）

### 13.2 本地开发

```bash
# 后端（Python 3.11+）
cd backend
pip install -r requirements.txt -r ../requirements.txt   # 路由+管线依赖
uvicorn app.main:app --reload --port 8000                # 需先起 PostgreSQL

# 前端
cd frontend
npm install
npm run dev        # :5173，/api 代理到 :8000
npm run test       # vitest

# 移动端
cd anki-swipe-app
npm install
npm run start      # expo start（android/ios/web）
```

### 13.3 数据库迁移

```bash
cd backend
alembic upgrade head     # 001_initial → 004_reserve_reference_id
```

### 13.4 生产部署要点

- Nginx：`nginx-anki-merged.conf` 合并站点配置（`anki.3mudi.com`，含 `/swipe` 路径给 swipe web build）；swipe-app 下还有多版 `nginx-anki*.conf` / `nginx-swipe.conf` 历史配置
- 部署脚本：`deploy.py`、`scripts/deploy_*.sh`（前端构建同步、后端重启、nginx+systemd）
- 遗留 Streamlit v2：`anki-streamlit-v2.service`（systemd，8502 端口）
- 依赖 ffmpeg、（可选）GPU/CUDA 加速 whisper

---

## 14. 测试与运维脚本

### 自动化测试

- `backend/tests/`（pytest + pytest-asyncio）：`test_api/test_billing/test_crypto/test_email/test_models/test_schemas/test_help_*/test_swipe_*`
- `frontend/tests/`：vitest 组件与 API 测试
- 冒烟/e2e：`scripts/e2e_test.py`、`scripts/test_*.sh`、根目录 `test_api*.sh`

### 运维脚本

| 类别 | 位置 | 举例 |
|---|---|---|
| 部署 | 根目录 + `scripts/` | `deploy.py`、`deploy_*.sh`、`sync_and_build.sh` |
| 数据迁移 | `scripts/` | `migrate_streamlit_pushes.py`、`migrate_subtitle_beta.py`、`migrate_v2_streamlit_to_api.py`、`migration_003.sql` |
| 初始化 | `scripts/` | `init_admin.py`、`setup_db.sh`、`seed_pricing.py`、`seed_swipe.py`、`backend/scripts/seed_help_articles.py` |
| 计费排障 | 根目录 | `check_billing.py/sh`、`fix_unsettled_billing*.py`、`fix_charge_*.py`、`fix_add_credits*.py`、`backend/scripts/fix_orphan_reserves.py` |
| 任务排障 | 根目录 | `check_task*.sql`、`fix_stuck_task.sql`、`check_segments.py` |

---

## 附：文档索引

- 设计文档：[docs/V2-重构技术方案.md](docs/V2-重构技术方案.md)、[docs/FEATURE_DESIGN_push_tracking_and_public_library.md](docs/FEATURE_DESIGN_push_tracking_and_public_library.md)
- 交接文档：[docs/V2-项目交接文档.md](docs/V2-项目交接文档.md)、[HANDOFF.md](HANDOFF.md)、[HERMES_SUMMARY.md](HERMES_SUMMARY.md)
- 旧版项目说明：[PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)
