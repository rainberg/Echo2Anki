# 语音转文字功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有网站上新增独立的语音转文字功能页面，使用服务器本地 Cohere Transcribe 模型，支持 14 种语言，单线程队列处理。

**Architecture:** 后端新增 Transcription 模型 + 转录路由 + 单线程 Worker 队列。前端新增 TranscribeView 页面 + API 客户端模块。导航栏在"收藏集"后、"Anki"前添加"转录"入口。

**Tech Stack:** FastAPI + SQLAlchemy async (后端), Vue 3 + Naive UI (前端), CohereASR 本地 Python 调用 (cohere_asr.py)

---

## File Structure

| Action | File | Responsibility |
|---|---|---|
| Modify | `backend/app/models.py` | 新增 Transcription 模型 |
| Create | `backend/app/routers/transcribe.py` | 转录 API 路由（上传/列表/详情/删除） |
| Create | `backend/app/transcribe_worker.py` | 单线程转录 Worker 队列 |
| Modify | `backend/app/config.py` | 新增 COHERE_DEVICE 配置 |
| Modify | `backend/app/main.py` | 注册转录路由 + lifespan 中启动 Worker |
| Create | `frontend/src/api/transcribe.js` | 转录 API 客户端 |
| Create | `frontend/src/views/TranscribeView.vue` | 转录页面组件 |
| Modify | `frontend/src/router/index.js` | 新增 /transcribe 路由 |
| Modify | `frontend/src/App.vue` | 导航栏添加"转录"按钮 |

---

### Task 1: 新增 Transcription 数据模型

**Files:**
- Modify: `backend/app/models.py` (文件末尾追加)

- [ ] **Step 1: 在 models.py 末尾添加 Transcription 模型**

```python
class Transcription(Base):
    __tablename__ = "transcriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    language = Column(String(5), default="de", nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    text = Column(Text, default="")
    error_message = Column(Text, default="")
    file_size = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", lazy="selectin")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add Transcription model for speech-to-text feature"
```

---

### Task 2: 新增 COHERE_DEVICE 配置

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: 在 Settings 类中添加 COHERE_DEVICE 字段**

在 `config.py` 的 `Settings` 类中，`FRONTEND_DIST` 之前添加：

```python
    COHERE_DEVICE: str = "cpu"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add COHERE_DEVICE config for transcribe worker"
```

---

### Task 3: 创建转录 Worker

**Files:**
- Create: `backend/app/transcribe_worker.py`

- [ ] **Step 1: 创建 transcribe_worker.py**

```python
"""
Single-threaded transcription worker.
Processes one Cohere ASR job at a time from a FIFO queue.
"""

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Transcription

logger = logging.getLogger(__name__)

_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            settings.DATABASE_URL_SYNC,
            pool_size=5,
            max_overflow=10,
        )
    return _sync_engine


class TranscribeWorker:
    """Single-threaded worker that processes transcription jobs sequentially."""

    def __init__(self):
        self._queue: list[str] = []  # transcription IDs
        self._lock = threading.Lock()
        self._active = False
        self._cohere_asr = None
        self._max_queue = 10

    @property
    def queue_size(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def _get_asr(self):
        """Lazy-load Cohere ASR model (heavy, only load when first needed)."""
        if self._cohere_asr is None:
            from cohere_asr import CohereASR
            logger.info("Loading Cohere ASR model on %s...", settings.COHERE_DEVICE)
            self._cohere_asr = CohereASR(device=settings.COHERE_DEVICE)
            logger.info("Cohere ASR model loaded")
        return self._cohere_asr

    def submit(self, transcription_id: str) -> bool:
        """Add a transcription job to the queue. Returns False if queue is full."""
        with self._lock:
            if len(self._queue) >= self._max_queue:
                return False
            self._queue.append(transcription_id)
            if not self._active:
                self._active = True
                t = threading.Thread(target=self._run_loop, daemon=True)
                t.start()
        return True

    def _run_loop(self):
        """Process jobs from the queue one at a time."""
        while True:
            with self._lock:
                if not self._queue:
                    self._active = False
                    return
                transcription_id = self._queue.pop(0)

            self._process_job(transcription_id)

    def _process_job(self, transcription_id: str):
        engine = _get_sync_engine()
        with Session(engine) as db:
            record = db.execute(
                select(Transcription).where(Transcription.id == transcription_id)
            ).scalar_one_or_none()
            if not record:
                logger.warning("Transcription %s not found", transcription_id)
                return

            # Build temp file path
            tmp_dir = os.path.join(settings.WORK_DIR, "transcriptions")
            os.makedirs(tmp_dir, exist_ok=True)
            tmp_path = os.path.join(tmp_dir, f"{transcription_id}_{record.filename}")

            if not os.path.exists(tmp_path):
                record.status = "failed"
                record.error_message = "Audio file not found on disk"
                record.updated_at = datetime.now(timezone.utc)
                db.commit()
                return

            try:
                record.status = "processing"
                record.updated_at = datetime.now(timezone.utc)
                db.commit()

                asr = self._get_asr()
                text = asr.transcribe(tmp_path, language=record.language)

                record.status = "done"
                record.text = text
                record.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info("Transcription %s completed", transcription_id)

            except Exception as exc:
                logger.exception("Transcription %s failed", transcription_id)
                record.status = "failed"
                record.error_message = str(exc)[:500]
                record.updated_at = datetime.now(timezone.utc)
                db.commit()

            finally:
                # Clean up temp file
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass


# Singleton
_worker: Optional[TranscribeWorker] = None


def get_transcribe_worker() -> TranscribeWorker:
    global _worker
    if _worker is None:
        _worker = TranscribeWorker()
    return _worker
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/transcribe_worker.py
git commit -m "feat: add single-threaded TranscribeWorker with Cohere ASR"
```

