# 念念 NianNian

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.110+-green" alt="FastAPI">
  <img src="https://img.shields.io/badge/license-MIT-purple" alt="License">
  <img src="https://img.shields.io/badge/LLM-DeepSeek%20V4-orange" alt="LLM">
  <img src="https://img.shields.io/badge/Embedding-DashScope-blue" alt="Embedding">
</p>

<p align="center">
  <b>让 AI 记住你的一切，成为你的数字分身。</b>
</p>

---

## 这是什么

念念是一个**个人数字镜像 Agent**（Personal Digital Twin）。它通过日记，持续构建用户的深度人格画像、知识图谱和长期记忆，让 LLM 真正「认识」并「理解」你。

与通用 AI 助手不同，念念不是「每次对话都重新认识你」，而是**越聊越懂你**——它会记住你的习惯、偏好、人际关系、情绪模式，甚至在你意识不到的时候，帮你发现自己的变化。

### 一句话总结

> 念念 = 日记分析 + 记忆引擎 + 知识图谱 + 人格画像 + 个性化对话

---

## 核心特性

### 深度记忆系统

念念的记忆不是简单的聊天记录保存，而是一套**从数据到知识到人格**的渐进式记忆引擎。

```
┌─────────────────────────────────────────────────────────────┐
│                    三层记忆架构                               │
├─────────────────────────────────────────────────────────────┤
│  L0 短期记忆 (40 条消息)                                      │
│  · 当前会话上下文，确保对话连贯                                │
│  · 窗口滑动，自动管理，无需手动清理                             │
├─────────────────────────────────────────────────────────────┤
│  L1 中期记忆 (5 个会话摘要)                                    │
│  · 近期对话的压缩回顾，跨会话保持连贯                           │
│  · 摘要维度：话题、关键信息、情绪基调                           │
├─────────────────────────────────────────────────────────────┤
│  L2 长期记忆 (知识图谱 + 人格画像)                              │
│  · 永不丢失的个人档案                                          │
│  · 包含：实体、关系、习惯、偏好、情绪模式、价值观信号             │
│  · 自动编译、去重、一致性检查                                   │
└─────────────────────────────────────────────────────────────┘
```

**双层快照架构（Snapshot）**：利用 LLM 的 KV Cache 机制，将高频使用的记忆分为核心层（冻结）和情境层（缓存），大幅降低每次对话的 Token 开销和推理延迟。

**画像变化检测**：自动监控四种变化类型：
- 习惯消退（90 天无新证据自动标记）
- 特质转变（新信号与旧画像矛盾时触发）
- 偏好变化（兴趣/品味维度的新旧对比）
- 决策模式形成（新决策子维度画像首次生成）

### 人格化对话

对话引擎不仅仅是「回答问题」，而是基于你的完整画像进行**个性化交互**：

- **情境感知**：自动检测对话情境（家庭/工作/社交/决策/媒体），调整回复风格
- **意图识别**：区分「分享」vs「分析」，匹配不同的回复策略
- **知识注入**：对话时自动检索相关实体、日记、时间线事件，重排序后注入上下文
- **工具调用**：支持联网搜索（Tavily）、天气查询（高德地图）、时间感知
- **画像变化提醒**：主动提示用户行为模式的变化（如「你最近跑步频率下降了 40%」）

### 知识图谱

念念会自动从你的数据中提取并构建知识图谱：

```
日记内容 ──→ 信号提取 ──→ 页面创建 ──→ 编译 ──→ 知识图谱
                │              │            │
                ▼              ▼            ▼
          实体识别        关系抽取       一致性检查
          情感标注        链接构建       合并检测
          时间线事件      分类整理       矛盾处理
```

支持的实体类型：人物、地点、习惯、情绪模式、价值观信号、决策模式、偏好、角色、成就等。

### 数据导入

念念通过日记进行数据导入，每条日记会自动提取事件、信号和知识，构建记忆：

| 数据源 | 导入方式 | 提取内容 |
|--------|---------|---------|
| 日记 | 手动创建 / 结构化导入 | 时间线事件、实体、信号、情绪模式、知识页面 |

### 仪表盘可视化

提供情绪变化的可视化分析：

- **情绪季节**：情绪变化的时间序列分析

---

## 技术架构

