# NianNian (念念)

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.110+-green" alt="FastAPI">
  <img src="https://img.shields.io/badge/license-MIT-purple" alt="License">
  <img src="https://img.shields.io/badge/LLM-DeepSeek%20V4-orange" alt="LLM">
  <img src="https://img.shields.io/badge/Embedding-DashScope-blue" alt="Embedding">
</p>

<p align="center">
  <b>Your Personal Digital Twin — an AI that truly remembers and understands you.</b>
</p>

---

## What is NianNian?

NianNian is a **Personal Digital Twin Agent** — an LLM-powered memory and conversation system that builds a deep understanding of who you are. It ingests your diaries to construct a persistent personality profile, knowledge graph, and long-term memory, enabling an AI that genuinely "knows" you.

Unlike general-purpose AI assistants that treat every conversation as a blank slate, NianNian **gets better the more you use it** — it remembers your habits, preferences, relationships, emotional patterns, and even surfaces changes you might not notice yourself.

### In a Nutshell

> NianNian = Diary Analysis + Memory Engine + Knowledge Graph + Personality Portrait + Personalized Conversation

---

## Core Features

### Deep Memory System

NianNian's memory is not a simple chat log — it's a **progressive memory engine** that transforms raw data into knowledge and personality.

```
┌─────────────────────────────────────────────────────────────┐
│                 Three-Tier Memory Architecture               │
├─────────────────────────────────────────────────────────────┤
│  L0 Short-Term (40 messages)                                 │
│  · Current session context for coherent conversation         │
│  · Sliding window, auto-managed, no manual cleanup           │
├─────────────────────────────────────────────────────────────┤
│  L1 Mid-Term (5 session summaries)                           │
│  · Compressed recap of recent conversations                 │
│  · Dimensions: topics, key info, emotional tone              │
├─────────────────────────────────────────────────────────────┤
│  L2 Long-Term (Knowledge Graph + Personality Portrait)       │
│  · Permanent personal archive, never lost                    │
│  · Contains: entities, relationships, habits, preferences,   │
│    emotional patterns, value signals                         │
│  · Auto-compiled, deduplicated, consistency-checked          │
└─────────────────────────────────────────────────────────────┘
```

**Dual-Layer Snapshot Architecture**: Leveraging LLM KV Cache mechanism, frequently used memories are split into a frozen core layer and a cached context layer, significantly reducing token overhead and inference latency per conversation round.

**Profile Change Detection**: Automatically monitors four types of changes:
- Habit Fading (auto-tagged after 90 days without new evidence)
- Trait Shifts (triggered when new signals contradict old profiles)
- Preference Changes (old vs. new comparison in interest/taste dimensions)
- Decision Pattern Formation (first-time generation of decision sub-profile)

### Personalized Conversation

The conversation engine doesn't just answer questions — it interacts with you **based on your complete personality profile**:

- **Context Detection**: Auto-detects conversation context (family/work/social/decision-making/media), adapting response style
- **Intent Recognition**: Distinguishes "sharing" vs. "analyzing" to match response strategies
- **Knowledge Injection**: Retrieves relevant entities, diary entries, and timeline events during conversation, re-ranks them, and injects into context
- **Tool Calling**: Supports web search (Tavily), weather queries (Amap), time awareness
- **Profile Change Alerts**: Proactively surfaces behavioral pattern changes (e.g., "Your running frequency has dropped 40% this month")

### Knowledge Graph

NianNian automatically extracts and builds a knowledge graph from your data:

```
Diary Content ──→ Signal Extraction ──→ Page Creation ──→ Compilation ──→ Knowledge Graph
                     │                      │                    │
                     ▼                      ▼                    ▼
              Entity Recognition    Relationship Extraction   Consistency Check
              Sentiment Labeling    Link Construction         Merge Detection
              Timeline Events      Categorization            Conflict Resolution
```

Supported entity types: people, places, habits, emotional patterns, value signals, decision patterns, preferences, roles, achievements, and more.

### Data Import

NianNian ingests data through diaries. Each diary entry automatically extracts events, signals, and knowledge to build your memory:

| Source | Method | Extracted Content |
|--------|--------|-------------------|
| Diary | Manual entry / Structured import | Timeline events, entities, signals, emotional patterns, knowledge pages |

### Dashboard Visualizations

Emotion visualization API endpoint:

- **Emotion Season**: Time-series analysis of emotional changes

---