---

### Task 4: 创建转录 API 路由

**Files:**
- Create: `backend/app/routers/transcribe.py`

- [ ] **Step 1: 创建 transcribe 路由文件**

```python
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import Transcription, User
from app.config import settings
from app.transcribe_worker import get_transcribe_worker

router = APIRouter(prefix="/transcribe", tags=["transcribe"])

ALLOWED_EXTENSIONS = {".flac", ".mp3", ".mpeg", ".mpga", ".ogg", ".wav"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
SUPPORTED_LANGUAGES = {"de", "en", "fr", "it", "es", "pt", "el", "nl", "pl", "vi", "zh", "ar", "ja", "ko"}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_transcription(
    file: UploadFile = File(...),
    language: str = Form("de"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate language
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}. Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}")

    # Validate file extension
    filename = file.filename or "audio.wav"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size: 25MB")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Create DB record
    record = Transcription(
        user_id=user.id,
        filename=filename,
        language=language,
        status="pending",
        file_size=len(content),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    # Save file to temp dir
    tmp_dir = os.path.join(settings.WORK_DIR, "transcriptions")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{record.id}_{filename}")
    with open(tmp_path, "wb") as f:
        f.write(content)

    # Submit to worker queue
    worker = get_transcribe_worker()
    if not worker.submit(str(record.id)):
        # Queue full — clean up
        os.remove(tmp_path)
        record.status = "failed"
        record.error_message = "转录队列已满，请稍后重试"
        record.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(record)
        raise HTTPException(status_code=429, detail="转录队列已满，请稍后重试")

    return {
        "id": str(record.id),
        "filename": record.filename,
        "language": record.language,
        "status": record.status,
        "file_size": record.file_size,
        "queue_size": worker.queue_size,
        "created_at": record.created_at.isoformat(),
    }


@router.get("/")
async def list_transcriptions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transcription)
        .where(Transcription.user_id == user.id)
        .order_by(Transcription.created_at.desc())
        .limit(50)
    )
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "filename": r.filename,
            "language": r.language,
            "status": r.status,
            "file_size": r.file_size,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in records
    ]


@router.get("/{transcription_id}")
async def get_transcription(
    transcription_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transcription).where(
            Transcription.id == uuid.UUID(transcription_id),
            Transcription.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Transcription not found")

    return {
        "id": str(record.id),
        "filename": record.filename,
        "language": record.language,
        "status": record.status,
        "text": record.text,
        "error_message": record.error_message,
        "file_size": record.file_size,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


@router.delete("/{transcription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transcription(
    transcription_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transcription).where(
            Transcription.id == uuid.UUID(transcription_id),
            Transcription.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Transcription not found")
    await db.delete(record)
    await db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/transcribe.py
git commit -m "feat: add transcribe API router (upload/list/detail/delete)"
```

---

### Task 5: 注册路由到 main.py

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 添加 import 和注册路由**

在 `main.py` 的 import 区域添加：

```python
from app.routers.transcribe import router as transcribe_router
```

在路由注册区域（`app.include_router(swipe_router, prefix="/api")` 之后）添加：

```python
app.include_router(transcribe_router, prefix="/api")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: register transcribe router in main.py"
```

---

### Task 6: 创建前端 API 客户端

**Files:**
- Create: `frontend/src/api/transcribe.js`

- [ ] **Step 1: 创建 transcribe.js**

```javascript
import api from './client'

export function uploadTranscription(file, language = 'de') {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('language', language)
  return api.post('/transcribe/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export function listTranscriptions() {
  return api.get('/transcribe/')
}

export function getTranscription(id) {
  return api.get(`/transcribe/${id}`)
}

export function deleteTranscription(id) {
  return api.delete(`/transcribe/${id}`)
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/transcribe.js
git commit -m "feat: add transcribe API client module"
```

