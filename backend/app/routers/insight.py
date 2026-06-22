from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from app.database import get_connection

router = APIRouter(prefix="/api/insight", tags=["insight"])


# ---------- 生命河流 ----------

@router.get("/life-river")
async def api_life_river(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
):
    """时间线事件流数据，用于桑基/河流图"""
    async with get_connection() as db:
        query = """
            SELECT id, timestamp, event_type, summary, importance_score, sentiment, is_milestone
            FROM timeline_events
            WHERE 1=1
        """
        params: list = []
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        nodes = []
        for row in rows:
            nodes.append({
                "id": row["id"],
                "date": row["timestamp"][:10] if row["timestamp"] else "",
                "event_type": row["event_type"] or "routine",
                "summary": row["summary"] or "",
                "importance_score": row["importance_score"] or 0,
                "sentiment": row["sentiment"],
                "is_milestone": bool(row["is_milestone"]),
            })

        # Build links: consecutive events of same type
        links = []
        type_last: dict[str, str] = {}
        for node in reversed(nodes):  # chronological
            et = node["event_type"]
            if et in type_last:
                links.append({
                    "source": type_last[et],
                    "target": node["id"],
                    "value": 1,
                })
            type_last[et] = node["id"]

    return {"nodes": nodes, "links": links}


# ---------- 关系星云 ----------

@router.get("/relation-nebula")
async def api_relation_nebula(
    depth: int = Query(default=1, ge=1, le=3),
    center_slug: Optional[str] = Query(default=None),
):
    """关系网络数据，用于力导向图"""
    async with get_connection() as db:
        nodes = []
        links = []

        # Knowledge pages nodes
        cursor = await db.execute(
            "SELECT slug, title, type FROM pages WHERE type IN ('person', 'self', 'company', 'project', 'concept')"
        )
        page_rows = await cursor.fetchall()
        page_slugs = {r["slug"] for r in page_rows}
        for r in page_rows:
            type_map = {"person": 1, "self": 2, "company": 3, "project": 4, "concept": 5}
            nodes.append({
                "id": r["slug"],
                "name": r["title"],
                "type": r["type"],
                "group": type_map.get(r["type"], 0),
            })

        # Knowledge links
        if page_slugs:
            placeholders = ",".join("?" for _ in page_slugs)
            cursor = await db.execute(
                f"""SELECT l.source_page_id, l.target_page_id, l.link_type, l.confidence,
                            sp.slug as source_slug, tp.slug as target_slug
                     FROM links l
                     JOIN pages sp ON l.source_page_id = sp.id
                     JOIN pages tp ON l.target_page_id = tp.id
                     WHERE sp.slug IN ({placeholders}) AND tp.slug IN ({placeholders})""",
                list(page_slugs) + list(page_slugs),
            )
            for lr in await cursor.fetchall():
                links.append({
                    "source": lr["source_slug"],
                    "target": lr["target_slug"],
                    "relation_type": lr["link_type"] or "关联",
                    "confidence": lr["confidence"] or "implied",
                })

    return {"nodes": nodes, "links": links}


# ---------- 习惯潮汐 ----------

@router.get("/habit-tide")
async def api_habit_tide():
    """习惯频次周期数据"""
    async with get_connection() as db:
        cursor = await db.execute(
            """SELECT slug, title, frontmatter, created_at FROM pages WHERE type = 'habit'"""
        )
        habit_rows = await cursor.fetchall()

        habits = []
        import json
        for r in habit_rows:
            fm = r["frontmatter"] or {}
            if isinstance(fm, str):
                try:
                    fm = json.loads(fm)
                except Exception:
                    fm = {}

            freq = fm.get("frequency_30d")
            freq_val = int(freq) if freq is not None else 0
            created = r["created_at"][:10] if r["created_at"] else ""

            habits.append({
                "habit_name": r["title"],
                "habit_type": fm.get("habit_type") or "其他",
                "frequency_30d": freq_val,
                "confidence": fm.get("confidence") or "inferred",
                "first_seen": fm.get("first_seen") or created,
                "last_seen": fm.get("last_seen") or "",
                "daily_distribution": {},
            })

        cursor = await db.execute(
            """SELECT timestamp, summary, event_type FROM timeline_events
               WHERE event_type = 'routine' OR event_type = 'health'
               ORDER BY timestamp DESC LIMIT 100"""
        )
        tl_rows = await cursor.fetchall()

    return {
        "habits": habits,
        "period_start": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        "period_end": datetime.now().strftime("%Y-%m-%d"),
        "timeline_routines": [
            {"date": r["timestamp"][:10] if r["timestamp"] else "", "summary": r["summary"], "type": r["event_type"]}
            for r in tl_rows
        ],
    }


# ---------- 情绪季节 ----------

