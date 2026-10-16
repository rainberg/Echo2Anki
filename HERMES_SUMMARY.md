# Hermes 已完成工作总结 — 供 Codex 继续开发

> 最后更新: 2026-04-25 17:25 UTC

---

## 1. 项目概览

**项目名称**: 德语听力卡片生成器 (deutsch-lernen-app)
**服务器**: Oracle Cloud Frankfurt (89.168.93.94)
**目标**: 上传德语音频 → ASR 转写 → 句子切割 → 翻译 → 推送 Anki 卡片到自建服务器

---

## 2. 服务器基础设施

### 2.1 硬件与环境

| 项目 | 值 |
|------|-----|
| 外网 IP | 89.168.93.94 |
| 内网 IP | 10.0.0.76 |
| OS | Ubuntu (Oracle Cloud) |
| 用户 | ubuntu (sudo NOPASSWD) |
| Python | 3.11 (虚拟环境: `/opt/anki-venv/`) |
| 代理 | 默认无代理（~/.bashrc 中已注释 Xray 配置） |

### 2.2 Docker 服务

| 服务 | 镜像 | 端口 | 状态 |
|------|------|------|------|
| anki-sync-standalone | `ghcr.io/danielpmichalski/anki-cloud-sync:v25.09-r7` | 8080(REST/sync) / 8081(internal) | ✅ Up |
| steiner-postgres | postgres | 5433 | ✅ Up (无关服务) |

### 2.3 Systemd 服务

| 服务名 | 描述 | 端口 | 管理命令 |
|--------|------|------|----------|
| anki-streamlit | Streamlit 前端应用 | 8501 | `sudo systemctl restart/status anki-streamlit` |

---

## 3. 应用代码 (`/opt/anki-app/`)

### 3.1 文件清单

| 文件 | 功能 |
|------|------|
| `cohere_asr.py` | Cohere Transcribe 本地ASR模型 (CPU推理, 德语) |
| `whisper_timestamps.py` | faster-whisper tiny 模型提取单词级时间戳 |
| `align_and_cut.py` | Cohere ASR文本 + Whisper时间戳对齐, 句子级音频切割 |
| `anki_api.py` | genanki 生成 .apkg (含嵌入音频) — **备用方案** |
| `anki_sync_push.py` | **主推方案**: 直接写入 SQLite, 免去手动导入 |
| `app.py` | Streamlit 全链路 Web 应用 |
| `test_pipeline.py` | 测试脚本 |

### 3.2 核心流程

```
德语音频 (MP3/WAV)
  → Cohere ASR (CPU) → 德语文本
  → faster-whisper (tiny/int8) → 词级时间戳
  → align_and_cut.py → 句子级对齐 + 音频切割为 clip_001.mp3 ...
  → GoogleTranslator (deep-translator) → 中文翻译
  → anki_sync_push.py → 直接写 SQLite → 客户端同步
```

### 3.3 卡片格式

| 字段 | 内容格式 |
|------|----------|
| **Front** (正面) | `[sound:clip_001.mp3]` — 纯音频，不显示任何文字 |
| **Back** (背面) | `德语原文\n\n中文翻译` |

---

## 4. `anki_sync_push.py` 详解 (核心模块)

### 4.1 总原则

**anki-cloud standalone sync server 没有 REST API**，只有 Anki sync protocol。卡片必须通过直接操作 SQLite 方式写入。

### 4.2 工作流程

```python
push_cards(sentences, audio_dir, deck_name):
  1. docker stop anki-sync-standalone      # 停容器防锁
  2. cp collection.anki2 → temp_db         # 备份
  3. 备份 → collection.anki2.backup_{ts}   # 保留历史
  4. SQLite 操作:
     a. INSERT INTO notes (id, guid, mid, flds, sfld, csum, ...)
        - flds = "[sound:clip_001.mp3]\x1f德语\n\n中文"
        - csum = crc32(front_field.lower())
        - mid  = 1623434819882 (Basic note type)
     b. INSERT INTO cards (id, nid, did, ord, due, ...)
        - did = deck_id (从 col/decks 表中读取/创建)
        - due = i+1 (学习顺序)
  5. cp temp_db → collection.anki2 + chmod 600
  6. _copy_audio_to_media() → 复制音频到 docker volume media/ 目录
  7. _register_media_files() → 注册到 media.db (SHA1, size, usn, mtime)
  8. docker start anki-sync-standalone + sleep 3
```

### 4.3 关键常量

```python
DATA_DIR = "/var/lib/docker/volumes/anki-cloud_app-data/_data/anki_user"
COLLECTION_DB = DATA_DIR + "/collection.anki2"
MEDIA_DIR = DATA_DIR + "/media"
MEDIA_DB = DATA_DIR + "/media.db"
BASIC_NOTE_TYPE_ID = 1623434819882   # 已存在于数据库中
CONTAINER_NAME = "anki-sync-standalone"
```