```
┌──────────────────────────────────────────────────────────────┐
│                         FastAPI                               │
│                   (REST API + SSE 流式响应)                    │
├──────────────────────────────────────────────────────────────┤
│  Routers (9)              │  Services (20+)                  │
│  ─────────────────        │  ─────────────────               │
│  /chat      对话接口       │  chat.py          对话引擎        │
│  /diary     日记接口       │  diary.py         日记处理        │
│  /timeline  时间线接口     │  timeline.py      时间线          │
│  /profile   画像接口       │  profile_builder  画像构建        │
│  /knowledge 知识库接口     │  profile_manager  画像管理        │
│  /import    数据导入接口   │  compiler.py      知识编译        │
│  /insight   洞察分析接口   │  knowledge.py     知识管理        │
│  /quicknote 快速笔记接口   │  rag.py           检索增强        │
│  /monitor   监控接口       │  graph_search.py  实体图搜索      │
│                            │  reranker.py      重排序          │
│                            │  memory.py        记忆管理        │
│                            │  snapshot.py      快照服务        │
│                            │  signals.py       信号提取        │
│                            │  signal_extractor 信号提取器      │
│                            │  change_detector  变化检测        │
│                            │  consistency_checker 一致性检查   │
│                            │  feedback_service 反馈服务        │
│                            │  query_rewriter   查询改写        │
│                            │  context_detector 情境检测        │
│                            │  dynamic_context  动态上下文      │
│                            │  weather_service  天气服务        │
│                            │  search.py        联网搜索        │
│                            │  vector_store.py  向量存储        │
│                            │  portrait_skills/ 画像技能        │
│                            │  importer/        数据导入        │
│                            │  gbrain_*         知识图谱引擎    │
├──────────────────────────────────────────────────────────────┤
│  Models (20+)              │  Prompts (30+)                   │
│  ─────────────────        │  ─────────────────               │
│  chat.py      消息/会话    │  core_system.py   系统提示词      │
│  diary.py     日记        │  event_extraction 事件提取        │
│  timeline.py  时间线事件   │  profile_*        各类画像提示词   │
│  profile.py   画像        │  knowledge_*      知识编译提示词   │
│  knowledge.py 知识页面    │  signal_*         信号提取提示词   │
│  signal.py    信号        │  gbrain_*         知识图谱提示词   │
│  insight.py   洞察        │  diary_*          日记处理提示词   │
│  gbrain_*.py  知识图谱    │  ...                              │
│  quicknote.py 快速笔记    │                                   │
│  feedback.py  反馈        │                                   │
│  ...                      │                                   │
├──────────────────────────────────────────────────────────────┤
│  SQLite (主存储)              │  LanceDB (向量检索)            │
│  · 消息 / 会话 / 日记         │  · 画像向量                     │
│  · 时间线事件 / 实体          │  · 知识页面向量                  │
│  · 知识页面 / 关系 / 链接     │  · 时间线事件向量                │
│  · 画像记录 / 变化记录        │  · 实体向量                     │
├──────────────────────────────────────────────────────────────┤
│  外部服务                                                      │
│  · DeepSeek V4 (LLM 对话)                                      │
│  · 阿里云 DashScope (Embedding 向量化)                          │
│  · Tavily (联网搜索)                                           │
│  · 高德地图 (天气 / 位置)                                       │
│  · BGE-reranker-v2-m3 (本地重排序, 本地运行)                    │
└──────────────────────────────────────────────────────────────┘
```

### 记忆检索流程

```
用户消息
   │
   ├──→ 查询改写 (Query Rewriter) ──→ 优化后的查询
   │
   ├──→ RAG 检索 (向量相似度) ──────→ Top-K 相关记忆
   ├──→ 实体图搜索 (GBrain) ───────→ 直接+间接关联实体
   ├──→ 中期记忆 ───────────────────→ 近期会话摘要
   └──→ 画像快照 ───────────────────→ 长期人格 + 情境画像
                  │
                  ▼
            重排序融合 (BGE-reranker-v2-m3)
                  │
                  ▼
            上下文注入 ──→ LLM 生成回复
```

### 数据流：日记 → 知识图谱

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 日记创建  │───→│ 信号提取   │───→│ 页面创建   │───→│ 知识编译   │
│ (diary)  │    │ (signals) │    │ (pages)  │    │ (compiler)│
└─────────┘    └──────────┘    └──────────┘    └──────────┘
                     │                │               │
                     ▼                ▼               ▼
              ┌──────────┐    ┌──────────┐    ┌──────────┐
              │ 时间线事件  │    │ 关系提取   │    │ 知识图谱   │
              │ (timeline) │    │ (links)  │    │ (graph)  │
              └──────────┘    └──────────┘    └──────────┘
