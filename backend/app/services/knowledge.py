from __future__ import annotations

import json
import re
import uuid

from app.database import get_connection
from app.services.vector_store import VectorStore
from app.services.signals import extract_and_log_signals
from app.services.gbrain_page import upsert_page as _upsert_page, _generate_slug
from app.utils.embedding import embed_texts
from app.utils.llm import chat_completion


async def create_knowledge_item(data: dict) -> str:
    """创建知识条目"""
    kb_id = uuid.uuid4().hex
    async with get_connection() as db:
        await db.execute(
            """
            INSERT INTO knowledge_base (id, title, type, user_status, user_consumed_date, user_rating,
             user_notes, summary, genres, key_characters, themes, creator, year, source_url,
             plot_detail, cultural_impact, reviews_summary, similar_works, depth_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                kb_id,
                data.get("title"),
                data.get("type"),
                data.get("user_status", "mentioned"),
                data.get("user_consumed_date"),
                data.get("user_rating"),
                data.get("user_notes"),
                data.get("summary"),
                data.get("genres"),
                data.get("key_characters"),
                data.get("themes"),
                data.get("creator"),
                data.get("year"),
                data.get("source_url"),
                data.get("plot_detail"),
                data.get("cultural_impact"),
                data.get("reviews_summary"),
                data.get("similar_works"),
                data.get("depth_level", 1),
            ),
        )
        await db.commit()

    if data.get("summary"):
        vector = (await embed_texts([data["summary"]]))[0]
        vs = VectorStore()
        await vs.add_knowledge(
            kb_id=kb_id,
            title=data.get("title", ""),
            type=data.get("type", ""),
            summary=data.get("summary", ""),
            genres=data.get("genres", ""),
            themes=data.get("themes", ""),
            vector=vector,
        )

    return kb_id


async def find_knowledge_by_title_fuzzy(title: str) -> dict | None:
    """大小写不敏感查找知识条目"""
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM knowledge_base WHERE LOWER(title) = LOWER(?)",
            (title.strip(),),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def detect_media_context(content: str) -> str | None:
    """使用 LLM 检测内容是否在讨论媒体作品，返回媒体标题或 None"""
    if not content or len(content.strip()) < 20:
        return None

    try:
        response = await chat_completion(
            messages=[{
                "role": "system",
                "content": (
                    "判断以下内容是否在讨论某个具体的媒体作品（书、电影、电视剧、音乐、播客等）。"
                    "如果内容主要是在讨论某个媒体作品中的角色、剧情、事件或感受，"
                    "返回该媒体作品的标题（仅返回标题字符串）。"
                    "如果内容不是在讨论媒体作品，返回 null。"
                    "只返回标题或 null，不要返回其他内容。"
                ),
            }, {
                "role": "user",
                "content": content[:2000],
            }],
            temperature=0.1,
            max_tokens=100,
        )
        result = response.strip()
        if result.lower() in ("null", "none", "无", "不是", ""):
            return None
        # Strip common quotation marks
        result = result.strip('"').strip("'").strip("《").strip("》")
        return result if result else None
    except Exception:
        return None


async def upsert_knowledge_item(item: dict) -> str | None:
    title = (item.get("title") or "").strip()
    kb_type = (item.get("type") or "").strip()
    if not title or not kb_type:
        return None

    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT id FROM knowledge_base WHERE title = ? AND type = ?",
            (title, kb_type),
        )
        existing = await cursor.fetchone()
        if existing:
            return existing["id"]

        kb_id = item.get("id") or str(uuid.uuid4())
        summary = (item.get("summary") or "")[:2000]
        depth_level = item.get("depth_level", 1)
        source = (item.get("source") or "")[:50]
        genres = (item.get("genres") or "")[:200]
        themes = (item.get("themes") or "")[:500]
        creator = (item.get("creator") or "")[:200]
        key_characters = (item.get("key_characters") or "")[:500]
        user_status = (item.get("user_status") or "mentioned")[:50]
        source_url = (item.get("source_url") or "")[:1000]

        await db.execute(
            """INSERT INTO knowledge_base (id, title, type, summary, depth_level, source, genres, themes, creator, key_characters, user_status, source_url, created_at, last_updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (kb_id, title, kb_type, summary, depth_level, source, genres, themes, creator, key_characters, user_status, source_url),
        )

        cursor = await db.execute("SELECT rowid FROM knowledge_base WHERE id = ?", (kb_id,))
        row = await cursor.fetchone()
        await db.execute(
            "INSERT INTO knowledge_fts(rowid, title, summary, genres, themes, creator) VALUES (?, ?, ?, ?, ?, ?)",
            (row["rowid"], title, summary, genres, themes, creator),
        )
        await db.commit()

    try:
        text_for_vector = f"{title} {summary} {genres} {themes}".strip()
        if text_for_vector:
            vector = (await embed_texts([text_for_vector]))[0]
            vs = VectorStore()
            await vs.add_knowledge(
                kb_id=kb_id,
                title=title,
                type=kb_type,
                summary=summary,
                genres=genres,
                themes=themes,
                vector=vector,
            )
    except Exception:
        pass

    return kb_id


async def extract_knowledge_from_import(data: dict, source: str) -> list[str]:
    results = []

    items_to_extract = data.get("items", [data]) if isinstance(data, dict) else data
    if not isinstance(items_to_extract, list):
        items_to_extract = [items_to_extract]

    for item in items_to_extract:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("name") or item.get("contact_name", "")
        if not title:
            continue
        # Remove Chinese book title marks to avoid duplicate entities
        title = re.sub(r'[《》]', '', title)
        summary = str(item.get("summary") or item.get("description") or item.get("notes", ""))
        kb_item = {
            "title": title[:200],
            "type": item.get("type", "imported"),
            "summary": summary[:2000],
            "depth_level": 1,
            "source": f"import:{source}",
            "genres": "",
            "themes": "",
        }
        kb_id = await upsert_knowledge_item(kb_item)
        if kb_id:
            results.append(kb_id)

    return results


async def extract_knowledge_from_diary(diary_text: str, diary_id: str = "") -> list[str]:
    if not diary_text or len(diary_text.strip()) < 30:
        return []

    # Detect if content is discussing a media work
    media_parent = await detect_media_context(diary_text)

    try:
        media_isolation_rule = ""
        if media_parent:
            media_isolation_rule = f"\n\n【媒体上下文隔离规则】当前内容正在讨论媒体作品《{media_parent}》。该作品中的角色、事件、情绪属于该媒体实体的子内容，不应创建独立的 person/event/emotion_pattern 实体。应将这些内容归入 media 类型实体，并在 type_fields 中添加 media_parent: \"{media_parent}\"。例如：如果提到《{media_parent}》中的角色'某某'，不要创建 person 类型的实体，而是将角色信息作为 media 实体的 key_characters 字段。"
        else:
            media_isolation_rule = "\n\n【媒体上下文隔离规则】如果内容中提到某个媒体作品（书、电影、电视剧、音乐、播客等）中的角色、事件或情绪，不要为它们创建独立的 person/event/emotion_pattern 实体。这些内容应归入 media 类型实体，并在 type_fields 中添加 media_parent 字段指向所属媒体作品标题。例如：《风骚律师》中的角色'索尔'不应创建独立的 person 实体，而应作为 media 实体《风骚律师》的子内容。"

        content = await chat_completion(
            messages=[{
                "role": "system",
                "content": "从以下日记中提取可结构化的知识实体。只返回JSON数组，每个元素包含：\n- title: 实体标题（简洁，如\"小王\"、\"晨跑\"、\"周一焦虑\"）\n- summary: 基于日记原文内容的一句话总结（≤100字），必须从用户视角描述与该实体的关系、互动或影响，禁止概念性解释。例如对人物应描述\"用户与某人的关系和互动\"，对概念应描述\"用户对此概念的理解和实践\"，对习惯应描述\"用户的频率和场景\"，而非百科式定义。\n- type: 实体类型，可选值：person(人物)、place(地点)、event(事件)、concept(概念)、habit(习惯)、emotion_pattern(情绪模式)、value_signal(价值观信号)、company(组织)、project(项目)、meeting(会议)、media(书影音)、learning(学习收获)\n- tags: 标签数组（如[\"同事\",\"跑步搭子\"]）\n- aliases: 别名数组（可选，如人物的小名）\n- related_entities: 关系数组（可选，格式：[[\"type:slug\", \"关系描述\", \"confidence:explicit/frequent/implied/inferred\"]]）\n- type_fields: 类型专属字段（可选，根据实体类型输出）：\n  - person: intimacy(0-100整数), relationship_type(如\"同事\"/\"朋友\"/\"同学\")\n  - habit: habit_type(如\"运动\"/\"学习\"), frequency_30d(整数，估计30天内出现次数)\n  - emotion_pattern: triggers(触发条件列表), emotion_type(如\"焦虑\"/\"开心\"), recovery_method(恢复方式)\n  - value_signal: signal_type(如\"重视家庭\"/\"追求效率\"), evidence_strength(explicit/frequent/implied/inferred)\n  - place: place_type(如\"餐厅\"/\"学校\"), related_activities(关联活动列表)\n  - media: media_type(如\"book\"/\"movie\"/\"tv_series\"/\"music\"/\"podcast\"), rating(1-5整数), director(导演/作者), key_characters(主要人物列表), media_summary(作品摘要), media_parent(所属媒体作品标题，仅当该实体是某媒体作品的子内容时填写)\n\n【严格过滤规则】以下内容绝对不要提取为实体：\n- 消费金额（如\"花了XX块\"\"XX元\"），金额不是实体，消费行为应记录在人物或店落实体下\n- 短暂情绪（如\"高兴\"\"开心\"\"难过\"），除非有≥5次证据的反复情绪模式\n- 日常琐事（如\"吃了饭\"\"打电话\"\"视频聊天\"），除非涉及重要人物且≥5次\n- 泛指（如\"同学\"\"室友\"\"老师\"），除非有具体姓名\n- 抽象概念（如\"人际互动\"\"做出决定\"\"计划\"\"学到\"\"总结\"\"反思\"\"打电话\"），太泛无信息量\n- 单次小事（如\"今天下雨\"），除非有持续影响\n\n准入标准（至少满足一条才提取）：\n- 具体人物/地点/组织：如\"王小明\"、\"万达\"、\"编程培训班\"\n- 习惯（≥3次证据）：如\"跑步\"、\"瑞幸拿铁\"\n- 情绪模式（≥5次证据）：如\"周一焦虑\"\n- 价值观信号：如\"重视健康\"\n- 书影音作品：如\"百年孤独\"\n- 人生事件：如\"表姐的婚礼\"\n\n书影音作品的 title 不要带书名号《》，直接写作品名（如\"百年孤独\"而非\"《百年孤独》\"）\n\n如果无有长期价值的实体则返回空数组[]。" + media_isolation_rule
            }, {
                "role": "user",
                "content": diary_text[:3000]
            }],
            temperature=0.3,
            max_tokens=20000,
            purpose="知识提取",
        )
        try:
            items = json.loads(content)
            if not isinstance(items, list):
                return []
        except json.JSONDecodeError:
            items_str = content.strip()
            # Remove code fence markers
            if items_str.startswith("```"):
                items_str = re.sub(r'^```(?:json)?\s*\n?', '', items_str)
                items_str = re.sub(r'\n?```\s*$', '', items_str)
            try:
                items = json.loads(items_str)
            except json.JSONDecodeError:
                # Try to fix truncated JSON: find last complete object and close the array
                last_brace = items_str.rfind('}')
                if last_brace > 0:
                    truncated = items_str[:last_brace + 1] + ']'
                    bracket_pos = truncated.find('[')
                    if bracket_pos >= 0:
                        truncated = truncated[bracket_pos:]
                    try:
                        items = json.loads(truncated)
                    except json.JSONDecodeError:
                        return []
                else:
                    return []

        await extract_and_log_signals(diary_text, source_type="diary", source_id=diary_id)

        results = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", ""))[:200].strip()
            summary = str(item.get("summary", ""))[:500].strip()
            if not title:
                continue
            
            # Post-filter: reject garbage entities
            kb_type_init = str(item.get("type", "learning"))
            # Reject spending amount entities
            if re.match(r'^花了?\d+[块元]?$', title) or re.match(r'^消费\d+[元块]$', title) or re.match(r'^\d+[块元]$', title):
                continue
            # Reject abstract concepts
            garbage_concepts = {"人际互动", "做出决策", "目标意愿", "计划", "学到", "总结", "回顾", "反思领悟", "聊天", "打电话", "打电话聊天", "电话", "沟通"}
            if kb_type_init == "concept" and title in garbage_concepts:
                continue
            # Reject single-use trivia
            garbage_events = {"下雨了", "今天下雨", "天气好", "吃了饭", "吃了午饭", "吃了晚饭", "吃了早餐", "洗了个澡", "做了作业", "写了作业"}
            if kb_type_init == "event" and title in garbage_events:
                continue
            # Reject too-short titles that are just verbs
            if len(title) <= 2 and kb_type_init == "concept":
                continue
            kb_type = str(item.get("type", "learning"))
            # Map type to page type
            type_mapping = {
                "person": "person", "place": "place", "event": "event",
                "concept": "concept", "habit": "habit",
                "emotion_pattern": "emotion_pattern", "value_signal": "value_signal",
                "company": "company", "project": "project",
                "meeting": "meeting", "media": "media",
                "learning": "concept", "insight": "concept", "fact": "concept",
                "experience": "concept",
            }
            page_type = type_mapping.get(kb_type, "concept")
            slug = _generate_slug(title)
            tags = item.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            aliases = item.get("aliases", [])
            if isinstance(aliases, str):
                aliases = [a.strip() for a in aliases.split(",") if a.strip()]
            related = item.get("related_entities", [])
            
            frontmatter = {"source": "diary", "original_type": kb_type}
            if tags:
                frontmatter["tags"] = tags
            if aliases:
                frontmatter["aliases"] = aliases
            if related:
                # Convert array format to Wikilink format
                rel_entries = []
                for rel in related:
                    if isinstance(rel, list) and len(rel) >= 2:
                        target = rel[0]
                        relation = rel[1]
                        confidence = rel[2] if len(rel) > 2 else "implied"
                        rel_entries.append(f"[[{target}]] | {relation} | confidence: {confidence}")
                    elif isinstance(rel, str):
                        rel_entries.append(rel)
                if rel_entries:
                    frontmatter["related_entities"] = rel_entries

            type_fields = item.get("type_fields", {})
            if isinstance(type_fields, dict) and type_fields:
                frontmatter.update(type_fields)

            # Media context isolation: if media_parent was detected, tag the entity
            if media_parent:
                frontmatter["media_parent"] = media_parent

            result = await _upsert_page({
                "slug": slug,
                "type": page_type,
                "title": title,
                "compiled_truth": summary,
                "summary": summary,
                "frontmatter": frontmatter,
            })
            if result:
                results.append(result)
                # Link timeline events to this newly created/updated page
                try:
                    from app.services.timeline import link_timeline_to_pages
                    await link_timeline_to_pages(slug, title)
                except Exception:
                    pass  # Non-critical: linking can be retried later

        return results
    except Exception:
        return []
