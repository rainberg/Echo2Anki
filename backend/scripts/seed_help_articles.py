"""Seed help articles into the database.

Usage: python -m scripts.seed_help_articles
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.database import async_session
from app.models import HelpArticle

ARTICLES = [
    # ─── tasks: 任务与音频处理 ──────────────────────────────────────────
    {
        "slug": "upload-audio",
        "title": "如何上传音频",
        "category": "tasks",
        "sort_order": 1,
        "is_published": True,
        "content": """\
# 如何上传音频

上传音频是使用本平台的第一步，支持常见的音频格式。

## 支持的格式

- **MP3** — 最常用的音频格式
- **WAV** — 无损音频格式
- **M4A** — Apple 音频格式
- **OGG** — 开源音频格式
- **FLAC** — 无损压缩格式

## 上传步骤

1. 登录后，点击导航栏中的「任务」
2. 点击页面上的上传区域或拖拽音频文件到上传区
3. 选择引擎和模型大小（默认使用 Local Whisper small 模型）
4. 点击确认上传

## 注意事项

- 单个文件大小建议不超过 500MB
- 上传后系统会自动进行音频标准化处理
- 处理时间取决于音频时长和所选引擎
- 系统会根据音频时长预扣积分，处理完成后按实际时长结算

## 文件去重

如果上传的音频文件与之前的文件完全相同（文件哈希一致），系统会提示已存在，避免重复处理。
""",
    },
    {
        "slug": "task-status",
        "title": "任务状态说明",
        "category": "tasks",
        "sort_order": 2,
        "is_published": True,
        "content": """\
# 任务状态说明

上传音频后，任务会经历以下阶段：

## 任务阶段

| 阶段 | 说明 |
|------|------|
| **pending** | 等待处理，系统正在排队 |
| **normalizing** | 音频标准化中，转换格式和采样率 |
| **segmenting** | 音频分割中，按语音停顿切分片段 |
| **transcribing** | 语音识别中，生成德语文本 |
| **translating** | 翻译中，生成中文译文 |
| **completed** | 处理完成，可以查看和编辑 |
| **failed** | 处理失败，可查看错误信息 |

## 处理进度

任务详情页会显示实时进度百分比和当前阶段信息。WebSocket 连接会推送进度更新，无需手动刷新。

## 失败重试

如果任务处理失败，可以在任务详情页点击「重试」，可选择更换引擎重新处理。

## 积分说明

- 上传时预扣积分 = 音频时长 × 引擎单价
- 处理完成后按实际时长结算，多退少补
- 失败的任务会退还预扣积分
""",
    },
    {
        "slug": "segment-editing",
        "title": "片段编辑指南",
        "category": "tasks",
        "sort_order": 3,
        "is_published": True,
        "content": """\
# 片段编辑指南

音频处理完成后，会被分割为多个片段，每个片段包含德语原文和中文译文。

## 编辑操作

- **德语文本** — 可以修正语音识别错误
- **中文译文** — 可以修正翻译不准确的地方
- 修改后自动保存

## 音频播放

- 点击片段可以播放对应的音频片段
- 支持逐片段播放，方便对照修改
- 播放器支持暂停、进度拖动

## 片段操作

- 每个片段可以单独添加到收藏集
- 可以选择片段推送到 Anki
- 在推送前确认文本内容，确保卡片质量

## 小技巧

> 建议先通听一遍所有片段，再逐个修正文本。重点关注专有名词和口语化表达，这些是语音识别最容易出错的地方。
""",
    },
    # ─── collections: 收藏与公共库 ──────────────────────────────────────
    {
        "slug": "collection-guide",
        "title": "收藏集管理",
        "category": "collections",
        "sort_order": 1,
        "is_published": True,
        "content": """\
# 收藏集管理

收藏集用于整理和管理你感兴趣的音频片段。

## 创建收藏集

1. 进入「收藏集」页面
2. 点击「新建收藏集」
3. 输入名称和描述（可选）

## 添加片段

有以下几种方式添加片段到收藏集：

- 在任务详情页，点击片段旁的收藏按钮
- 在公共库浏览时，收藏感兴趣的共享资源
- 从其他收藏集复制片段

## 管理收藏集

- **重命名** — 修改收藏集名称和描述
- **删除片段** — 从收藏集中移除不需要的片段
- **推送开关** — 可以单独控制每个片段是否参与 Anki 推送
- **删除收藏集** — 删除整个收藏集（不会删除原始片段）

## 推送到 Anki

收藏集是推送到 Anki 的基本单位。选择一个收藏集，配置推送目标，即可将启用了推送的片段制作为 Anki 卡片。
""",
    },
    {
        "slug": "public-library",
        "title": "公共库浏览",
        "category": "collections",
        "sort_order": 2,
        "is_published": True,
        "content": """\
# 公共库浏览

公共库是所有用户共享的音频资源库，无需登录即可浏览和播放。

## 浏览资源

- 首页默认展示公共库内容
- 可以按难度、分类筛选
- 支持关键词搜索

## 互动功能

| 功能 | 未登录 | 已登录 |
|------|--------|--------|
| 浏览和播放 | ✅ | ✅ |
| 点赞 | ❌ | ✅ |
| 收藏到收藏集 | ❌ | ✅ |
| 分享自己的资源 | ❌ | ✅ |

> 未登录用户点赞或收藏时会提示先登录。

## 分享你的资源

