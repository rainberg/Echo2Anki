# Deutsch Lernen App — 项目完整文档

> 最后更新: 2026-04-25
> 服务器: Oracle Cloud Frankfurt (89.168.93.94)
> 维护人: anki_user / ubuntu

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [前后端设计](#3-前后端设计)
4. [模块详解](#4-模块详解)
5. [部署配置](#5-部署配置)
6. [数据流与工作流程](#6-数据流与工作流程)
7. [数据库结构](#7-数据库结构)
8. [开发与运维指南](#8-开发与运维指南)
9. [已知问题与限制](#9-已知问题与限制)

---

## 1. 项目概述

### 1.1 项目目标

将**德语音频**自动转化为 **Anki 听力卡片**，流程为：

```
德语音频 → ASR 转写 → 时间戳对齐 → 逐句切割 → 中文翻译 → 推送至自建 Anki 云
```

卡片格式：
- **正面 (Front)**: 仅 `[sound:xxx.mp3]` — 纯听力练习，不显示文本
- **背面 (Back)**: 德语原文 + 空行 + 中文翻译

### 1.2 技术栈总览

| 层级 | 技术 | 用途 |
|------|------|------|
| 前端 UI | Streamlit + PyQt5 | Web 端处理界面 / 桌面客户端 |
| ASR 模型 | Cohere Transcribe (2B) | 德语语音→文本 (本地 CPU 推理) |
| 时间戳 | faster-whisper (tiny) | 单词级时间戳 (本地 CPU 推理) |
| 翻译 | deep-translator (Google Translate) | 德语→中文逐句翻译 |
| 音频处理 | pydub + librosa | 音频加载、切割、格式转换 |
| 卡片存储 | genanki (备用) / SQLite 直写 | 卡片生成与推送 |
| 同步服务 | anki-cloud-sync (Docker) | 自建 Anki 同步服务器 |
| 后台服务 | systemd | Streamlit 进程管理 |

### 1.3 用户场景

```
用户(Telegram) → 发送德语音频 → [处理流水线] → Anki 卡片 → 手机/电脑同步学习
```

用户通过 Telegram 发送录音，后台处理后直接将卡片推送到自建 Anki 云服务器，打开手机 AnkiDroid 同步即可学习。

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│  Oracle Cloud Frankfurt (89.168.93.94)                              │
│                                                                     │
│  ┌──────────────────┐    ┌──────────────────────────────────────┐   │
│  │  systemd          │    │  Docker: anki-sync-standalone        │   │
│  │  anki-streamlit   │    │  ┌────────────────────────────────┐ │   │
│  │  (8501)           │    │  │  anki-cloud-sync (AGPLv3)      │ │   │
│  │  │                │    │  │  port 8080 → 8081              │ │   │
│  │  └─ Streamlit     │    │  │  SQLite: collection.anki2      │ │   │
│  │     app.py        │    │  │  Media: /data/anki_user/media/ │ │   │
│  │                   │    │  └────────────────────────────────┘ │   │
│  └──────────────────┘    └──────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Model Cache (~3.9GB)                                       │   │
│  │  - Cohere Transcribe (transformer)                          │   │
│  │  - faster-whisper tiny (CTranslate2)                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 端口分配

| 端口 | 服务 | 说明 |
|------|------|------|
| 8080 | anki-sync-server (HTTP) | Anki 同步协议入口 |
| 8081 | anki-sync-server (内部) | 内部 sidecar 端口 |
| 8501 | Streamlit Web UI | 德语听力卡片生成器界面 |

### 2.3 网络说明

- Oracle Cloud 安全组已开放 8080 和 8501 端口
- **重要**: 用户家庭网络仅允许 HTTPS，无法直接访问 HTTP(8080)
  - 解决方案: 需要添加 Nginx 反向代理 + Let's Encrypt SSL，或用 Cloudflare Tunnel
  - 当前: 用户仅在非家庭网络(LTE/4G)下同步

---

## 3. 前后端设计

### 3.1 Streamlit Web UI (app.py)

**位置**: `/opt/anki-app/app.py`
**URL**: `http://89.168.93.94:8501`

**四步工作流**:

| 步骤 | UI 元素 | 功能 |
|------|---------|------|
| 1. 上传音频 | file_uploader + audio player | 选择并试听 MP3/WAV 文件 |
| 2. 识别切割 | st.status + progress bar | 加载模型 → ASR → 时间戳 → 切割音频 |
| 3. 选择+翻译 | checkbox 列表 + 试听 + 翻译按钮 | 逐句勾选 → Google 翻译 → 展示结果 |
| 4. 推送服务器 | text_input + 推送按钮 | 指定牌组名 → 一键推送至 Docker 数据库 |

**UI 设计细节**:
- 使用 `st.cache_resource` 缓存模型实例，避免每次操作重新加载
- 使用 `st.session_state` 管理会话状态（segments, selected_indices, translations 等）
- 侧边栏显示模型状态和 Anki 云状态
- 错误处理: 推送失败时提示检查 Docker 容器状态

### 3.2 桌面客户端 (PyQt5)

- 使用 PyQt5 构建的桌面应用
- 本地处理音频，不需要 Web 浏览器
- 核心处理逻辑与 Streamlit 共用 cohere_asr.py / whisper_timestamps.py / align_and_cut.py 模块
- 支持 Telegram bot 集成，用户直接发送语音消息触发处理

---

## 4. 模块详解

### 4.1 cohere_asr.py — Cohere ASR 转写模块

**文件**: `/opt/anki-app/cohere_asr.py` (116 行)
**模型**: `CohereLabs/cohere-transcribe-03-2026` (3.9GB 本地缓存)

**核心功能**:
- 加载 Cohere Transcribe 2B 模型进行德语语音转写
- 使用 30 秒分块处理，避免 CPU OOM
- 支持德语(de)/英语(en)语言提示

**关键参数**:
- `device`: "cpu" (当前服务器无 GPU)
- `chunk_seconds`: 30 (分块大小)
- `language_prompt`: 使用 `<|startoftranscript|><|de|>` 前缀

**性能**: 1 分钟音频约 30-60 秒处理时间 (CPU)

### 4.2 whisper_timestamps.py — 时间戳提取模块

**文件**: `/opt/anki-app/whisper_timestamps.py` (68 行)
**模型**: `Systran/faster-whisper-tiny` (75MB)

**核心功能**:
- 使用 faster-whisper tiny 模型提取单词级时间戳
- 启用 VAD 过滤器提升准确性
- CPU int8 量化推理

**返回格式**:
```python
[
  {"word": "Hallo", "start": 0.5, "end": 0.8},
  {"word": "wie",   "start": 0.9, "end": 1.1},
  ...
]
```

### 4.3 align_and_cut.py — 对齐与切割模块

**文件**: `/opt/anki-app/align_and_cut.py` (215 行)

**核心功能**:
- `split_into_sentences()`: 德语分句（处理 Dr., Prof. 等缩写）
- `align_text_to_timestamps()`: 将 Cohere 转写文本与 Whisper 时间戳对齐
  - 单词级模糊匹配（前 3 个单词作为锚点）
  - 处理 Cohere 和 Whisper 之间的文本差异
- `cut_audio_clips()`: 按对齐的时间段切割音频
  - 50ms 填充避免截断
  - 最小片段长度 200ms
- `process_pipeline()`: 完整流水线封装

**对齐策略**:
```
Cohere 文本: "Hallo, wie geht es dir? Mir geht es gut."
                    ↓ 分词
sentence[0] = "Hallo, wie geht es dir?"
sentence[1] = "Mir geht es gut."
                    ↓ 匹配前3词
Whisper 时间戳 → hallo(0.5-0.8) wie(0.9-1.1) geht(1.2-1.4) es(1.5-1.6) dir(1.7-2.0)
                    ↓
segment[0] = {text: "Hallo, wie geht es dir?", start: 0.5, end: 2.0}
```

### 4.4 anki_sync_push.py — 数据库直写推送模块

**文件**: `/opt/anki-app/anki_sync_push.py` (522 行)

**这是整个项目的核心创新点**——不使用 genanki 导出 .apkg 文件，而是直接操作 sync server 的 SQLite 数据库。

**工作流程**:
```
1. sudo docker stop anki-sync-standalone    # 暂停容器
2. sudo cp collection.anki2 → 临时副本      # 备份数据库
3. 写入 SQLite:
   - notes 表: note_id, guid, flds, sfld, csum
   - cards 表: card_id, nid, did, ord, ...
4. sudo cp 音频文件 → media/ 目录
5. 写入 media.db: fname, sha1, size, usn, mtime
6. sudo cp 临时数据库 → collection.anki2    # 写回
7. sudo docker start anki-sync-standalone   # 重启容器
```

**为什么用直写而非 genanki**:
- anki-cloud-sync 的 standalone 模式没有 REST API
- genanki 生成 .apkg 文件后仍需手动导入或同步
- 直写数据库是最短路径：打开手机 → 同步 → 卡片出现

**卡片字段格式**:
```sql
flds = "[sound:clip_001.mp3]\x1fHallo, wie geht es?\n\n你好，你好吗？"
       │  Front ([sound:...])    ││  Back (德语\n\n中文)             │
       └──── 第一个字段 ──────────┘└──── 第二个字段 ────────────────┘
```

**关键 SQLite 操作**:
- `notes` 表写入: id, guid, mid=1623434819882(Basic), mod, usn, tags, flds, sfld, csum
- `cards` 表写入: id, nid, did, ord=0(正面的), mod, usn, type=0(新卡片), queue=0(新), due
- csum 计算: `zlib.crc32(front_field.strip().lower().encode("utf-8"))`
- sfld: `front_field.lower()`
- GUID 生成: `os.urandom(8)` → base64

**sudo 操作**（ubuntu 用户 NOPASSWD）:
- `sudo docker stop/start anki-sync-standalone`
- `sudo cp` (复制数据库和音频文件到 Docker volume)
- `sudo chmod / chown` (设置权限)
- `sudo mkdir -p` (创建目录)
- `sudo sha1sum` (计算媒体文件校验和)
- `sudo tee` (写入文件)

### 4.5 anki_api.py — genanki 导出模块 (备用)

**文件**: `/opt/anki-app/anki_api.py` (268 行)

**用途**: 作为直写方案的备选，使用 genanki 导出 .apkg 文件。当前**未启用**。

**卡片模板**:
- 模型 ID: `1726354051`
- 字段: Audio(正面)、German、Chinese
- CSS: Noto Sans SC 字体，居中布局

### 4.6 test_pipeline.py — 测试脚本

**文件**: `/opt/anki-app/test_pipeline.py` (126 行)

**用途**: 测试完整流水线（Cohere ASR + Whisper + 对齐 + 切割）

**运行方式**:
```bash
source /opt/anki-venv/bin/activate
python /opt/anki-app/test_pipeline.py /tmp/test_audio_de.mp3
```

输出: 切割后的 MP3 文件 + JSON 结果 `transcription_result.json`

---

## 5. 部署配置

### 5.1 服务器信息

| 属性 | 值 |
|------|-----|
| 提供商 | Oracle Cloud Infrastructure |
| 区域 | Frankfurt (eu-frankfurt-1) |
| 公网 IP | 89.168.93.94 |
| 内网 IP | 10.0.0.76 |
| OS | Ubuntu (3.11 Python, amd64) |
| CPU | Intel Xeon (无 GPU) |
| 用户 | ubuntu (有 sudo NOPASSWD) |

### 5.2 目录结构

```
/opt/anki-app/                  # 项目主目录
├── app.py                      # Streamlit Web UI (477行)
├── cohere_asr.py               # Cohere ASR 转写模块 (116行)
├── whisper_timestamps.py       # Whisper 时间戳模块 (68行)
├── align_and_cut.py            # 对齐与切割模块 (215行)
├── anki_sync_push.py           # 数据库直写推送模块 (522行)
├── anki_api.py                 # genanki 导出模块 (268行，备用)
├── test_pipeline.py            # 测试脚本 (126行)
├── PROJECT_DOCUMENTATION.md    # 本文档
├── HERMES_SUMMARY.md           # 技术交接摘要
└── models/                     # faster-whisper 模型缓存
    └── models--Systran--faster-whisper-tiny/
        ├── blobs/              # 模型权重文件 (75MB)
        └── refs/

/opt/anki-venv/                 # Python 虚拟环境
├── bin/
│   ├── python3 → /usr/bin/python3
│   ├── streamlit
│   ├── pip
│   └── ...
└── lib/python3.11/site-packages/

/etc/systemd/system/
└── anki-streamlit.service      # systemd 服务单元

/home/ubuntu/anki-cloud/        # Docker Compose 项目
├── docker-compose.yml           # 完整版 (含 API/MCP)
├── docker-compose.standalone.yml # 精简版 (仅 sync-server)
├── .env                         # 环境变量
└── CLAUDE.md                    # 上游项目文档

/var/lib/docker/volumes/
└── anki-cloud_app-data/_data/  # Docker volume
    └── anki_user/
        ├── collection.anki2    # Anki 主数据库 (SQLite)
        ├── media.db            # 媒体文件注册表 (SQLite)
        └── media/              # 音频文件目录 (830MB, 4518个文件)
```

### 5.3 Python 虚拟环境

```
位置: /opt/anki-venv/
Python: 3.11 (系统 Python)
```

**核心依赖**:
```
streamlit      1.56.0    Web UI 框架
deep-translator 1.11.4   Google 翻译接口
faster-whisper 1.2.1     Whisper 时间戳
genanki        0.13.1     .apkg 导出 (备用)
librosa        0.11.0    音频加载
pydub          0.25.1    音频处理
soundfile      0.13.1    WAV 读写
torch          2.11.0+cpu PyTorch CPU 版
transformers   5.2.0     Cohere 模型框架
numpy          2.2.6     数组计算
```

### 5.4 Docker 配置

**容器**: `anki-sync-standalone`
**镜像**: `ghcr.io/danielpmichalski/anki-cloud-sync:v25.09-r7`
**模式**: standalone（精简模式，无 API/MCP 服务）

**环境变量**:
```
SYNC_MODE=standalone
SYNC_USER1=anki_user:anki_sync_2024
SYNC_BASE=/data
SYNC_INTERNAL_PORT=8081
SYNC_INTERNAL_HOST=0.0.0.0
```

**Docker Compose** (`/home/ubuntu/anki-cloud/docker-compose.standalone.yml`):
```yaml
services:
  anki-sync-server:
    image: ghcr.io/danielpmichalski/anki-cloud-sync:v25.09-r7
    container_name: anki-sync-standalone
    ports:
      - "8080:8080"
      - "8081:8081"
    environment:
      SYNC_BASE: /data
      SYNC_INTERNAL_PORT: 8081
      SYNC_INTERNAL_HOST: 0.0.0.0
      SYNC_MODE: standalone
      SYNC_USER1: ${SYNC_USER1}
    volumes:
      - app-data:/data
    restart: unless-stopped

volumes:
  app-data:
```

**启动方式**: `cd /home/ubuntu/anki-cloud && sudo docker compose -f docker-compose.standalone.yml up -d`

### 5.5 Systemd 服务

**文件**: `/etc/systemd/system/anki-streamlit.service`
**描述**: Anki Streamlit App — German Audio Card Generator

```ini
[Unit]
Description=Anki Streamlit App — German Audio Card Generator
After=network.target docker.service
Requires=docker.service

[Service]
User=ubuntu
WorkingDirectory=/opt/anki-app
Environment="PATH=/opt/anki-venv/bin:..."
Environment="PYTHONPATH=/opt/anki-app"
ExecStart=/opt/anki-venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**常用命令**:
```bash
sudo systemctl status anki-streamlit     # 查看状态
sudo systemctl restart anki-streamlit    # 重启
sudo journalctl -u anki-streamlit -f     # 查看日志
```

### 5.6 模型缓存 (~3.9GB)

| 模型 | 大小 | 缓存位置 |
|------|------|----------|
| Cohere Transcribe 2B | ~3.9GB | ~/.cache/huggingface/hub/models--CohereLabs--cohere-transcribe-03-2026/ |
| faster-whisper tiny | ~75MB | /opt/anki-app/models/models--Systran--faster-whisper-tiny/ + ~/.cache/huggingface/hub/models--Systran--faster-whisper-tiny/ |

---

## 6. 数据流与工作流程

### 6.1 完整处理流水线

```
用户操作             后台处理                              数据存储
─────────────────────────────────────────────────────────────────────
上传 MP3 音频  ──→  librosa 加载音频 (16000Hz, mono)
                    ↓
                    Cohere ASR 分块转写 (30s chunk)
                    ↓                    ──→ transcription (str)
                    faster-whisper 提取单词时间戳
                    ↓                    ──→ word_timestamps (list[dict])
                    文本对齐 (前3词锚点匹配)
                    ↓                    ──→ segments (list[{text,start,end}])
                    pydub 切割音频
                    ↓                    ──→ clip_001.mp3 ~ clip_NNN.mp3
                    ↓
用户勾选句子 ──→    收集 selected_indices
                    ↓
点击翻译     ──→    GoogleTranslator 逐句翻译
                    ↓                    ──→ translations (list[str])
                    ↓
点击推送     ──→    stop Docker container
                    ↓
                    copy collection.anki2 → temp
                    ↓
                    INSERT INTO notes (flds, sfld, csum, ...)
                    INSERT INTO cards (nid, did, ord, ...)
                    ↓
                    copy audio → Docker volume media/
                    INSERT INTO media.db (fname, sha1, size, ...)
                    ↓
                    cp temp → collection.anki2
                    start Docker container
                    ↓                    ──→ 卡片在服务器就绪
                    ↓
用户打开 AnkiDroid ──→ 同步按钮 → 下载卡片 → 开始学习
```

### 6.2 卡面格式说明

**正面 (Front) — 仅音频**:
```
┌──────────────────────────────────┐
│                                  │
│         ▶ [播放按钮]              │
│                                  │
│     (无文字，纯听力练习)           │
│                                  │
└──────────────────────────────────┘
```

**背面 (Back) — 德语 + 中文**:
```
┌──────────────────────────────────┐
│                                  │
│         ▶ [播放按钮]              │
│                                  │
│  ──────────────────────────────  │
│                                  │
│  Hallo, wie geht es?             │
│                                  │
│  你好，你好吗？                    │
│                                  │
└──────────────────────────────────┘
```

### 6.3 Anki 客户端同步配置

| 参数 | 值 |
|------|-----|
| 服务器地址 | `http://89.168.93.94:8080` |
| 用户名 | `anki_user` |
| 密码 | `anki_sync_2024` |
| 牌组名称 | `德语听力`（可自定义） |

> ⚠️ 注意：当前只能通过 HTTP 同步。用户家庭网络仅支持 HTTPS，因此同步需要在外网（如 LTE）下进行。如需家庭网络使用，需配置 SSL 证书。

---

## 7. 数据库结构

### 7.1 collection.anki2 (SQLite)

Current state: 5074 notes, 5074 cards, 7 decks, 7 notetypes

**decks 表**:
```
ID          | Name
1           | Default
1623473103774 | Deutsch
1637827114437 | 精彩
1627214452808 | 英语
1655335410665 | Eurythmie
1657062541058 | 十二感官
1705393177024 | C2
```

**notetypes 表**:
| ID | Name |
|----|------|
| 1612935922206 | AwesomeSelect-3.x |
| 1623434819882 | **Basic** ← 我们使用的 |
| 1623434819883 | Basic (and reversed card) |
| 1623434819884 | Basic (optional reversed card) |
| 1623434819885 | Basic (type in the answer) |
| 1623434819886 | Cloze |
| 1750481904187 | 图片遮盖 |

**notes 表字段** (通过 `anki_sync_push.py` 写入):
```sql
id      INTEGER PRIMARY KEY,    -- 毫秒时间戳 + 随机数
guid    TEXT,                    -- base64(urandom(8))
mid     INTEGER,                -- 1623434819882 (Basic)
mod     INTEGER,                -- Unix timestamp
usn     INTEGER,                -- 更新序列号
tags    TEXT,                    -- "deutsch-lernen"
flds    TEXT,                    -- "[sound:xxx.mp3]\x1fGerman\n\nChinese"  (用 \x1f 分隔字段)
sfld    TEXT,                    -- 排序字段 = lower(front_field)
csum    INTEGER,                -- crc32(clean_front_field) & 0xFFFFFFFF
flags   INTEGER DEFAULT 0,
data    TEXT DEFAULT ''
```

**cards 表字段**:
```sql
id      INTEGER PRIMARY KEY,    -- 毫秒时间戳 + 随机数
nid     INTEGER,                -- 关联的 note_id
did     INTEGER,                -- deck_id (牌组)
ord     INTEGER DEFAULT 0,      -- 0=正面模板 (Basic只有1张卡)
mod     INTEGER,                -- Unix timestamp
usn     INTEGER,                -- 更新序列号
type    INTEGER DEFAULT 0,      -- 0=新卡片
queue   INTEGER DEFAULT 0,      -- 0=新卡片
due     INTEGER,                -- 排序位置 (从1开始)
ivl     INTEGER DEFAULT 0,
factor  INTEGER DEFAULT 0,
reps    INTEGER DEFAULT 0,
lapses  INTEGER DEFAULT 0,
left    INTEGER DEFAULT 0,
odue    INTEGER DEFAULT 0,
odid    INTEGER DEFAULT 0,
flags   INTEGER DEFAULT 0,
data    TEXT DEFAULT '{}'
```

### 7.2 media.db (媒体文件注册)

```sql
CREATE TABLE media (
    fname TEXT PRIMARY KEY,  -- 文件名 ("clip_001.mp3")
    sha1 BLOB,               -- SHA1 校验和 (20字节)
    size INTEGER,            -- 文件大小 (字节)
    usn INTEGER,             -- 更新序列号
    mtime INTEGER            -- 修改时间
);
```

---

## 8. 开发与运维指南

### 8.1 常用运维命令

```bash
# === Streamlit UI ===
sudo systemctl status anki-streamlit           # 状态
sudo systemctl restart anki-streamlit           # 重启
sudo journalctl -u anki-streamlit -n 100 -f     # 查看日志

# === Docker 容器操作 ===
sudo docker ps --filter name=anki-sync-standalone     # 容器状态
sudo docker stop anki-sync-standalone                  # 暂停容器
sudo docker start anki-sync-standalone                 # 启动容器
sudo docker logs anki-sync-standalone -n 50            # 同步日志

# === 数据库操作 ===
# 复制到本地后查询 (需 sudo 先复制)
sudo cp /var/lib/docker/volumes/anki-cloud_app-data/_data/anki_user/collection.anki2 /tmp/tmp.anki2
sudo chown ubuntu /tmp/tmp.anki2
sqlite3 /tmp/tmp.anki2 "SELECT COUNT(*) FROM notes;"
sqlite3 /tmp/tmp.anki2 "SELECT id, substr(flds,1,60) FROM notes ORDER BY id DESC LIMIT 5;"

# === 模型缓存 ===
du -sh ~/.cache/huggingface/hub/models--CohereLabs--cohere-transcribe-03-2026/
ls /opt/anki-app/models/models--Systran--faster-whisper-tiny/blobs/

# === 日志文件 ===
ls -la /tmp/anki-streamlit/        # Streamlit 临时文件目录
ls -la /tmp/test_clips/            # 测试切割输出
```

### 8.2 添加新卡片 (手动测试)

```python
from anki_sync_push import push_cards_to_server

sentences = [{
    "audio_filename": "test_audio.mp3",
    "german_text": "Hallo, wie geht es dir?",
    "chinese_text": "你好，你好吗？"
}]
result = push_cards_to_server(sentences, "/path/to/audio/dir", "德语听力")
print(result)
```

### 8.3 开发注意事项

1. **Cohere ASR 首次加载 ~60 秒** — Streamlit 缓存后复用
2. **Docker volume 文件属于 root** — 所有写操作需用 `sudo cp` 或 `sudo tee`
3. **media.db 必须同步注册** — 只复制音频文件不够，还需 INSERT INTO media.db
4. **容器暂停后再写** — collection.anki2 可能在运行时被锁定
5. **卡片 ID 冲突检测** — 目前的 `_next_note_id()` 基于毫秒时间戳 + 随机数，极低概率冲突
6. **前端在服务器上难以修改** — Streamlit 应用文件在 `/opt/anki-app/`，SSH 直接编辑

### 8.4 添加新功能建议

- 批量处理多个音频文件
- 添加 OpenAI / api2d.net 翻译选项（替代 Google Translate）
- 添加单词点击释义功能
- 添加收藏例句功能
- 添加 HTTPS 支持（Nginx + Let's Encrypt）
- Telegram bot 集成（用户发送语音自动处理并推送）

---

## 9. 已知问题与限制

### 9.1 当前未解决

| 问题 | 描述 | 优先级 |
|------|------|--------|
| ❌ HTTPS 不可用 | 用户家庭网络不能访问 HTTP，同步只能在外网进行。需加 Nginx + SSL | **高** |
| ❌ 无 REST API | anki-cloud-sync standalone 模式无卡片创建接口，只能用 SQLite 直写 | 中 |
| ❌ 无错误重试机制 | 翻译失败/推送失败时 UI 只能提示，无自动重试 | 低 |
| ❌ 无缓存清理 | Docker volume media 目录已有 830MB/4518 个文件，会持续增长 | 中 |

### 9.2 潜在问题

- **Cohere ASR 模型更新** — 代码硬编码了模型名 `CohereLabs/cohere-transcribe-03-2026`，需跟踪新版本
- **faster-whisper 版本兼容** — `compute_type="int8"` 在不同版本间可能变化
- **Docker compose 版本兼容** — api/mcp 服务未启动（只用了 standalone 模式），完整 docker-compose.yml 中包含 API 和 MCP 服务配置
- **media.db SHA1 格式** — 需确认 anki-cloud-sync 是否要求 hex 字符串还是二进制 blob（当前使用二进制 blob）

### 9.3 安全注意事项

- 同步服务器无 SSL/TLS 保护（HTTP 明文传输）
- `SYNC_USER1` 密码存储在 `.env` 文件中（明文）
- SQLite 直写绕过了 Anki 的同步协议和冲突检测
- 同时多个用户推送卡片可能造成数据库写冲突

---

## 附录

### A. 相关技能

项目可用的 Hermes 技能:
- `german-speech-to-chinese` — 德语语音转中文翻译的完整流程
- `deploy-china-server` — 使用中外混合部署架构向中国用户提供稳定服务

### B. 相关项目

- **anki-cloud-sync**: https://github.com/danielpmichalski/anki-cloud-sync
- **genanki**: https://github.com/kerrickstaley/genanki
- **Cohere Transcribe**: https://huggingface.co/CohereLabs/cohere-transcribe-03-2026
- **faster-whisper**: https://github.com/SYSTRAN/faster-whisper