```

---

## 快速开始

### 环境要求

- Python 3.10+
- 内存：至少 4GB（本地重排序模型 BGE-reranker-v2-m3 需要）
- 磁盘：至少 2GB 可用空间

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-username/niannian.git
cd niannian

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 .\venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的 API Key
# 必填：DEEPSEEK_API_KEY、DASHSCOPE_API_KEY
# 可选：TAVILY_API_KEY（联网搜索）、AMAP_API_KEY（天气服务）
```

| 环境变量 | 说明 | 是否必填 | 获取地址 |
|---------|------|---------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek 对话模型 | 必填 | https://platform.deepseek.com/api_keys |
| `DASHSCOPE_API_KEY` | 阿里云 Embedding 模型 | 必填 | https://dashscope.aliyun.com/ |
| `TAVILY_API_KEY` | 联网搜索服务 | 可选 | https://tavily.com/ |
| `AMAP_API_KEY` | 高德地图（天气/位置） | 可选 | https://lbs.amap.com/ |

### 启动

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

访问 http://localhost:8000/docs 查看 Swagger API 文档。

---

## API 概览

### 对话 `/api/chat`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat/stream` | SSE 流式对话（核心接口） |
| `POST` | `/api/chat/sessions` | 创建新会话 |
| `GET` | `/api/chat/sessions` | 获取会话列表 |
| `GET` | `/api/chat/sessions/{id}` | 获取会话详情 |
| `GET` | `/api/chat/sessions/{id}/messages` | 获取会话消息 |
| `DELETE` | `/api/chat/sessions/{id}` | 删除会话 |

### 日记 `/api/diary`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/diary` | 创建日记（自动提取事件+信号） |
| `GET` | `/api/diary` | 查询日记列表 |
| `GET` | `/api/diary/{id}` | 获取日记详情 |
| `PUT` | `/api/diary/{id}` | 更新日记 |
| `DELETE` | `/api/diary/{id}` | 删除日记 |
| `GET` | `/api/diary/search` | 全文搜索日记 |
| `POST` | `/api/diary/{id}/reprocess` | 重新处理日记 |
| `GET` | `/api/diary/check-duplicate` | 检查重复日记 |

### 时间线 `/api/timeline`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/timeline/events` | 查询时间线事件（支持筛选） |
| `GET` | `/api/timeline/events/{id}` | 获取事件详情 |
| `PUT` | `/api/timeline/events/{id}` | 编辑事件 |
| `DELETE` | `/api/timeline/events/{id}` | 删除事件 |
| `POST` | `/api/timeline/events/{id}/confirm` | 确认事件 |
| `POST` | `/api/timeline/events/{id}/lock` | 锁定事件 |
| `GET` | `/api/timeline/stats` | 时间线统计 |

### 画像 `/api/profile`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/profile` | 获取当前画像 |
| `GET` | `/api/profile/versions` | 获取画像版本列表 |
| `GET` | `/api/profile/versions/{id}` | 获取指定版本画像 |
| `POST` | `/api/profile/generate` | 手动触发画像生成 |
| `POST` | `/api/profile/distill` | 人格蒸馏 |
| `GET` | `/api/profile/changes` | 获取画像变化记录 |
| `POST` | `/api/profile/changes/{id}/dismiss` | 关闭变化提醒 |
| `POST` | `/api/profile/feedback` | 提交画像反馈 |
| `GET` | `/api/profile/feedback` | 获取反馈列表 |

### 知识库 `/api/knowledge`

| 方法       | 路径                            | 说明       |
| -------- | ----------------------------- | -------- |
| `GET`    | `/api/knowledge/pages`        | 获取知识页面列表 |
| `POST`   | `/api/knowledge/pages`        | 创建知识页面   |
| `GET`    | `/api/knowledge/pages/{slug}` | 获取页面详情   |
| `PUT`    | `/api/knowledge/pages/{slug}` | 更新页面     |
| `DELETE` | `/api/knowledge/pages/{slug}` | 删除页面     |
| `POST`   | `/api/knowledge/pages/merge`  | 合并重复页面   |
| `GET`    | `/api/knowledge/search`       | 知识搜索     |
| `GET`    | `/api/knowledge/graph`        | 获取知识图谱   |
| `POST`   | `/api/knowledge/compile`      | 触发知识编译   |
| `GET`    | `/api/knowledge/export`       | 导出知识     |

### 数据导入 `/api/import`

| 方法       | 路径                              | 说明        |
| -------- | ------------------------------- | --------- |
| `GET`    | `/api/import/batches`           | 获取导入批次列表  |
| `DELETE` | `/api/import/batches/{id}`      | 删除导入批次    |
| `GET`    | `/api/import/privacy/{contact}` | 获取隐私设置    |
| `PUT`    | `/api/import/privacy/{contact}` | 更新隐私设置    |