1. 在任务详情页，点击「分享到公共库」
2. 填写标题、描述、难度等信息
3. 确认分享后，其他用户即可在公共库中看到

## 资源质量

建议分享时添加清晰的标题和描述，选择合适的难度标签，帮助其他用户快速找到所需内容。
""",
    },
    # ─── anki: Anki 推送 ────────────────────────────────────────────────
    {
        "slug": "anki-push-guide",
        "title": "Anki 推送入门",
        "category": "anki",
        "sort_order": 1,
        "is_published": True,
        "content": """\
# Anki 推送入门

将音频片段推送到 Anki 是本平台的核心功能，让你可以在 Anki 中复习德语听力。

## 推送方式

支持两种推送方式：

### 1. 自建 Anki 同步服务器

适用于自己搭建了 Anki Sync Server 的用户。

- 需要自建 Anki 同步服务器（如 [anki-sync-server](https://github.com/ankicommunity/anki-sync-server)）
- 配置同步服务器的用户名和密码
- 推送后通过 Anki 客户端同步即可获取卡片
- 适合有服务器的进阶用户

**配置步骤：**

1. 确保你的 Anki 同步服务器已正常运行
2. 在本平台「Anki」页面点击「添加配置」
3. 推送方式选择「自建 Anki 服务器」
4. 填写同步用户名和同步密码（与服务器端配置一致）
5. 填写牌组名称（如 `Default`）
6. 保存配置

### 2. AnkiWeb

适用于使用 AnkiWeb 官方同步服务的用户。

- 需要输入 AnkiWeb 账号密码
- 推送后通过 Anki 客户端同步即可获取卡片
- 无需自建服务器，开箱即用
- 适合大多数用户

**配置步骤：**

1. 在本平台「Anki」页面点击「添加配置」
2. 推送方式选择「AnkiWeb」
3. 填写 AnkiWeb 用户名和密码
4. 填写牌组名称（如 `Default`）
5. 保存配置

## 卡片内容

每张推送的卡片包含：

- **正面** — 德语文本 + 音频播放
- **背面** — 中文译文

## 推送步骤

1. 选择一个收藏集
2. 勾选要推送的目标配置（支持多选）
3. 点击推送
4. 等待推送完成
5. 在 Anki 客户端中点击同步，即可看到新卡片
""",
    },
    {
        "slug": "multi-config",
        "title": "多配置管理",
        "category": "anki",
        "sort_order": 2,
        "is_published": True,
        "content": """\
# 多配置管理

你可以保存多个 Anki 推送配置，推送时选择推送到哪些目标。

## 为什么需要多配置？

- 推送到不同的 Anki 牌组（如不同主题）
- 同时使用自建服务器和 AnkiWeb
- 推送到不同的 Anki 账号

## 管理配置

### 添加配置

1. 进入「Anki」页面
2. 点击「添加配置」
3. 选择推送方式并填写连接信息
4. 配置会自动命名（如「自建服务器 #1」），也可以自定义名称

### 编辑配置

- 点击配置旁的编辑按钮修改连接信息
- 可以修改配置名称，方便区分

### 删除配置

- 删除配置不会影响已推送的卡片
- 删除后无法恢复

## 配置上限

- 每个用户默认最多 4 个配置
- 管理员可以为个别用户调整上限

## 多目标推送

推送时可以同时勾选多个配置，实现一次推送、多端同步。例如：

- 同时推送到本地 Anki 和 AnkiWeb
- 同时推送到不同的牌组
""",
    },
    {
        "slug": "push-troubleshooting",
        "title": "推送问题排查",
        "category": "anki",
        "sort_order": 3,
        "is_published": True,
        "content": """\
# 推送问题排查

## 自建服务器连接失败

**症状：** 推送时提示连接失败

**排查步骤：**

1. 确认 Anki 正在运行
2. 确认 AnkiConnect 插件已安装并启用
3. 检查 AnkiConnect 地址是否正确（默认 `http://localhost:8765`）
4. 如果 Anki 运行在远程服务器，确保网络可达

## AnkiWeb 推送失败

**症状：** 推送时提示认证失败

**排查步骤：**

1. 确认 AnkiWeb 用户名和密码正确
2. 检查 AnkiWeb 账号是否被锁定
3. 尝试在浏览器中手动登录 AnkiWeb 验证

## 部分片段推送失败

**症状：** 推送记录显示部分片段被跳过

**可能原因：**

- 片段的推送开关被关闭
- 片段的音频文件缺失
- 目标牌组不存在（AnkiConnect 模式下会自动创建）

## 推送记录

每次推送都会生成推送记录，包含：

- 推送状态（成功/失败）
- 推送的卡片数量
- 跳过的卡片数量
- 错误信息

在「Anki」页面可以查看推送历史。
""",
    },
]


async def seed():
    async with async_session() as session:
        for article_data in ARTICLES:
            slug = article_data["slug"]
            result = await session.execute(
                select(HelpArticle).where(HelpArticle.slug == slug)
            )
            existing = result.scalar_one_or_none()
            if existing:
                print(f"  更新: {slug}")
                for key, value in article_data.items():
                    setattr(existing, key, value)
            else:
                print(f"  创建: {slug}")
                article = HelpArticle(**article_data)
                session.add(article)

        await session.commit()
        print(f"\n完成！共处理 {len(ARTICLES)} 篇文章。")


if __name__ == "__main__":
    print("正在写入帮助文章...")
    asyncio.run(seed())