---

### Task 7: 创建转录页面组件

**Files:**
- Create: `frontend/src/views/TranscribeView.vue`

- [ ] **Step 1: 创建 TranscribeView.vue**

```vue
<template>
  <div class="transcribe-container">
    <!-- Upload Area -->
    <n-card title="语音转文字" size="small">
      <n-upload
        :max="1"
        :default-upload="false"
        accept=".flac,.mp3,.mpeg,.mpga,.ogg,.wav"
        @change="handleFileChange"
      >
        <n-upload-dragger>
          <n-text style="font-size: 16px">点击或拖拽音频文件到此处</n-text>
          <n-text depth="3" style="font-size: 13px; display: block; margin-top: 4px">
            支持 FLAC / MP3 / OGG / WAV，最大 25MB
          </n-text>
        </n-upload-dragger>
      </n-upload>

      <n-space vertical style="margin-top: 12px">
        <n-space align="center">
          <n-text>语言：</n-text>
          <n-select v-model:value="language" :options="languageOptions" style="width: 180px" />
        </n-space>
        <n-button type="primary" :loading="uploading" :disabled="!selectedFile" @click="handleUpload" block>
          {{ uploading ? '上传中...' : '开始转录' }}
        </n-button>
      </n-space>
    </n-card>

    <!-- Current Job Status -->
    <n-card v-if="currentJob" size="small" style="margin-top: 16px">
      <template #header>
        <n-space align="center">
          <n-spin v-if="currentJob.status === 'pending' || currentJob.status === 'processing'" :size="16" />
          <n-tag :type="statusType(currentJob.status)" size="small">{{ statusLabel(currentJob.status) }}</n-tag>
          <n-text>{{ currentJob.filename }}</n-text>
        </n-space>
      </template>
      <n-text v-if="currentJob.status === 'pending'" depth="3">排队中，前方 {{ currentJob.queue_size || 0 }} 个任务</n-text>
      <n-text v-else-if="currentJob.status === 'processing'" depth="3">正在转录，请稍候...</n-text>
      <template v-else-if="currentJob.status === 'done'">
        <n-input type="textarea" :value="currentJob.text" readonly :rows="8" style="font-family: monospace" />
        <n-button size="small" style="margin-top: 8px" @click="copyText(currentJob.text)">复制文本</n-button>
      </template>
      <n-text v-else-if="currentJob.status === 'failed'" type="error">{{ currentJob.error_message }}</n-text>
    </n-card>

    <!-- History -->
    <n-card title="转录历史" size="small" style="margin-top: 16px">
      <n-empty v-if="!records.length" description="暂无转录记录" />
      <n-list bordered v-else>
        <n-list-item v-for="rec in records" :key="rec.id">
          <n-thing>
            <template #header>
              <n-tag :type="statusType(rec.status)" size="small">{{ statusLabel(rec.status) }}</n-tag>
              <n-text style="margin-left: 8px">{{ rec.filename }}</n-text>
            </template>
            <template #description>
              <n-text depth="3" style="font-size: 13px">
                {{ languageName(rec.language) }} · {{ formatSize(rec.file_size) }} · {{ formatDate(rec.created_at) }}
              </n-text>
            </template>
            <template #action>
              <n-space>
                <n-button v-if="rec.status === 'done'" size="tiny" @click="viewDetail(rec)">查看</n-button>
                <n-popconfirm @positive-click="handleDelete(rec)">
                  <template #trigger><n-button size="tiny" type="error" ghost>删除</n-button></template>
                  确定删除？
                </n-popconfirm>
              </n-space>
            </template>
          </n-thing>
        </n-list-item>
      </n-list>
    </n-card>

    <!-- Detail Modal -->
    <n-modal v-model:show="showDetail" preset="card" title="转录结果" style="max-width: 700px">
      <template v-if="detailRecord">
        <n-text depth="3" style="font-size: 13px; display: block; margin-bottom: 8px">
          {{ detailRecord.filename }} · {{ languageName(detailRecord.language) }} · {{ formatDate(detailRecord.created_at) }}
        </n-text>
        <n-input type="textarea" :value="detailRecord.text" readonly :rows="12" style="font-family: monospace" />
        <n-button size="small" style="margin-top: 8px" @click="copyText(detailRecord.text)">复制文本</n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { uploadTranscription, listTranscriptions, getTranscription, deleteTranscription } from '../api/transcribe'

const message = useMessage()

const language = ref('de')
const selectedFile = ref(null)
const uploading = ref(false)
const currentJob = ref(null)
const records = ref([])
const showDetail = ref(false)
const detailRecord = ref(null)
let pollTimer = null

const languageOptions = [
  { label: '🇩🇪 德语', value: 'de' },
  { label: '🇬🇧 英语', value: 'en' },
  { label: '🇫🇷 法语', value: 'fr' },
  { label: '🇮🇹 意大利语', value: 'it' },
  { label: '🇪🇸 西班牙语', value: 'es' },
  { label: '🇵🇹 葡萄牙语', value: 'pt' },
  { label: '🇬🇷 希腊语', value: 'el' },
  { label: '🇳🇱 荷兰语', value: 'nl' },
  { label: '🇵🇱 波兰语', value: 'pl' },
  { label: '🇻🇳 越南语', value: 'vi' },
  { label: '🇨🇳 中文', value: 'zh' },
  { label: '🇸🇦 阿拉伯语', value: 'ar' },
  { label: '🇯🇵 日语', value: 'ja' },
  { label: '🇰🇷 韩语', value: 'ko' },
]

const LANG_NAMES = {
  de: '德语', en: '英语', fr: '法语', it: '意大利语', es: '西班牙语',
  pt: '葡萄牙语', el: '希腊语', nl: '荷兰语', pl: '波兰语', vi: '越南语',
  zh: '中文', ar: '阿拉伯语', ja: '日语', ko: '韩语',
}

function languageName(code) { return LANG_NAMES[code] || code }

function statusType(s) {
  if (s === 'done') return 'success'
  if (s === 'failed') return 'error'
  if (s === 'processing') return 'warning'
  return 'default'
}

function statusLabel(s) {
  if (s === 'pending') return '排队中'
  if (s === 'processing') return '转录中'
  if (s === 'done') return '完成'
  if (s === 'failed') return '失败'
  return s
}

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function formatDate(dt) {
  return dt ? new Date(dt).toLocaleString('zh-CN') : ''
}

function handleFileChange({ file }) {
  selectedFile.value = file?.file || null
}

async function handleUpload() {
  if (!selectedFile.value) return
  uploading.value = true
  try {
    const { data } = await uploadTranscription(selectedFile.value, language.value)
    currentJob.value = data
    message.success('已提交转录任务')
    startPolling(data.id)
    await fetchRecords()
  } catch (err) {
    message.error(err.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

function startPolling(id) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const { data } = await getTranscription(id)
      currentJob.value = data
      if (data.status === 'done' || data.status === 'failed') {
        stopPolling()
        await fetchRecords()
      }
    } catch {
      stopPolling()
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function fetchRecords() {
  try {
    const { data } = await listTranscriptions()
    records.value = data
  } catch {}
}

function viewDetail(rec) {
  detailRecord.value = rec
  showDetail.value = true
}

async function handleDelete(rec) {
  try {
    await deleteTranscription(rec.id)
    message.success('已删除')
    await fetchRecords()
  } catch {
    message.error('删除失败')
  }
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => message.success('已复制')).catch(() => message.error('复制失败'))
}

onMounted(() => {
  fetchRecords()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.transcribe-container {
  max-width: 900px;
  margin: 0 auto;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/TranscribeView.vue
git commit -m "feat: add TranscribeView page with upload, polling, history"
```