## Technical Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         FastAPI                               │
│                   (REST API + SSE Streaming)                  │
├──────────────────────────────────────────────────────────────┤
│  Routers (9)              │  Services (20+)                  │
│  ─────────────────        │  ─────────────────               │
│  /chat      Chat API      │  chat.py          Chat Engine     │
│  /diary     Diary API     │  diary.py         Diary Processing│
│  /timeline  Timeline API  │  timeline.py      Timeline Engine │
│  /profile   Profile API   │  profile_builder  Portrait Builder│
│  /knowledge Knowledge API │  profile_manager  Portrait Manager│
│  /import    Import API    │  compiler.py      Knowledge Compile│
│  /insight   Insight API   │  knowledge.py     Knowledge Mgmt  │
│  /quicknote QuickNote API │  rag.py           RAG Retrieval   │
│  /monitor   Monitor API   │  graph_search.py  Entity Graph    │
│                            │  reranker.py      Re-ranker       │
│                            │  memory.py        Memory Manager  │
│                            │  snapshot.py      Snapshot Service│
│                            │  signals.py       Signal Extraction│
│                            │  signal_extractor Signal Extractor│
│                            │  change_detector  Change Detector │
│                            │  consistency_checker Consistency  │
│                            │  feedback_service Feedback Service│
│                            │  query_rewriter   Query Rewriter  │
│                            │  context_detector Context Detector│
│                            │  dynamic_context  Dynamic Context │
│                            │  weather_service  Weather Service │
│                            │  search.py        Web Search      │
│                            │  vector_store.py  Vector Store    │
│                            │  portrait_skills/ Portrait Skills │
│                            │  importer/        Data Importers  │
│                            │  gbrain_*         Knowledge Engine│
├──────────────────────────────────────────────────────────────┤
│  Models (20+)              │  Prompts (30+)                   │
│  ─────────────────        │  ─────────────────               │
│  chat.py      Messages    │  core_system.py   System Prompt   │
│  diary.py     Diaries     │  event_extraction Event Extraction│
│  timeline.py  Events      │  profile_*        Portrait Prompts│
│  profile.py   Portraits   │  knowledge_*      Compile Prompts │
│  knowledge.py Pages       │  signal_*         Signal Prompts  │
│  signal.py    Signals     │  gbrain_*         Graph Prompts   │
│  insight.py   Insights    │  diary_*          Diary Prompts   │
│  gbrain_*.py  Graph       │  ...                              │
│  quicknote.py QuickNotes  │                                   │
│  feedback.py  Feedback    │                                   │
│  ...                      │                                   │
├──────────────────────────────────────────────────────────────┤
│  SQLite (Primary Storage)     │  LanceDB (Vector Search)      │
│  · Messages / Sessions        │  · Portrait vectors            │
│  · Diaries / Timeline Events  │  · Knowledge page vectors      │
│  · Knowledge Pages / Links    │  · Timeline event vectors      │
│  · Portrait Records / Changes │  · Entity vectors              │
├──────────────────────────────────────────────────────────────┤
│  External Services                                             │
│  · DeepSeek V4 (LLM)                                          │
│  · Alibaba DashScope (Embedding)                              │
│  · Tavily (Web Search)                                        │
│  · Amap (Weather / Location)                                  │
│  · BGE-reranker-v2-m3 (Local Re-ranker, runs locally)        │
└──────────────────────────────────────────────────────────────┘
```

### Memory Retrieval Pipeline

```
User Message
   │
   ├──→ Query Rewriter ──→ Optimized Query
   │
   ├──→ RAG Retrieval (vector similarity) ──→ Top-K relevant memories
   ├──→ Entity Graph Search (GBrain) ───────→ Direct + indirect related entities
   ├──→ Mid-Term Memory ────────────────────→ Recent session summaries
   └──→ Portrait Snapshot ──────────────────→ Long-term + contextual portraits
                  │
                  ▼
             Re-Ranking (BGE-reranker-v2-m3)
                  │
                  ▼
             Context Injection ──→ LLM Response Generation
```

### Data Flow: Diary → Knowledge Graph

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Diary    │───→│ Signals  │───→│ Pages    │───→│ Compiler │
│ Created  │    │ Extracted│    │ Created  │    │ Runs     │
└─────────┘    └──────────┘    └──────────┘    └──────────┘
                     │                │               │
                     ▼                ▼               ▼
              ┌──────────┐    ┌──────────┐    ┌──────────┐
              │ Timeline │    │ Relations│    │ Knowledge│
              │ Events   │    │ Extracted│    │ Graph    │
              └──────────┘    └──────────┘    └──────────┘
```

