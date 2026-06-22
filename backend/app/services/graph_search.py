from __future__ import annotations

import json
import math
import time

import aiosqlite
import structlog

from app.database import get_connection

logger = structlog.get_logger()

# 实体名称匹配缓存: (pages_list, timestamp)
# TTL 5 分钟，避免每次对话都全量加载
_entities_cache: tuple[list[dict], float] = ([], 0)
_ENTITIES_CACHE_TTL = 300  # 5 分钟

# 实体 embedding 缓存: (embeddings_map, timestamp)
# 与 _entities_cache 同步过期
_embeddings_cache: tuple[dict[str, list[float]], float] = ({}, 0)


def _placeholders(n: int) -> str:
    return ",".join("?" for _ in range(n))


async def _query_neighbors(
    db: aiosqlite.Connection,
    slugs: list[str],
    exclude_slugs: set[str],
) -> list[dict]:
    if not slugs:
        return []

    ph = _placeholders(len(slugs))
    ex_ph = _placeholders(len(exclude_slugs))

    sql = f"""
        SELECT DISTINCT p.slug, p.title, p.type, SUBSTR(p.compiled_truth, 1, 200) as snippet
        FROM links l
        JOIN pages sp ON l.source_page_id = sp.id
        JOIN pages p ON l.target_page_id = p.id
        WHERE sp.slug IN ({ph})
          AND p.slug NOT IN ({ex_ph})
        UNION
        SELECT DISTINCT p.slug, p.title, p.type, SUBSTR(p.compiled_truth, 1, 200) as snippet
        FROM links l
        JOIN pages tp ON l.target_page_id = tp.id
        JOIN pages p ON l.source_page_id = p.id
        WHERE tp.slug IN ({ph})
          AND p.slug NOT IN ({ex_ph})
    """

    params = list(slugs) + list(exclude_slugs) + list(slugs) + list(exclude_slugs)
    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def _count_connections(
    db: aiosqlite.Connection,
    search_slugs: list[str],
    graph_slugs: list[str],
) -> dict[str, int]:
    if not search_slugs or not graph_slugs:
        return {}

    s_ph = _placeholders(len(search_slugs))
    g_ph = _placeholders(len(graph_slugs))

    sql = f"""
        SELECT p.slug, COUNT(DISTINCT sp.slug) as connections
        FROM links l
        JOIN pages sp ON sp.id IN (l.source_page_id, l.target_page_id)
        JOIN pages p ON p.id IN (l.source_page_id, l.target_page_id) AND p.id != sp.id
        WHERE sp.slug IN ({s_ph})
          AND p.slug IN ({g_ph})
        GROUP BY p.slug
        ORDER BY connections DESC
    """

    cursor = await db.execute(sql, list(search_slugs) + list(graph_slugs))
    rows = await cursor.fetchall()
    return {r["slug"]: r["connections"] for r in rows}


async def graph_complement(
    search_results: list[dict],
    max_complement: int = 3,
    depth: int = 1,
) -> list[dict]:
    if not search_results:
        return []

    search_slugs = [r["slug"] for r in search_results]
    search_slug_set = set(search_slugs)
    seen = set(search_slugs)

    async with get_connection() as db:
        all_graph = []

        # depth 1
        neighbors = await _query_neighbors(db, search_slugs, seen)
        for row in neighbors:
            row["source"] = "graph"
            row["_graph_depth"] = 1
        all_graph.extend(neighbors)
        seen.update(r["slug"] for r in neighbors)

        # depth 2
        if depth >= 2 and neighbors:
            d1_slugs = [r["slug"] for r in neighbors]
            d2_neighbors = await _query_neighbors(db, d1_slugs, seen)
            for row in d2_neighbors:
                row["source"] = "graph"
                row["_graph_depth"] = 2
            all_graph.extend(d2_neighbors)

        if not all_graph:
            return []

        # count connections
        graph_slugs = [r["slug"] for r in all_graph]
        counts = await _count_connections(db, search_slugs, graph_slugs)

        for row in all_graph:
            row["_connections"] = counts.get(row["slug"], 0)

        all_graph.sort(key=lambda r: r["_connections"], reverse=True)

        for row in all_graph:
            row.pop("_connections", None)

    return all_graph[:max_complement]