@router.get("/emotion-season")
async def api_emotion_season(
    year: Optional[int] = Query(default=None),
    month: Optional[int] = Query(default=None),
):
    """情感日历与维度数据。返回 available_years 供前端选择年份。
    当请求年份无数据时，自动回退到最近有数据的年份。
    """
    async with get_connection() as db:
        # 查询所有有情绪数据的年份
        cursor = await db.execute(
            """SELECT DISTINCT SUBSTR(timestamp, 1, 4) as yr
               FROM timeline_events
               WHERE sentiment IS NOT NULL
               ORDER BY yr DESC"""
        )
        year_rows = await cursor.fetchall()
        available_years = [int(r["yr"]) for r in year_rows]

        # 如果没有指定年份，或指定年份无数据，回退到最近有数据的年份
        if year is None:
            if available_years:
                year = available_years[0]
            else:
                year = datetime.now().year
        elif year not in available_years and available_years:
            year = available_years[0]

        start_str = f"{year}-01-01"
        end_str = f"{year}-12-31"
        if month:
            start_str = f"{year}-{month:02d}-01"
            if month == 12:
                end_str = f"{year}-12-31"
            else:
                end_str = f"{year}-{month + 1:02d}-01"

        cursor = await db.execute(
            """SELECT SUBSTR(timestamp, 1, 10) as date,
                      AVG(sentiment) as avg_sentiment,
                      COUNT(*) as count
               FROM timeline_events
               WHERE sentiment IS NOT NULL
                 AND timestamp >= ? AND timestamp <= ?
               GROUP BY SUBSTR(timestamp, 1, 10)
               ORDER BY date""",
            (start_str, end_str),
        )
        daily_rows = await cursor.fetchall()

        daily = [
            {
                "date": r["date"],
                "avg_sentiment": round(r["avg_sentiment"] or 0, 3),
                "count": r["count"],
            }
            for r in daily_rows
        ]

        cursor = await db.execute(
            """SELECT SUBSTR(timestamp, 1, 7) as month,
                      AVG(sentiment) as avg_sentiment
               FROM timeline_events
               WHERE sentiment IS NOT NULL AND timestamp LIKE ?
               GROUP BY SUBSTR(timestamp, 1, 7)
               ORDER BY month""",
            (f"{year}-%",),
        )
        monthly_rows = await cursor.fetchall()
        monthly_avg = {r["month"]: round(r["avg_sentiment"] or 0, 3) for r in monthly_rows}

    return {"daily": daily, "monthly_avg": monthly_avg, "year": year, "available_years": available_years}


# ---------- 工作流 ----------

# 日记处理流水线的7个步骤（与 process_diary_async 一一对应）
PIPELINE_STEPS = [
    {"key": "ingest",      "label": "日记录入",   "desc": "日记内容写入数据库"},
    {"key": "summary",     "label": "摘要提取",   "desc": "LLM 生成摘要与标签"},
    {"key": "signal",      "label": "信号提取",   "desc": "提取行为/情绪/价值观信号"},
    {"key": "timeline",    "label": "时间线提取", "desc": "从内容中提取时间线事件"},
    {"key": "profile",     "label": "画像更新",   "desc": "信号驱动画像片段更新"},
    {"key": "relation",    "label": "关系提取",   "desc": "提取实体间关系"},
    {"key": "knowledge",   "label": "知识入库",   "desc": "实体写入知识图谱"},
]


def _infer_step_progress(diary_row: dict, has_signals: bool, has_events: bool,
                          has_profiles: bool, has_relations: bool, has_knowledge: bool) -> dict:
    """根据已有数据推断每篇日记走到了流水线的哪一步。"""
    steps = {}
    # Step 1: 日记录入 — 日记存在即完成
    steps["ingest"] = "completed"
    # Step 2: 摘要提取 — extracted_summary 非空
    steps["summary"] = "completed" if diary_row.get("extracted_summary") else "pending"
    # Step 3: 信号提取 — raw_signals 中有该日记的记录
    steps["signal"] = "completed" if has_signals else "pending"
    # Step 4: 时间线提取 — timeline_events 中有该日记的记录
    steps["timeline"] = "completed" if has_events else "pending"
    # Step 5: 画像更新 — 有信号则画像步骤也算完成（画像依赖信号）
    steps["profile"] = "completed" if has_profiles else "pending"
    # Step 6: 关系提取
    steps["relation"] = "completed" if has_relations else "pending"
    # Step 7: 知识入库
    steps["knowledge"] = "completed" if has_knowledge else "pending"

    # 如果整体状态是 processing，找到第一个 pending 步骤标记为 active
    if diary_row.get("processing_status") == "processing":
        for s in PIPELINE_STEPS:
            if steps[s["key"]] == "pending":
                steps[s["key"]] = "active"
                break
    # 如果整体状态是 failed，找到第一个 pending 步骤标记为 failed
    elif diary_row.get("processing_status") == "failed":
        for s in PIPELINE_STEPS:
            if steps[s["key"]] == "pending":
                steps[s["key"]] = "failed"
                break

    # 计算当前步骤索引
    current_step = 0
    for i, s in enumerate(PIPELINE_STEPS):
        if steps[s["key"]] == "completed":
            current_step = i + 1
        elif steps[s["key"]] in ("active", "failed"):
            current_step = i
            break

    return {"steps": steps, "current_step": current_step, "total_steps": len(PIPELINE_STEPS)}