---

## Quick Start

### Requirements

- Python 3.10+
- Memory: 4GB+ (local re-ranker BGE-reranker-v2-m3)
- Disk: 2GB+ free space

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/niannian.git
cd niannian

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or .\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your API keys
# Required: DEEPSEEK_API_KEY, DASHSCOPE_API_KEY
# Optional: TAVILY_API_KEY (web search), AMAP_API_KEY (weather)
```

| Variable | Description | Required | Get From |
|----------|-------------|----------|----------|
| `DEEPSEEK_API_KEY` | DeepSeek LLM API key | Yes | https://platform.deepseek.com/api_keys |
| `DASHSCOPE_API_KEY` | Alibaba Embedding API key | Yes | https://dashscope.aliyun.com/ |
| `TAVILY_API_KEY` | Web search service | No | https://tavily.com/ |
| `AMAP_API_KEY` | Amap (weather/location) | No | https://lbs.amap.com/ |

### Run

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for the Swagger API documentation.

---

## API Overview

### Chat `/api/chat`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat/stream` | SSE streaming chat (core endpoint) |
| `POST` | `/api/chat/sessions` | Create new session |
| `GET` | `/api/chat/sessions` | List sessions |
| `GET` | `/api/chat/sessions/{id}` | Get session details |
| `GET` | `/api/chat/sessions/{id}/messages` | Get session messages |
| `DELETE` | `/api/chat/sessions/{id}` | Delete session |

### Diary `/api/diary`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/diary` | Create diary (auto-extracts events + signals) |
| `GET` | `/api/diary` | List diaries |
| `GET` | `/api/diary/{id}` | Get diary details |
| `PUT` | `/api/diary/{id}` | Update diary |
| `DELETE` | `/api/diary/{id}` | Delete diary |
| `GET` | `/api/diary/search` | Full-text search |
| `POST` | `/api/diary/{id}/reprocess` | Reprocess diary |
| `GET` | `/api/diary/check-duplicate` | Check for duplicates |

### Timeline `/api/timeline`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/timeline/events` | Query events (with filters) |
| `GET` | `/api/timeline/events/{id}` | Get event details |
| `PUT` | `/api/timeline/events/{id}` | Edit event |
| `DELETE` | `/api/timeline/events/{id}` | Delete event |
| `POST` | `/api/timeline/events/{id}/confirm` | Confirm event |
| `POST` | `/api/timeline/events/{id}/lock` | Lock event |
| `GET` | `/api/timeline/stats` | Timeline statistics |

### Profile `/api/profile`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/profile` | Get current portrait |
| `GET` | `/api/profile/versions` | List portrait versions |
| `GET` | `/api/profile/versions/{id}` | Get specific version |
| `POST` | `/api/profile/generate` | Trigger portrait generation |
| `POST` | `/api/profile/distill` | Personality distillation |
| `GET` | `/api/profile/changes` | Get change records |
| `POST` | `/api/profile/changes/{id}/dismiss` | Dismiss change alert |
| `POST` | `/api/profile/feedback` | Submit feedback |
| `GET` | `/api/profile/feedback` | List feedback |

### Knowledge `/api/knowledge`

| Method   | Path                            | Description          |
| -------- | ------------------------------- | -------------------- |
| `GET`    | `/api/knowledge/pages`          | List knowledge pages |
| `POST`   | `/api/knowledge/pages`          | Create knowledge page |
| `GET`    | `/api/knowledge/pages/{slug}`   | Get page details     |
| `PUT`    | `/api/knowledge/pages/{slug}`   | Update page          |
| `DELETE` | `/api/knowledge/pages/{slug}`   | Delete page          |
| `POST`   | `/api/knowledge/pages/merge`    | Merge duplicate pages |
| `GET`    | `/api/knowledge/search`         | Knowledge search     |
| `GET`    | `/api/knowledge/graph`          | Get knowledge graph  |
| `POST`   | `/api/knowledge/compile`        | Trigger compilation  |
| `GET`    | `/api/knowledge/export`         | Export knowledge     |

### Import `/api/import`

| Method   | Path                              | Description            |
| -------- | --------------------------------- | ---------------------- |
| `GET`    | `/api/import/batches`             | List import batches    |
| `DELETE` | `/api/import/batches/{id}`        | Delete import batch    |
| `GET`    | `/api/import/privacy/{contact}`   | Get privacy settings   |
| `PUT`    | `/api/import/privacy/{contact}`   | Update privacy settings|