---

### Task 8: 注册前端路由

**Files:**
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: 在路由数组中添加 /transcribe 路由**

在 `Anki` 路由之前添加：

```javascript
  {
    path: '/transcribe',
    name: 'Transcribe',
    component: () => import('../views/TranscribeView.vue'),
    meta: { auth: true },
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router/index.js
git commit -m "feat: add /transcribe route"
```

---

### Task 9: 导航栏添加"转录"按钮

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 在导航栏中添加"转录"按钮**

在 `App.vue` 模板中，找到收藏集按钮行（`@click="$router.push('/collections')"`）之后、Anki 按钮之前，添加：

```html
              <n-button size="tiny" quaternary :type="currentRoute === '/transcribe' ? 'primary' : 'default'" @click="$router.push('/transcribe')">转录</n-button>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.vue
git commit -m "feat: add Transcribe button to navbar between Collections and Anki"
```

---

### Task 10: 数据库迁移 + 端到端验证

**Files:** 无新文件

- [ ] **Step 1: 重启后端服务，确认表自动创建**

后端使用 `Base.metadata.create_all` 自动建表，重启即可。

- [ ] **Step 2: 验证 API 端点可用**

```bash
curl -s https://anki.3mudi.com/api/transcribe/ -H "Authorization: Bearer <token>" | head -5
```

预期返回空列表 `[]`

- [ ] **Step 3: 验证前端页面可访问**

浏览器打开 `https://anki.3mudi.com/transcribe`，确认页面正常渲染。

- [ ] **Step 4: Commit（如有修复）**

```bash
git add -A
git commit -m "fix: adjustments from end-to-end testing"
```