@router.get("/workflow")
async def api_workflow():
    """日记处理工作流：流水线步骤进度 + 各步骤最近输出"""
    import json as _json

    async with get_connection() as db:
        # 最近5篇日记
        cursor = await db.execute(
            """SELECT id, date, content, extracted_summary, extracted_tags, processing_status, created_at
               FROM diaries ORDER BY created_at DESC LIMIT 5"""
        )
        diary_rows = await cursor.fetchall()

        diaries = []
        for r in diary_rows:
            diary_id = r["id"]
            # 检查该日记在各步骤是否有产出
            cur = await db.execute(
                "SELECT COUNT(*) as cnt FROM raw_signals WHERE source_id = ?", (diary_id,)
            )
            has_signals = (await cur.fetchone())["cnt"] > 0

            cur = await db.execute(
                "SELECT COUNT(*) as cnt FROM timeline_events WHERE source_id = ?", (diary_id,)
            )
            has_events = (await cur.fetchone())["cnt"] > 0

            has_profiles = has_signals  # 画像依赖信号，简化判断

            cur = await db.execute("SELECT COUNT(*) as cnt FROM links")
            rel_row = await cur.fetchone()
            has_relations = rel_row["cnt"] > 0 if rel_row else False

            cur = await db.execute(
                "SELECT COUNT(*) as cnt FROM pages WHERE type != 'system'"
            )
            kb_row = await cur.fetchone()
            has_knowledge = kb_row["cnt"] > 0 if kb_row else False

            progress = _infer_step_progress(dict(r), has_signals, has_events, has_profiles, has_relations, has_knowledge)

            diaries.append({
                "id": diary_id,
                "date": r["date"],
                "content_preview": (r["content"] or "")[:150] + ("..." if len(r["content"] or "") > 150 else ""),
                "summary": r["extracted_summary"] or "",
                "tags": r["extracted_tags"] or "",
                "status": r["processing_status"] or "pending",
                "progress": progress,
                "created_at": r["created_at"],
            })

        # 各步骤最近产出（用于点击步骤时展示详情）
        # 摘要
        summaries = [
            {"diary_date": r["date"], "summary": r["extracted_summary"] or "", "tags": r["extracted_tags"] or ""}
            for r in diary_rows if r["extracted_summary"]
        ][:5]

        # 信号
        cursor = await db.execute(
            """SELECT id, signal_json, entity_tags, source_type, source_id, status, created_at
               FROM raw_signals ORDER BY created_at DESC LIMIT 15"""
        )
        signal_rows = await cursor.fetchall()
        signals = []
        for r in signal_rows:
            sig_data = {}
            try:
                sig_data = _json.loads(r["signal_json"]) if r["signal_json"] else {}
            except (_json.JSONDecodeError, TypeError):
                pass
            signals.append({
                "id": r["id"],
                "type": sig_data.get("type", ""),
                "sub_type": sig_data.get("sub_type", ""),
                "content": sig_data.get("content", "")[:200],
                "entity_tags": r["entity_tags"] or "",
                "source_type": r["source_type"] or "",
                "status": r["status"] or "",
                "created_at": r["created_at"],
            })

        # 时间线事件
        cursor = await db.execute(
            """SELECT id, timestamp, event_type, summary, sentiment, emotional_keywords
               FROM timeline_events ORDER BY timestamp DESC LIMIT 10"""
        )
        events = [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "event_type": r["event_type"] or "",
                "summary": r["summary"] or "",
                "sentiment": r["sentiment"],
                "emotional_keywords": r["emotional_keywords"] or "",
            }
            for r in await cursor.fetchall()
        ]

        # 实体
        cursor = await db.execute(
            """SELECT slug, title, type, summary, frontmatter, updated_at
               FROM pages WHERE type != 'system' ORDER BY updated_at DESC LIMIT 10"""
        )
        entity_rows = await cursor.fetchall()
        entities = []
        for r in entity_rows:
            fm = {}
            try:
                fm = _json.loads(r["frontmatter"]) if r["frontmatter"] else {}
            except (_json.JSONDecodeError, TypeError):
                pass
            entities.append({
                "slug": r["slug"],
                "title": r["title"],
                "type": r["type"],
                "summary": r["summary"] or "",
                "confidence": fm.get("confidence", fm.get("evidence_strength", "")),
                "updated_at": r["updated_at"],
            })

        # 关系
        cursor = await db.execute(
            """SELECT l.link_type, l.confidence, sp.title as source_title, tp.title as target_title
               FROM links l
               JOIN pages sp ON l.source_page_id = sp.id
               JOIN pages tp ON l.target_page_id = tp.id
               ORDER BY l.rowid DESC LIMIT 10"""
        )
        relations = [
            {
                "source": r["source_title"],
                "target": r["target_title"],
                "relation_type": r["link_type"] or "关联",
                "confidence": r["confidence"] or "implied",
            }
            for r in await cursor.fetchall()
        ]

    return {
        "pipeline_steps": PIPELINE_STEPS,
        "diaries": diaries,
        "step_outputs": {
            "summaries": summaries,
            "signals": signals,
            "events": events,
            "entities": entities,
            "relations": relations,
        },
    }