### 洞察 `/api/insight`

| 方法    | 路径                               | 说明           |
| ----- | -------------------------------- | ------------ |
| `GET` | `/api/insight/emotion-season`    | 情绪季节（情绪时间序列） |


### 快速笔记 `/api/quicknote`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/quicknote` | 创建快速笔记 |
| `GET` | `/api/quicknote` | 查询快速笔记 |
| `PUT` | `/api/quicknote/{id}` | 更新快速笔记 |
| `DELETE` | `/api/quicknote/{id}` | 删除快速笔记 |
| `POST` | `/api/quicknote/consumption` | 创建消费记录 |

### 监控 `/api/monitor`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/monitor/status` | 系统状态概览 |
| `GET` | `/api/monitor/pending-events` | 待确认事件 |
| `POST` | `/api/monitor/retry-failed` | 重试失败日记 |

---

## 画像系统详解

念念的画像系统是核心差异化能力，采用**双轨制**架构：

### 细致型画像（Detailed Portrait）

```
数据源：L0 原始事件(30天) + L1 月度记忆(36月) + L2 年度记忆
降级策略：L1/L2 缺失时自动回退到读取更多原始事件
更新频率：每月
```

生成模块包括：日常习惯、社交模式、消费偏好、情绪状态、工作状态、健康状况等。

### 深度型画像（Deep Portrait）

```
数据源：L1 月度记忆(36月) + L2 年度记忆（不读原始事件）
降级策略：完全无记忆时回退到全部原始事件
更新频率：每月
```

抽象层级：

| 层级 | 名称 | 触发条件 | 置信度 |
|------|------|---------|--------|
| 1 | 具体习惯 | ≥3次，7天跨度 | frequent |
| 2 | 情境模式 | ≥5次，≥2个不同触发，30天跨度 | frequent |
| 3 | 人格特质 | ≥10次，≥3个不同模式，90天跨度 | implied |
| 4 | 价值观/动机 | 3个不同情境一致性，180天 | inferred |

深度型画像遵循严格的升级规则：
- 不可跳级抽象
- 每个模块必须包含反例（counter_examples）
- 避免标签化（不说「你是外向的人」，而是具体描述行为模式）
- 生成反思性问题而非断言

### 画像版本管理

所有画像生成后自动保存版本历史，支持：
- 版本对比（追踪人格变化）
- 版本回看（查看历史画像）
- 变化追踪（自动检测习惯消退、特质转变、偏好变化、决策模式形成）

---

## 项目结构