### Insight `/api/insight`

| Method | Path                            | Description                        |
| ------ | ------------------------------- | ---------------------------------- |
| `GET`  | `/api/insight/emotion-season`   | Emotion Season time series analysis |

### Quick Note `/api/quicknote`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/quicknote` | Create quick note |
| `GET` | `/api/quicknote` | Query quick notes |
| `PUT` | `/api/quicknote/{id}` | Update quick note |
| `DELETE` | `/api/quicknote/{id}` | Delete quick note |
| `POST` | `/api/quicknote/consumption` | Create consumption record |

### Monitor `/api/monitor`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/monitor/status` | System status overview |
| `GET` | `/api/monitor/pending-events` | Pending confirmation events |
| `POST` | `/api/monitor/retry-failed` | Retry failed diaries |

---

## Portrait System Deep Dive

NianNian's portrait system is the core differentiator, using a **dual-track** architecture:

### Detailed Portrait

```
Data Source: L0 raw events (30 days) + L1 monthly memories (36 months) + L2 yearly memories
Fallback: When L1/L2 are missing, auto-falls back to reading more raw events
Update Frequency: Monthly
```

Generated modules: daily habits, social patterns, consumption preferences, emotional state, work status, health status, etc.

### Deep Portrait

```
Data Source: L1 monthly memories (36 months) + L2 yearly memories (no raw events)
Fallback: When no memories exist, falls back to all raw events
Update Frequency: Monthly
```

Abstraction levels with strict upgrade rules:

| Level | Name | Trigger Condition | Confidence |
|-------|------|-------------------|------------|
| 1 | Concrete Habit | ≥3 occurrences, 7-day span | frequent |
| 2 | Situational Pattern | ≥5 occurrences, ≥2 different triggers, 30-day span | frequent |
| 3 | Personality Trait | ≥10 occurrences, ≥3 different patterns, 90-day span | implied |
| 4 | Values / Motivation | 3 different situational consistencies, 180 days | inferred |

Deep Portrait enforces strict rules:
- No skipping abstraction levels
- Every module must include counter-examples
- Avoids labeling (never says "you are an extrovert" — instead describes specific behavioral patterns)
- Generates reflection questions rather than assertions

### Portrait Version Management

All portraits are auto-saved with version history, supporting:
- Version comparison (track personality changes over time)
- Version review (view historical portraits)
- Change tracking (auto-detect habit fading, trait shifts, preference changes, decision pattern formation)

---

## Project Structure

