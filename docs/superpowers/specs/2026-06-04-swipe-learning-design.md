# 抖音式学习滑动流 — 设计文档

**日期**: 2026-06-04
**状态**: 已批准

## 概述

开发一款独立的手机 APP（React Native），提供抖音式的全屏沉浸式德语听力学习体验。用户通过滑动手势学习片段，基于难度标注自适应推荐，保持 80% 熟悉 + 20% 挑战的比例。APP 复用现有后端 API，新增滑动流专用 API。

## 平台决策

**选择 React Native 开发独立手机 APP**，原因：
- 原生手势体验丝滑（滑动惯性、回弹效果）
- 音频播放完全可控，无浏览器自动播放限制
- 全屏沉浸感强，真正接近"刷抖音"体验
- 支持推送通知（学习提醒、每日推荐）
- 离线缓存片段，无网络也能刷
- 跨平台（iOS + Android）一套代码

## 核心交互

### 手势定义

| 手势 | 动作 | 视觉反馈 |
|------|------|----------|
| 上滑 | 重复播放当前片段 | 音频从头播放，进度条重置 |
| 下滑 | 展开原文+翻译+解释 | 德语大字 + 中文译文 + 附加说明从下方滑入 |
| 左滑 | 标记"简单" → 播放下一条 | 绿色"简单"闪烁 → 自动切到下一片段 |
| 右滑 | 标记"困难" → 播放下一条 | 红色"困难"闪烁 → 自动切到下一片段 |
| 长按 / 三连击 | 收藏/取消收藏 | 星标动画，收藏集选择弹窗 |

### 视觉布局

全屏竖屏布局：
- **中央**：德语文本大字显示（当前播放的句子）
- **下方**：中文译文（默认隐藏，下滑时展开）
- **底部**：音频进度条 + 播放状态
- **右上角**：难度标签（A1-C2）+ 来源标签
- **左下角**：收藏状态图标

### 状态切换

- **听模式**（默认）：只显示德语文本，专注听力
- **看模式**（下滑触发）：显示德语+中文+解释，辅助理解

## 片段来源

两种来源，用户可切换：
- **公共库**：所有已发布的共享资源的片段，未登录也可用
- **我的片段**：用户自己任务的片段，需登录

## 数据模型

### 新增 `SegmentRating` 表（在现有后端 anki-app 数据库中）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| user_id | UUID | FK, nullable | 用户 ID（未登录时为空） |
| segment_id | UUID | FK, NOT NULL | 片段 ID |
| rating | String(10) | NOT NULL | 标注：`easy` / `hard` |
| is_collected | Boolean | default=False | 是否收藏 |
| created_at | DateTime | server_default=now | 标注时间 |

唯一约束：`(user_id, segment_id)` — 每个用户对每个片段只有一条记录，最新标注覆盖旧标注。

## 推荐算法

### 自适应难度推荐

1. 维护"当前难度水平"，初始值由用户选择（如 B1）
2. **每次请求 10 条片段**：8 条来自当前难度及以下（熟悉区），2 条来自更高难度（挑战区）
3. 难度水平调整规则：
   - 连续标记 5 条"困难" → 当前难度下移一级
   - 连续标记 5 条"简单" → 当前难度上移一级
4. 片段池去重：不重复推送已标注过的片段
5. 难度等级顺序：A1 < A2 < B1 < B2 < C1 < C2

### 片段池

- 公共库片段：通过 PublicShare 关联的 Task 的 Segments，取 difficulty 匹配的
- 我的片段：用户自己 Task 的 Segments

## 后端 API（在现有 anki-app 后端中新增）

