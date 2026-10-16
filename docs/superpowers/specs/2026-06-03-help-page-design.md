# 用户使用文档和帮助页 — 设计文档

**日期**: 2026-06-03
**状态**: 已批准

## 概述

在应用内新增帮助页面，用户可随时从导航栏访问。帮助内容存储在数据库中，管理员可通过后台动态编辑（Markdown 格式），无需重新部署前端。

## 需求

- 帮助页完全公开，未登录用户也可访问
- 覆盖三个内容分类：任务与音频处理、收藏与公共库、Anki 推送
- 管理员可在后台新增、编辑、删除、发布/下架帮助文章
- 内容使用 Markdown 格式，支持实时预览

## 数据模型

新增 `HelpArticle` 表：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| slug | String(100) | UNIQUE, NOT NULL | URL 友好标识，如 `anki-push-guide` |
| title | String(200) | NOT NULL | 文章标题 |
| content | Text | NOT NULL, default="" | Markdown 内容 |
| category | String(50) | NOT NULL | 分类：`tasks` / `collections` / `anki` |
| sort_order | Integer | NOT NULL, default=0 | 同分类内排序，小在前 |
| is_published | Boolean | NOT NULL, default=False | 是否发布 |
| created_at | DateTime | server_default=now | 创建时间 |
| updated_at | DateTime | onupdate=now | 更新时间 |

分类枚举：
- `tasks` — 任务与音频处理
- `collections` — 收藏与公共库
- `anki` — Anki 推送

## 后端 API

### 公开 API（无需认证）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/help/categories` | 获取所有分类及其已发布文章列表 |
| GET | `/help/articles/{slug}` | 获取单篇已发布文章详情 |

`GET /help/categories` 返回格式：
```json
[
  {
    "category": "tasks",
    "label": "任务与音频处理",
    "articles": [
      { "slug": "upload-guide", "title": "如何上传音频" },
      { "slug": "segment-edit", "title": "片段编辑指南" }
    ]
  }
]
```

`GET /help/articles/{slug}` 返回格式：
```json
{
  "slug": "upload-guide",
  "title": "如何上传音频",
  "content": "# 如何上传音频\n\n...",
  "category": "tasks",
  "updated_at": "2026-06-03T12:00:00Z"
}
```

### 管理 API（需 admin 认证）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/help/articles` | 获取所有文章（含未发布） |
| POST | `/admin/help/articles` | 创建文章 |
| PUT | `/admin/help/articles/{id}` | 更新文章 |
| DELETE | `/admin/help/articles/{id}` | 删除文章 |

新增路由文件 `routers/help.py`，管理端点挂载在已有的 admin_router 下。

## 前端页面

### 帮助页 `/help`（公开，无需登录）

- **布局**：左侧分类导航（折叠式）+ 右侧 Markdown 渲染区域
- **分类导航**：三个分类，点击展开显示该分类下的文章列表，点击文章标题加载内容
- **文章内容**：使用 `marked` 渲染 Markdown，`highlight.js` 代码高亮
- **默认行为**：进入帮助页时自动加载第一个分类的第一篇文章
- **路由**：`/help` 显示分类列表，`/help/:slug` 显示指定文章

### 导航栏变更

在 App.vue 导航栏中添加「帮助」按钮，位于「公共库」按钮之后，登录/未登录均可见。

### 管理后台「帮助文档」Tab

在 AdminView.vue 新增「帮助文档」选项卡：
- **文章列表**：表格显示所有文章（标题、分类、排序、发布状态），支持按分类筛选
- **编辑弹窗**：左侧 Markdown textarea + 右侧实时预览
- **操作**：新增、编辑、删除、发布/下架切换

## 前端依赖

- `marked` — Markdown 渲染为 HTML
- `highlight.js` — 代码块语法高亮（可选）

## 文件变更清单

### 后端新增
- `backend/app/models.py` — 新增 HelpArticle 模型
- `backend/app/routers/help.py` — 新增帮助路由
- `backend/app/schemas_help.py` — 新增帮助相关 schema
- `backend/app/main.py` — 注册 help_router

### 前端新增
- `frontend/src/views/HelpView.vue` — 帮助页面
- `frontend/src/api/help.js` — 帮助 API 接口

### 前端修改
- `frontend/src/router/index.js` — 新增 `/help` 和 `/help/:slug` 路由
- `frontend/src/App.vue` — 导航栏添加「帮助」按钮
- `frontend/src/views/AdminView.vue` — 新增「帮助文档」Tab
- `frontend/src/api/admin.js` — 新增帮助文档管理 API

## 初始内容

部署后需通过管理后台创建初始帮助文章，建议包含：
- 任务与音频处理：上传音频指南、任务状态说明、片段编辑方法
- 收藏与公共库：收藏集管理、公共库浏览、点赞与收藏
- Anki 推送：推送配置入门、多配置管理、AnkiWeb vs 自建服务器