```
niannian/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entry point, registers routers + middleware
│   │   ├── config.py                # Configuration (LLM, Embedding, Database)
│   │   ├── database.py              # SQLite init + connection management
│   │   ├── models/                  # Pydantic data models
│   │   │   ├── chat.py              # Message, session models
│   │   │   ├── diary.py             # Diary models
│   │   │   ├── timeline.py          # Timeline event models
│   │   │   ├── profile.py           # Portrait record models
│   │   │   ├── knowledge.py         # Knowledge page models
│   │   │   ├── signal.py            # Signal models
│   │   │   ├── insight.py           # Insight data models
│   │   │   ├── gbrain_*.py          # Knowledge graph models
│   │   │   ├── quicknote.py         # Quick note models
│   │   │   ├── feedback.py          # Feedback models
│   │   │   └── ...
│   │   ├── routers/                 # API route layer (9 router modules)
│   │   │   ├── chat.py              # Chat endpoints
│   │   │   ├── diary.py             # Diary endpoints
│   │   │   ├── timeline.py          # Timeline endpoints
│   │   │   ├── profile.py           # Profile endpoints
│   │   │   ├── knowledge.py         # Knowledge endpoints
│   │   │   ├── import_data.py       # Import endpoints
│   │   │   ├── insight.py           # Insight endpoints
│   │   │   ├── quicknote.py         # Quick note endpoints
│   │   │   └── monitor.py           # Monitor endpoints
│   │   ├── services/                # Business logic layer (20+ service modules)
│   │   │   ├── chat.py              # Chat engine (core)
│   │   │   ├── diary.py             # Diary processing
│   │   │   ├── timeline.py          # Timeline engine
│   │   │   ├── profile_builder.py   # Portrait builder
│   │   │   ├── profile_manager.py   # Portrait manager
│   │   │   ├── compiler.py          # Knowledge compiler
│   │   │   ├── knowledge.py         # Knowledge management
│   │   │   ├── rag.py               # RAG retrieval
│   │   │   ├── graph_search.py      # Entity graph search
│   │   │   ├── reranker.py          # Re-ranker
│   │   │   ├── memory.py            # Three-tier memory manager
│   │   │   ├── snapshot.py          # Dual-layer snapshot
│   │   │   ├── signals.py           # Signal extraction
│   │   │   ├── signal_extractor.py  # Signal extractor
│   │   │   ├── change_detector.py   # Profile change detection
│   │   │   ├── consistency_checker.py # Consistency checker
│   │   │   ├── feedback_service.py  # Feedback processing
│   │   │   ├── query_rewriter.py    # Query rewriter
│   │   │   ├── context_detector.py  # Context detector
│   │   │   ├── dynamic_context.py   # Dynamic context
│   │   │   ├── media_detector.py    # Media detector
│   │   │   ├── weather_service.py   # Weather service
│   │   │   ├── search.py            # Web search
│   │   │   ├── vector_store.py      # Vector store
│   │   │   ├── portrait_skills/     # Portrait skills
│   │   │   │   ├── coordinator.py   # Coordinator
│   │   │   │   ├── detailed_skill.py # Detailed portrait
│   │   │   │   └── deep_skill.py    # Deep portrait
│   │   │   ├── importer/            # Data importers
│   │   │   │   ├── wechat.py        # WeChat importer
│   │   │   │   ├── alipay.py        # Alipay importer
│   │   │   │   ├── media.py         # Media importer
│   │   │   │   └── consumption_base.py # Consumption base
│   │   │   ├── gbrain_ingest.py     # Knowledge graph ingest
│   │   │   ├── gbrain_page.py       # Knowledge graph page
│   │   │   ├── gbrain_search.py     # Knowledge graph search
│   │   │   └── gbrain_lint.py       # Knowledge graph lint
│   │   ├── prompts/                 # LLM prompts (30+ templates)
│   │   │   ├── core_system.py       # Core system prompt
│   │   │   ├── event_extraction.py  # Event extraction
│   │   │   ├── profile_*.py         # Portrait generation prompts
│   │   │   ├── knowledge_*.py       # Knowledge compilation prompts
│   │   │   ├── signal_*.py          # Signal extraction prompts
│   │   │   ├── gbrain_*.py          # Knowledge graph prompts
│   │   │   ├── diary_*.py           # Diary processing prompts
│   │   │   └── ...
│   │   └── utils/                   # Utility functions
│   │       ├── llm.py               # LLM call wrapper
│   │       ├── embedding.py         # Embedding call wrapper
│   │       ├── token_counter.py     # Token counter
│   │       └── text_processing.py   # Text processing
│   └── scripts/                     # Helper scripts
│       ├── seed_diaries.py          # Seed diary data
│       ├── seed_diaries_v2.py       # Seed diary v2
│       ├── migrate_knowledge.py     # Knowledge migration
│       └── check_data.py            # Data checker
├── tests/                           # Tests
├── .env.example                     # Environment template
├── .gitignore
└── README.md
```

---

## FAQ

**Q: How is NianNian different from ChatGPT/Claude's memory features?**

A: ChatGPT's "memory" is simple key-value storage (e.g., "user likes coffee"). NianNian's memory is a **three-tier progressive architecture** — it automatically extracts entities, relationships, habits, and emotional patterns from your diaries, building a knowledge graph and personality portrait. It's the difference between "remembering" and "understanding."

**Q: Where is my data stored? Is it secure?**

A: All data is stored locally in SQLite databases and LanceDB vector stores — nothing is uploaded to any cloud.

**Q: How much data do I need to start?**

A: Just one diary entry is enough to begin. NianNian starts extracting events and building knowledge from your first entry. Of course, more data means more accurate portraits.

**Q: Which LLMs are supported?**

A: Currently uses DeepSeek V4 for conversation and Alibaba DashScope for embeddings. You can switch to other OpenAI-compatible models by modifying `config.py` and `.env`.

---

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'feat: add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

### Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `refactor:` Code refactoring
- `docs:` Documentation updates
- `test:` Test related
- `chore:` Build/tooling changes

---

## License

MIT License

---

<p align="center">
  <b>念念不忘，必有回响。 — What is remembered, lives.</b>
</p>