### 新增路由文件 `routers/swipe.py`

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/swipe/feed` | 可选 | 获取滑动流片段 |
| POST | `/swipe/rate` | 可选 | 标注片段难度 |
| POST | `/swipe/collect` | 需登录 | 收藏片段到收藏集 |
| GET | `/swipe/stats` | 可选 | 获取推荐统计 |

### `GET /swipe/feed`

参数：
- `source` — `public` / `mine`，默认 `public`
- `limit` — 每批数量，默认 10

返回格式：
```json
{
  "segments": [
    {
      "id": "uuid",
      "german_text": "Ich möchte einen Kaffee bestellen.",
      "chinese_text": "我想点一杯咖啡。",
      "audio_url": "/api/segments/uuid/audio",
      "difficulty": "A2",
      "source_title": "日常对话 #3",
      "duration": 3.5
    }
  ],
  "current_level": "B1",
  "total_rated": 42
}
```

### `POST /swipe/rate`

请求体：
```json
{ "segment_id": "uuid", "rating": "easy" }
```

### `POST /swipe/collect`

请求体：
```json
{ "segment_id": "uuid", "collection_id": "uuid" }
```

### `GET /swipe/stats`

返回格式：
```json
{
  "current_level": "B1",
  "total_rated": 42,
  "easy_count": 30,
  "hard_count": 12,
  "consecutive_easy": 3,
  "consecutive_hard": 0
}
```

## APP 技术架构

### 技术栈

- **React Native** + **Expo**（快速开发，OTA 更新）
- **TypeScript**
- **React Navigation**（路由）
- **react-native-reanimated**（流畅手势动画）
- **react-native-track-player**（音频播放）
- **Zustand** 或 **Redux Toolkit**（状态管理）
- **AsyncStorage**（本地缓存）

### 项目结构（独立仓库）

```
anki-swipe-app/
├── app/
│   ├── screens/
│   │   ├── SwipeScreen.tsx      # 主滑动流页面
│   │   ├── LoginScreen.tsx      # 登录
│   │   ├── SettingsScreen.tsx   # 设置（难度选择等）
│   │   └── StatsScreen.tsx      # 学习统计
│   ├── components/
│   │   ├── SwipeCard.tsx        # 单个片段卡片
│   │   ├── SwipeDeck.tsx        # 滑动卡片堆（手势处理）
│   │   ├── AudioPlayer.tsx      # 音频播放器
│   │   └── DifficultyBadge.tsx  # 难度标签
│   ├── services/
│   │   ├── api.ts               # API 客户端
│   │   ├── audioCache.ts        # 音频预加载和缓存
│   │   └── authService.ts       # 认证服务
│   ├── store/
│   │   └── swipeStore.ts        # 滑动流状态管理
│   └── utils/
│       └── gestures.ts          # 手势工具
├── App.tsx
├── package.json
└── app.json
```

### 认证

复用现有 auth-service（auth.3mudi.com），APP 通过 JWT 认证调用后端 API。

### 音频缓存

- 预加载下 3 条片段的音频文件到本地
- 使用 `react-native-track-player` 播放本地/远程音频
- 支持离线模式：缓存已加载的片段，无网络时仍可刷

### 推送通知

- 每日学习提醒（可配置时间）
- 新推荐片段通知

## 后端变更清单（在现有 anki-app 中）

### 新增
- `backend/app/models.py` — 新增 SegmentRating 模型
- `backend/app/routers/swipe.py` — 新增滑动流路由
- `backend/app/schemas_swipe.py` — 新增滑动流 schema
- `backend/app/main.py` — 注册 swipe_router

## 成本评估

### 后端开发
- 推荐算法 + API：约 1-2 天
- 数据模型 + 测试：约 1 天

### APP 开发
- 项目初始化 + 基础架构：约 1 天
- 滑动手势 + 动画：约 2-3 天
- 音频播放 + 预加载：约 1-2 天
- 认证 + 设置 + 统计页面：约 1-2 天
- UI 打磨 + 测试：约 2 天

### 总计
- **后端 + APP 约 8-13 天**

### 技术风险
- React Native 手势动画需要 `react-native-reanimated` v3，学习曲线较陡
- iOS/Android 音频播放行为差异，需要充分测试
- 推荐冷启动：新用户没有标注数据，初始推荐依赖用户选择的难度等级
- App Store 审核可能需要调整隐私政策等