# ---------------------------------------------------------------------------
# 实体命中检测 + BFS 图谱搜索
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _load_entity_pages() -> list[dict]:
    """加载所有非 system 类型的实体页面（带内存缓存，TTL 5 分钟）。

    从 SQLite 加载，包含完整 compiled_truth。
    返回字段：slug, title, type, summary, compiled_truth, aliases_list, updated_at
    """
    global _entities_cache
    pages, ts = _entities_cache
    if pages and time.time() - ts < _ENTITIES_CACHE_TTL:
        return pages

    try:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT slug, title, type, summary, compiled_truth, aliases, updated_at "
                "FROM pages WHERE type != 'system'"
            )
            rows = await cursor.fetchall()
            pages = []
            for row in rows:
                try:
                    aliases_list = json.loads(row["aliases"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    aliases_list = []
                pages.append({
                    "slug": row["slug"],
                    "title": row["title"],
                    "type": row["type"],
                    "summary": row["summary"] or "",
                    "compiled_truth": row["compiled_truth"] or "",
                    "aliases_list": aliases_list,
                    "updated_at": row["updated_at"] or "",
                })
            _entities_cache = (pages, time.time())
            return pages
    except Exception:
        logger.exception("load_entity_pages_failed")
        return []


def _chinese_boundary_match(text: str, name: str) -> bool:
    """中文友好的词边界匹配：确保 name 在 text 中作为独立词出现。

    非中文字符（字母、数字、标点、空格）视为边界，
    中文字符之间不做边界检查（中文无空格分词）。
    """
    idx = 0
    while True:
        pos = text.find(name, idx)
        if pos == -1:
            return False
        before_ok = (pos == 0) or not _is_word_char(text[pos - 1])
        after_ok = (pos + len(name) >= len(text)) or not _is_word_char(text[pos + len(name)])
        if before_ok and after_ok:
            return True
        idx = pos + 1


def _is_word_char(ch: str) -> bool:
    """判断字符是否为"词字符"（字母、数字、下划线），这些字符不构成中文词边界。"""
    return ch.isalpha() or ch.isdigit() or ch == "_"


def _name_match_pages(text: str, pages: list[dict]) -> list[dict]:
    """名称匹配：最长标题优先，大小写不敏感。检查 title 和 aliases。

    参考 timeline._match_page_slugs 的最长标题优先策略，避免
    "王小波" 与 "小波" 重复匹配。使用中文友好的词边界检查避免子串误匹配。
    """
    text_lower = text.lower()
    candidates: list[tuple[str, dict]] = []
    for page in pages:
        title = (page.get("title") or "").strip()
        if title and len(title) >= 2:
            candidates.append((title, page))
        for alias in page.get("aliases_list", []):
            alias = (alias or "").strip()
            if alias and len(alias) >= 2:
                candidates.append((alias, page))

    # 按名称长度降序，长名优先匹配
    candidates.sort(key=lambda x: len(x[0]), reverse=True)

    matched: list[dict] = []
    matched_titles: set[str] = set()
    seen_slugs: set[str] = set()
    for name, page in candidates:
        name_lower = name.lower()
        # 跳过已被更长名称包含的短名
        if any(name_lower in mt for mt in matched_titles if len(mt) > len(name_lower)):
            continue
        if _chinese_boundary_match(text_lower, name_lower):
            if page["slug"] not in seen_slugs:
                matched.append(page)
                seen_slugs.add(page["slug"])
            matched_titles.add(name_lower)
    return matched


async def _compute_page_embeddings(pages: list[dict]) -> dict[str, list[float]]:
    """批量计算实体页面的 embedding，带缓存。

    embedding 文本 = title + summary（摘要比全文更精准，且 token 更少）。
    """
    global _embeddings_cache
    emb_map, ts = _embeddings_cache
    # 缓存与 _entities_cache 同步过期
    if emb_map and time.time() - ts < _ENTITIES_CACHE_TTL:
        return emb_map

    from app.utils.embedding import embed_texts

    emb_map = {}
    if not pages:
        return emb_map

    # 构造 embedding 文本
    texts = []
    for p in pages:
        title = (p.get("title") or "").strip()
        summary = (p.get("summary") or "").strip()
        texts.append(f"{title} {summary}".strip())

    try:
        vectors = await embed_texts(texts)
        for p, vec in zip(pages, vectors):
            emb_map[p["slug"]] = vec
        _embeddings_cache = (emb_map, time.time())
    except Exception:
        logger.exception("compute_page_embeddings_failed")

    return emb_map


async def detect_entity_hits(text: str, query_vector: list[float] = None) -> list[dict]:
    """检测文本中命中的实体（名称匹配 + 语义检索）。

    返回命中实体列表，每项含 slug/title/type/summary/compiled_truth/hit_type/score。
    query_vector: 预计算的 query embedding（可选，避免重复调用 embedding API）。
    """
    if not text or not text.strip():
        return []
    try:
        pages = await _load_entity_pages()
        if not pages:
            return []

        # a. 名称匹配
        name_matched = _name_match_pages(text, pages)
        name_slugs = {p["slug"] for p in name_matched}

        # b. 语义检索（实时计算 embedding + 余弦相似度）
        semantic_hits: list[tuple[float, dict]] = []
        try:
            from app.utils.embedding import embed_texts

            if query_vector is None:
                query_vector = (await embed_texts([text]))[0]

            page_embeddings = await _compute_page_embeddings(pages)

            scored: list[tuple[float, dict]] = []
            for p in pages:
                if p["slug"] in name_slugs:
                    continue
                vec = page_embeddings.get(p["slug"])
                if vec is None:
                    continue
                sim = _cosine_similarity(query_vector, vec)
                if sim >= 0.5:
                    scored.append((sim, p))

            scored.sort(key=lambda x: x[0], reverse=True)
            semantic_hits = scored[:5]
        except Exception:
            logger.exception("semantic_entity_search_failed")

        # 合并结果（名称匹配在前，score=1.0）
        results: list[dict] = []
        for page in name_matched:
            results.append({
                "slug": page["slug"],
                "title": page.get("title") or "",
                "type": page.get("type") or "concept",
                "summary": page.get("summary") or "",
                "compiled_truth": page.get("compiled_truth") or "",
                "hit_type": "name",
                "score": 1.0,
            })
        for score, page in semantic_hits:
            results.append({
                "slug": page["slug"],
                "title": page.get("title") or "",
                "type": page.get("type") or "concept",
                "summary": page.get("summary") or "",
                "compiled_truth": page.get("compiled_truth") or "",
                "hit_type": "semantic",
                "score": round(score, 4),
            })

        return results
    except Exception:
        logger.exception("detect_entity_hits_failed")
        return []


async def _query_bfs_neighbors(
    db: aiosqlite.Connection,
    frontier_slugs: list[str],
    seen_slugs: set[str],
) -> list[dict]:
    """查询 frontier 的邻居实体（带 link_type），排除已访问的 slug。

    links 表是双向的（source/target 都可能指向实体），用 UNION 覆盖两个方向。
    """
    if not frontier_slugs:
        return []

    ph = _placeholders(len(frontier_slugs))
    seen_list = list(seen_slugs)
    if seen_list:
        ex_ph = _placeholders(len(seen_list))
        exclude_clause = f"AND p.slug NOT IN ({ex_ph})"
    else:
        exclude_clause = ""

    sql = f"""
        SELECT DISTINCT p.slug, p.title, p.type, p.summary, p.compiled_truth, l.link_type,
               'forward' as _direction
        FROM links l
        JOIN pages fp ON fp.id = l.source_page_id
        JOIN pages p ON p.id = l.target_page_id
        WHERE fp.slug IN ({ph})
          AND p.type != 'system'
          {exclude_clause}
        UNION
        SELECT DISTINCT p.slug, p.title, p.type, p.summary, p.compiled_truth, l.link_type,
               'backward' as _direction
        FROM links l
        JOIN pages fp ON fp.id = l.target_page_id
        JOIN pages p ON p.id = l.source_page_id
        WHERE fp.slug IN ({ph})
          AND p.type != 'system'
          {exclude_clause}
    """

    params: list = list(frontier_slugs)
    if seen_list:
        params += seen_list
    params += list(frontier_slugs)
    if seen_list:
        params += seen_list

    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def bfs_entity_search(hit_slugs: list[str], max_depth: int = 1) -> list[dict]:
    """从命中实体出发进行 BFS 图谱搜索，动态调整深度。

    每层搜索后评估信息量：若邻居总内容长度 < 500 或邻居数量 < 3，且未达
    max_depth，则继续搜索下一层。最大深度限制为 2。
    """
    if not hit_slugs:
        return []
    try:
        max_depth = min(max_depth, 2)  # 防止过度搜索
        results: list[dict] = []
        seen: set[str] = set(hit_slugs)

        async with get_connection() as db:
            frontier_slugs = list(hit_slugs)
            depth = 1
            while depth <= max_depth and frontier_slugs:
                neighbors = await _query_bfs_neighbors(db, frontier_slugs, seen)
                if not neighbors:
                    break

                # 去重：同一 slug 只保留第一次出现
                added: list[dict] = []
                for n in neighbors:
                    if n["slug"] in seen:
                        continue
                    n["depth"] = depth
                    added.append(n)
                    seen.add(n["slug"])
                results.extend(added)

                # 评估信息量是否足够
                total_content_len = sum(
                    len(n.get("compiled_truth") or "") for n in results
                )
                if total_content_len >= 500 and len(results) >= 3:
                    break

                # 准备下一层 frontier
                frontier_slugs = [n["slug"] for n in added]
                depth += 1

        return results
    except Exception:
        logger.exception("bfs_entity_search_failed")
        return []


_TYPE_LABELS = {
    "person": "人物",
    "concept": "概念",
    "media": "媒体",
    "source": "来源",
    "work": "作品",
    "organization": "组织",
    "place": "地点",
    "event": "事件",
}


def _type_label(type_str: str) -> str:
    return _TYPE_LABELS.get(type_str, type_str or "实体")


def _format_context(hits: list[dict], neighbors: list[dict]) -> str:
    """格式化上下文文本，用于注入对话。compiled_truth 截断到前 300 字。"""
    if not hits and not neighbors:
        return ""
    lines: list[str] = []
    if hits:
        lines.append("命中的实体：")
        for h in hits:
            truth = (h.get('compiled_truth', '') or '')[:300]
            if len(h.get('compiled_truth', '') or '') > 300:
                truth += "..."
            lines.append(
                f"- [{_type_label(h.get('type', ''))}] {h.get('title', '')}：{truth}"
            )
    if neighbors:
        if lines:
            lines.append("")
        lines.append("相关实体（图谱搜索）：")
        for n in neighbors:
            truth = (n.get('compiled_truth', '') or '')[:300]
            if len(n.get('compiled_truth', '') or '') > 300:
                truth += "..."
            lines.append(
                f"- [{_type_label(n.get('type', ''))}] {n.get('title', '')}"
                f"（{n.get('depth', 1)}跳）：{truth}"
            )
    return "\n".join(lines)


async def entity_search(text: str, max_hits: int = 5, max_depth: int = 2, query_vector: list[float] = None) -> dict:
    """完整的实体搜索流程：命中检测 + BFS 图谱搜索 + 上下文格式化。

    返回 {"hits": [...], "neighbors": [...], "context_text": "..."}。
    无命中时返回空 dict。
    query_vector: 预计算的 query embedding（可选，避免重复调用 embedding API）。
    """
    try:
        if not text or not text.strip():
            return {"hits": [], "neighbors": [], "context_text": ""}

        hits = await detect_entity_hits(text, query_vector=query_vector)
        if not hits:
            return {"hits": [], "neighbors": [], "context_text": ""}

        hits = hits[:max_hits]
        hit_slugs = [h["slug"] for h in hits]
        neighbors = await bfs_entity_search(hit_slugs, max_depth=max_depth)
        context_text = _format_context(hits, neighbors)

        return {
            "hits": hits,
            "neighbors": neighbors,
            "context_text": context_text,
        }
    except Exception:
        logger.exception("entity_search_failed")
        return {"hits": [], "neighbors": [], "context_text": ""}