```
niannian/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口，注册路由 + 中间件
│   │   ├── config.py                # 配置管理（LLM、Embedding、数据库）
│   │   ├── database.py              # SQLite 初始化 + 连接管理
│   │   ├── models/                  # Pydantic 数据模型
│   │   │   ├── chat.py              # 消息、会话模型
│   │   │   ├── diary.py             # 日记模型
│   │   │   ├── timeline.py          # 时间线事件模型
│   │   │   ├── profile.py           # 画像记录模型
│   │   │   ├── knowledge.py         # 知识页面模型
│   │   │   ├── signal.py            # 信号模型
│   │   │   ├── insight.py           # 洞察数据模型
│   │   │   ├── gbrain_*.py          # 知识图谱数据模型
│   │   │   ├── quicknote.py         # 快速笔记模型
│   │   │   ├── feedback.py          # 反馈模型
│   │   │   └── ...
│   │   ├── routers/                 # API 路由层（9个路由模块）
│   │   │   ├── chat.py              # 对话接口
│   │   │   ├── diary.py             # 日记接口
│   │   │   ├── timeline.py          # 时间线接口
│   │   │   ├── profile.py           # 画像接口
│   │   │   ├── knowledge.py         # 知识库接口
│   │   │   ├── import_data.py       # 数据导入接口
│   │   │   ├── insight.py           # 洞察分析接口
│   │   │   ├── quicknote.py         # 快速笔记接口
│   │   │   └── monitor.py           # 监控接口
│   │   ├── services/                # 业务逻辑层（20+ 服务模块）
│   │   │   ├── chat.py              # 对话引擎（核心）
│   │   │   ├── diary.py             # 日记处理
│   │   │   ├── timeline.py          # 时间线引擎
│   │   │   ├── profile_builder.py   # 画像构建
│   │   │   ├── profile_manager.py   # 画像管理
│   │   │   ├── compiler.py          # 知识编译
│   │   │   ├── knowledge.py         # 知识管理
│   │   │   ├── rag.py               # RAG 检索
│   │   │   ├── graph_search.py      # 实体图搜索
│   │   │   ├── reranker.py          # 重排序
│   │   │   ├── memory.py            # 三层记忆管理
│   │   │   ├── snapshot.py          # 双层快照
│   │   │   ├── signals.py           # 信号提取
│   │   │   ├── signal_extractor.py  # 信号提取器
│   │   │   ├── change_detector.py   # 画像变化检测
│   │   │   ├── consistency_checker.py # 一致性检查
│   │   │   ├── feedback_service.py  # 反馈处理
│   │   │   ├── query_rewriter.py    # 查询改写
│   │   │   ├── context_detector.py  # 情境检测
│   │   │   ├── dynamic_context.py   # 动态上下文
│   │   │   ├── media_detector.py    # 媒体检测
│   │   │   ├── weather_service.py   # 天气服务
│   │   │   ├── search.py            # 联网搜索
│   │   │   ├── vector_store.py      # 向量存储
│   │   │   ├── portrait_skills/     # 画像技能
│   │   │   │   ├── coordinator.py   # 协调器
│   │   │   │   ├── detailed_skill.py # 细致型画像
│   │   │   │   └── deep_skill.py    # 深度型画像
│   │   │   ├── importer/            # 数据导入
│   │   │   │   ├── wechat.py        # 微信导入
│   │   │   │   ├── alipay.py        # 支付宝导入
│   │   │   │   ├── media.py         # 书影音导入
│   │   │   │   └── consumption_base.py # 消费导入基类
│   │   │   ├── gbrain_ingest.py     # 知识图谱摄取
│   │   │   ├── gbrain_page.py       # 知识图谱页面
│   │   │   ├── gbrain_search.py     # 知识图谱搜索
│   │   │   └── gbrain_lint.py       # 知识图谱检查
│   │   ├── prompts/                 # LLM 提示词（30+ 模板）
│   │   │   ├── core_system.py       # 核心系统提示词
│   │   │   ├── event_extraction.py  # 事件提取
│   │   │   ├── profile_*.py         # 各类画像生成提示词
│   │   │   ├── knowledge_*.py       # 知识编译提示词
│   │   │   ├── signal_*.py          # 信号提取提示词
│   │   │   ├── gbrain_*.py          # 知识图谱提示词
│   │   │   ├── diary_*.py           # 日记处理提示词
│   │   │   └── ...
│   │   └── utils/                   # 工具函数
│   │       ├── llm.py               # LLM 调用封装
│   │       ├── embedding.py         # Embedding 调用封装
│   │       ├── token_counter.py     # Token 计数器
│   │       └── text_processing.py   # 文本处理
│   └── scripts/                     # 辅助脚本
│       ├── seed_diaries.py          # 种子日记数据
│       ├── seed_diaries_v2.py       # 种子日记 v2
│       ├── migrate_knowledge.py     # 知识迁移
│       └── check_data.py            # 数据检查
├── tests/                           # 测试
├── .env.example                     # 环境变量模板
├── .gitignore
└── README.md
```

---

## 常见问题

**Q: 念念与 ChatGPT/Claude 的记忆功能有什么区别？**

A: ChatGPT 的「记忆」是简单的 Key-Value 存储（如「用户喜欢喝咖啡」），念念的记忆是**三层渐进式架构**——它会从你的日记中自动提取实体、关系、习惯、情绪模式，构建知识图谱和人格画像，实现真正的「理解」而非「记住」。

**Q: 数据存储在哪里？安全吗？**

A: 所有数据存储在本地 SQLite 数据库和 LanceDB 向量库中，不会上传到任何云端。

**Q: 需要多少数据才能开始使用？**

A: 写一篇日记就可以开始体验。念念会从第一篇日记开始提取事件、构建知识。当然，数据越多，画像越精准。

**Q: 支持哪些 LLM？**

A: 目前使用 DeepSeek V4 作为对话模型，阿里云 DashScope 作为 Embedding 模型。可以通过修改 `config.py` 和 `.env` 切换其他兼容 OpenAI API 的模型。

---

## 贡献指南

欢迎贡献！请遵循以下流程：

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'feat: add amazing feature'`
4. 推送到分支：`git push origin feature/amazing-feature`
5. 提交 Pull Request

### 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

- `feat:` 新功能
- `fix:` 修复 Bug
- `refactor:` 重构
- `docs:` 文档更新
- `test:` 测试相关
- `chore:` 构建/工具变更

---

## 许可证

MIT License

---

<p align="center">
  <b>念念不忘，必有回响。</b>
</p>