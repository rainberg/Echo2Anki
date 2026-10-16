# 语音转文字功能设计

## 概述

在现有网站上新增独立的语音转文字功能页面，使用服务器本地部署的 Cohere Transcribe 模型（Python 调用），支持 14 种语言转录，结果保存历史记录。

## 需求

- **使用场景**：通用转录工具，不限特定用途
- **访问权限**：登录用户专属
- **输入方式**：上传本地音频文件（flac/mp3/mpeg/mpga/ogg/wav）
- **语言**：默认德语，用户可切换其他 13 种语言
- **历史记录**：转录结果保存到数据库，可查看和删除
- **并发限制**：服务器本地 Cohere 模型不能并发，需使用队列

## 方案

**后端代理模式**：前端上传音频 → 后端接收 → 加入单线程队列 → Worker 调用本地 Cohere → 返回结果。

选择此方案的原因：
- API Key / 模型不暴露给前端
- 可做速率限制和用量统计
- 与现有架构一致
- 队列机制保证不并发

## 数据模型

新增 `transcriptions` 表：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID | 主键 |
| user_id | UUID FK → users | 所属用户 |
| filename | String(255) | 原始文件名 |
| language | String(5) | ISO-639-1 语言代码，默认 "de" |
| status | String(20) | "pending" / "processing" / "done" / "failed" |
| text | Text | 转录结果文本 |
| error_message | Text | 失败时的错误信息 |
| file_size | Integer | 文件大小（字节） |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

不保存原始音频文件，转录完成后删除临时文件。

## 后端 API

新增路由文件 `backend/app/routers/transcribe.py`，挂载到 `/api/transcribe`。

### 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/transcribe/` | 上传音频文件，加入转录队列 |
| GET | `/api/transcribe/` | 获取转录历史列表（分页，最新在前） |
| GET | `/api/transcribe/{id}` | 获取单条转录详情（含状态） |
| DELETE | `/api/transcribe/{id}` | 删除转录记录 |

### 转录流程

1. 前端上传音频文件（multipart/form-data），指定语言（默认 de）
2. 后端验证文件格式和大小（≤25MB，仅 flac/mp3/mpeg/mpga/ogg/wav）
3. 后端创建 Transcription 记录（status=pending），保存文件到临时目录
4. 将任务加入单线程转录队列
5. Worker 从队列取出任务，更新 status=processing
6. Worker 调用本地 `CohereASR.transcribe(file, language)`
7. 成功 → 更新 status=done, text=结果
8. 失败 → 更新 status=failed, error_message=错误信息
9. 清理临时文件
10. 前端轮询 GET `/api/transcribe/{id}` 获取状态

### 配置

在 `config.py` 中新增：
- `COHERE_DEVICE`: String，默认 "cpu"

无需 Cohere API Key（本地模型）。

### 转录队列

复用 `TaskWorkerV2` 的队列模式，但独立实例，max_workers=1：
- 单线程处理，保证不并发
- 队列积压 >10 时拒绝新请求（返回 429）

## 前端页面

### 路由

新增 `/transcribe` 路由，对应 `TranscribeView.vue`。

### 导航栏

在"收藏集"之后、"Anki"之前添加"转录"按钮。

导航栏顺序：公共库 | 仪表盘 | 任务 | 收藏集 | **转录** | Anki | 帮助

### 页面布局

1. **上传区域**（顶部卡片）
   - 文件拖拽/选择上传区（NUpload）
   - 语言选择下拉框（默认德语，14 种可选：de/en/fr/it/es/pt/el/nl/pl/vi/zh/ar/ja/ko）
   - 提交按钮
   - 队列状态提示（如"排队中，前方 2 个任务"）

2. **转录结果区域**（上传后显示）
   - 状态指示（排队中 / 转录中 / 完成 / 失败）
   - 完成后显示转录文本，支持一键复制
   - 失败时显示错误信息

3. **历史记录列表**（下方卡片列表）
   - 文件名、语言、状态、创建时间
   - 点击展开查看转录文本
   - 支持删除

### 状态轮询

- 提交后每 3 秒轮询 GET `/api/transcribe/{id}`
- 状态为 done 或 failed 时停止轮询

## 错误处理与边界

- **文件格式校验**：后端严格校验扩展名，不合法返回 400
- **文件大小限制**：25MB 上限，超出返回 413
- **队列满**：队列积压 >10 时返回 429，提示稍后重试
- **Cohere 调用失败**：捕获异常，记录 error_message，status=failed
- **临时文件清理**：转录完成（无论成功失败）后删除临时音频文件
- **权限校验**：所有端点需登录，删除操作校验记录归属

## 支持的语言

Cohere Transcribe 支持 14 种语言（ISO-639-1）：

| 代码 | 语言 |
|---|---|
| de | 德语（默认） |
| en | 英语 |
| fr | 法语 |
| it | 意大利语 |
| es | 西班牙语 |
| pt | 葡萄牙语 |
| el | 希腊语 |
| nl | 荷兰语 |
| pl | 波兰语 |
| vi | 越南语 |
| zh | 中文 |
| ar | 阿拉伯语 |
| ja | 日语 |
| ko | 韩语 |