### 4.4 Anki 同步账户

| 字段 | 值 |
|------|-----|
| 用户名 | `anki_user` |
| 密码 | `anki_sync_2024` |
| 同步 URL | `http://89.168.93.94:8080` |

### 4.5 已修复的 Bug

**media.db 未注册导致 404**: 早期版本的 `_copy_audio_to_media()` 只复制了音频文件到 media 目录，但没有注册到 `media.db`。客户端同步时通过 media.db 校验媒体文件列表，未注册的音频导致客户端报 404。已添加 `_register_media_files()` 方法修复。

---

## 5. Streamlit 应用 (`app.py`)

### 5.1 页面流程

```
Step 1: 上传音频 (st.file_uploader)
Step 2: 自动识别 + 切割 (Cohere ASR + Whisper + align)
Step 3: 句子列表 + 试听 + 勾选 (checkbox per sentence)
Step 4: 翻译 (Google Translate, DE→ZH)
Step 5: 一键推送 (调用 anki_sync_push.push_cards_to_server)
```

### 5.2 客户端同步指引（app.py 中已内置）

打开 Anki Desktop:
1. 工具 → 设置 → 同步 → 自建同步服务器
2. 服务器: `http://89.168.93.94:8080`（注意: 网络需支持 HTTP，部分家庭网络可能封锁 8080）
3. 用户名: `anki_user` / 密码: `anki_sync_2024`
4. 点击同步按钮 (☁️)

### 5.3 服务日志查看

```bash
sudo journalctl -u anki-streamlit -n 100 --no-pager
sudo docker logs anki-sync-standalone --tail 50
```

---

## 6. 已知问题 & 待办

### 6.1 网络限制 (⚠️ 当前阻塞项)

**问题**: 用户的家庭网络只允许 HTTPS（443端口），不允许 HTTP（8080端口）。
**影响**: 无法从家庭网络使用 Anki 客户端同步到 `http://89.168.93.94:8080`

**可能的解决方案** (待实现):

**方案A: Let's Encrypt + 反向代理 (推荐)**
- 需要一个指向 89.168.93.94 的域名
- 用 Nginx/Caddy 在 443 端口做 HTTPS 反向代理，指向 8080
- 客户端配置同步 URL 为 `https://your-domain.com`
- 需要工具: `letsencrypt-cloudflare` skill

**方案B: Cloudflare Tunnel (frp)**
- 通过 Cloudflare Tunnel 暴露 8080 端口
- 不需要公网 IP 或端口映射

**方案C: 自签证书 + 反向代理**
- 不用域名，自签 SSL 证书
- Anki Desktop 支持自签证书但需要额外配置

### 6.2 Oracle Cloud 安全列表

如果需要从外网直接访问 8501 (Streamlit) 或 8080，需要在 Oracle Cloud Console 中添加 Security List Ingress Rules:
- 来源: `0.0.0.0/0`
- 协议: TCP
- 端口: 8080, 8501
- OS 层 iptables 已放行这些端口

### 6.3 当前测试卡

服务器上当前有 5 张测试卡片（test_001 ~ test_005），牌组「德语听力」，media.db 已注册。用户需先解决 HTTP 访问问题才能同步验证。

---

## 7. 卡片内容示例 (当前测试数据)

| # | 正面 | 背面德语 | 背面中文 |
|---|------|----------|----------|
| 1 | [sound:test_001.mp3] | Die Sonne scheint heute. | 今天阳光明媚。 |
| 2 | [sound:test_002.mp3] | Ich trinke gerne Kaffee. | 我喜欢喝咖啡。 |
| 3 | [sound:test_003.mp3] | Wir fahren morgen nach Berlin. | 我们明天去柏林。 |
| 4 | [sound:test_004.mp3] | Das Wetter ist wunderbar. | 天气真好。 |
| 5 | [sound:test_005.mp3] | Gute Nacht und träum süß! | 晚安，好梦！ |

---

## 8. 快速命令参考

```bash
# 服务状态
sudo systemctl status anki-streamlit
sudo docker ps | grep anki-sync

# 重启服务
sudo systemctl restart anki-streamlit
sudo docker restart anki-sync-standalone

# 查看日志
sudo journalctl -u anki-streamlit -n 50 --no-pager
sudo docker logs anki-sync-standalone --tail 50

# 查看数据库状态
cd /opt/anki-app && /opt/anki-venv/bin/python anki_sync_push.py info

# 手动推送测试卡片
/opt/anki-venv/bin/python -c "
from anki_sync_push import push_cards_to_server
sentences = [{'audio_filename':'test.mp3','german_text':'Hallo','chinese_text':'你好'}]
result = push_cards_to_server(sentences, '/tmp/audio', '德语听力')
print(result)
"
```
