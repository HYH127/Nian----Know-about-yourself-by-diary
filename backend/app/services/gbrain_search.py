from __future__ import annotations

import asyncio
import json
import math
import re

from app.database import get_connection
from app.services.vector_store import VectorStore
from app.utils.embedding import embed_texts


def _jaccard(a: str, b: str) -> float:
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _infer_source(page_type: str, frontmatter: dict = None) -> str:
    """Infer source type from page metadata"""
    if page_type == 'media':
        return 'media'
    if page_type == 'source':
        return 'imported'
    if frontmatter and frontmatter.get('source') == 'conversation':
        return 'conversation'
    # Default: diary (most pages come from diary extraction)
    return 'diary'


async def search_fts(query: str, limit: int = 40) -> list[dict]:
    async with get_connection() as conn:
        try:
            cursor = await conn.execute(
                "SELECT p.slug, p.title, p.type, p.summary, SUBSTR(p.compiled_truth, 1, 200) as snippet, rank "
                "FROM pages_fts fts "
                "JOIN pages p ON fts.rowid = p.rowid "
                "WHERE pages_fts MATCH ? "
                "ORDER BY rank "
                "LIMIT ?",
                (query, limit),
            )
            rows = await cursor.fetchall()
        except Exception:
            rows = []
        results = [
            {
                "slug": row["slug"],
                "title": row["title"],
                "type": row["type"],
                "summary": row["summary"] or "",
                "snippet": row["snippet"],
                "rank": row["rank"],
            }
            for row in rows
        ]

        # Chinese text fallback: FTS5 default tokenizer doesn't tokenize CJK
        if not results or re.search(r'[\u4e00-\u9fff]', query):
            terms = [t for t in query.split() if t.strip()]
            if not terms:
                terms = [query]
            clauses = []
            params = []
            for term in terms:
                like_val = f"%{term}%"
                clauses.append("(p.compiled_truth LIKE ? OR p.title LIKE ? OR p.aliases LIKE ?)")
                params.extend([like_val, like_val, like_val])
            where_sql = " OR ".join(clauses)
            like_cursor = await conn.execute(
                f"SELECT p.slug, p.title, p.type, p.summary, "
                f"SUBSTR(p.compiled_truth, 1, 200) as snippet, "
                f"0.0 as rank "
                f"FROM pages p "
                f"WHERE {where_sql} "
                f"ORDER BY p.updated_at DESC "
                f"LIMIT ?",
                (*params, limit),
            )
            like_rows = await like_cursor.fetchall()
            existing_slugs = {r["slug"] for r in results}
            for row in like_rows:
                if row["slug"] not in existing_slugs:
                    results.append(
                        {
                            "slug": row["slug"],
                            "title": row["title"],
                            "type": row["type"],
                            "summary": row["summary"] or "",
                            "snippet": row["snippet"],
                            "rank": row["rank"],
                        }
                    )
                    existing_slugs.add(row["slug"])

        return results


async def search_bm25(
    query: str, limit: int = 40, sources: list[str] = None
) -> list[dict]:
    async with get_connection() as conn:
        rows = []
        try:
            cursor = await conn.execute(
                "SELECT p.slug, p.title, p.type, p.summary, p.frontmatter, "
                "SUBSTR(p.compiled_truth, 1, 200) as snippet, "
                "bm25(pages_fts) as rank "
                "FROM pages_fts fts "
                "JOIN pages p ON fts.rowid = p.rowid "
                "WHERE pages_fts MATCH ? "
                "ORDER BY rank "
                "LIMIT ?",
                (query, limit),
            )
            rows = await cursor.fetchall()
        except Exception:
            rows = []
        results: list[dict] = []
        for row in rows:
            frontmatter_raw = row["frontmatter"]
            try:
                frontmatter = json.loads(frontmatter_raw) if frontmatter_raw else None
            except (json.JSONDecodeError, TypeError):
                frontmatter = None
            source = _infer_source(row["type"], frontmatter)
            if sources is not None and source not in sources:
                continue
            results.append(
                {
                    "slug": row["slug"],
                    "title": row["title"],
                    "type": row["type"],
                    "summary": row["summary"] or "",
                    "snippet": row["snippet"],
                    "highlight": row["snippet"],
                    "rank": row["rank"],
                    "source": source,
                }
            )

        # Chinese text fallback: FTS5 default tokenizer doesn't tokenize CJK
        if not results or re.search(r'[\u4e00-\u9fff]', query):
            terms = [t for t in query.split() if t.strip()]
            if not terms:
                terms = [query]
            clauses = []
            params = []
            for term in terms:
                like_val = f"%{term}%"
                clauses.append("(p.compiled_truth LIKE ? OR p.title LIKE ? OR p.aliases LIKE ?)")
                params.extend([like_val, like_val, like_val])
            where_sql = " OR ".join(clauses)
            like_cursor = await conn.execute(
                f"SELECT p.slug, p.title, p.type, p.summary, p.frontmatter, "
                f"SUBSTR(p.compiled_truth, 1, 200) as snippet "
                f"FROM pages p "
                f"WHERE {where_sql} "
                f"ORDER BY p.updated_at DESC "
                f"LIMIT ?",
                (*params, limit),
            )
            like_rows = await like_cursor.fetchall()
            existing_slugs = {r["slug"] for r in results}
            for row in like_rows:
                if row["slug"] in existing_slugs:
                    continue
                frontmatter_raw = row["frontmatter"]
                try:
                    frontmatter = (
                        json.loads(frontmatter_raw) if frontmatter_raw else None
                    )
                except (json.JSONDecodeError, TypeError):
                    frontmatter = None
                source = _infer_source(row["type"], frontmatter)
                if sources is not None and source not in sources:
                    continue
                results.append(
                    {
                        "slug": row["slug"],
                        "title": row["title"],
                        "type": row["type"],
                        "summary": row["summary"] or "",
                        "snippet": row["snippet"],
                        "highlight": row["snippet"],
                        "rank": 0.0,
                        "source": source,
                    }
                )
                existing_slugs.add(row["slug"])

        return results


async def search_vector(query: str, limit: int = 40) -> list[dict]:
    try:
        embeddings = await embed_texts([query])
        if not embeddings:
            return []
        query_vector = embeddings[0]
        results = await VectorStore().search_knowledge(query_vector, limit)
        return [
            {
                "slug": item.get("kb_id", ""),
                "title": item.get("title", ""),
                "type": item.get("type", ""),
                "summary": item.get("summary", "")[:200],
                "snippet": item.get("summary", "")[:200],
                "_distance": item.get("_distance", 0.0),
                "source": _infer_source(item.get("type", "")),
            }
            for item in results
        ]
    except Exception:
        return []


def rrf_fusion(
    fts_results: list[dict],
    vector_results: list[dict],
    k: int = 60,
) -> list[dict]:
    fused: dict[str, dict] = {}

    for i, item in enumerate(fts_results):
        slug = item.get("slug", "")
        if not slug:
            continue
        if slug not in fused:
            fused[slug] = {
                "slug": slug,
                "title": item.get("title", ""),
                "type": item.get("type", ""),
                "summary": item.get("summary", ""),
                "snippet": item.get("snippet", ""),
                "score": 0.0,
            }
        fused[slug]["score"] += 1.0 / (k + i + 1)

    for j, item in enumerate(vector_results):
        slug = item.get("slug", "")
        if not slug:
            continue
        if slug not in fused:
            fused[slug] = {
                "slug": slug,
                "title": item.get("title", ""),
                "type": item.get("type", ""),
                "summary": item.get("summary", ""),
                "snippet": item.get("snippet", ""),
                "score": 0.0,
            }
        else:
            if item.get("snippet") and not fused[slug]["snippet"]:
                fused[slug]["snippet"] = item["snippet"]
            if item.get("summary") and not fused[slug]["summary"]:
                fused[slug]["summary"] = item["summary"]
        fused[slug]["score"] += 1.0 / (k + j + 1)

    sorted_results = sorted(fused.values(), key=lambda x: x["score"], reverse=True)
    return sorted_results


def weighted_rrf_fusion(
    bm25_results: list[dict],
    vector_results: list[dict],
    source_weights: dict = None,
    k: int = 60,
) -> list[dict]:
    if source_weights is None:
        source_weights = {
            "diary": 1.5,
            "conversation": 1.2,
            "media": 1.0,
            "imported": 0.8,
            "external": 0.5,
        }
    fused: dict[str, dict] = {}

    for i, item in enumerate(bm25_results):
        slug = item.get("slug", "")
        if not slug:
            continue
        rrf_score = 1.0 / (k + i + 1)
        source = item.get("source", "external")
        weight = source_weights.get(source, 1.0)
        final_score = rrf_score * weight
        if slug not in fused:
            fused[slug] = {
                "slug": slug,
                "title": item.get("title", ""),
                "type": item.get("type", ""),
                "summary": item.get("summary", ""),
                "snippet": item.get("snippet", ""),
                "source": source,
                "score": 0.0,
                "rrf_score": 0.0,
                "score_breakdown": {"rrf_score": 0.0, "source_weight": weight, "final_score": 0.0},
            }
        fused[slug]["score"] += final_score
        fused[slug]["rrf_score"] += rrf_score
        fused[slug]["score_breakdown"] = {
            "rrf_score": fused[slug]["rrf_score"],
            "source_weight": weight,
            "final_score": fused[slug]["score"],
        }

    for j, item in enumerate(vector_results):
        slug = item.get("slug", "")
        if not slug:
            continue
        rrf_score = 1.0 / (k + j + 1)
        source = item.get("source", "external")
        weight = source_weights.get(source, 1.0)
        final_score = rrf_score * weight
        if slug not in fused:
            fused[slug] = {
                "slug": slug,
                "title": item.get("title", ""),
                "type": item.get("type", ""),
                "summary": item.get("summary", ""),
                "snippet": item.get("snippet", ""),
                "source": source,
                "score": 0.0,
                "rrf_score": 0.0,
                "score_breakdown": {"rrf_score": 0.0, "source_weight": weight, "final_score": 0.0},
            }
        else:
            if item.get("snippet") and not fused[slug]["snippet"]:
                fused[slug]["snippet"] = item["snippet"]
            if item.get("summary") and not fused[slug]["summary"]:
                fused[slug]["summary"] = item["summary"]
        fused[slug]["score"] += final_score
        fused[slug]["rrf_score"] += rrf_score
        fused[slug]["score_breakdown"] = {
            "rrf_score": fused[slug]["rrf_score"],
            "source_weight": weight,
            "final_score": fused[slug]["score"],
        }

    sorted_results = sorted(fused.values(), key=lambda x: x["score"], reverse=True)
    return sorted_results


def deduplicate_4layer(results: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for item in results:
        slug = item.get("slug", "")
        if not slug:
            continue
        if slug not in seen or item.get("score", 0.0) > seen[slug].get("score", 0.0):
            seen[slug] = item
    layer1 = list(seen.values())

    if len(layer1) <= 1:
        return layer1

    layer2: list[dict] = []
    for item in layer1:
        duplicate = False
        for kept in layer2:
            if _jaccard(
                item.get("snippet", ""),
                kept.get("snippet", ""),
            ) > 0.85:
                if item.get("score", 0.0) > kept.get("score", 0.0):
                    layer2.remove(kept)
                    layer2.append(item)
                duplicate = True
                break
        if not duplicate:
            layer2.append(item)

    if len(layer2) > 5:
        type_counts: dict[str, int] = {}
        for item in layer2:
            t = item.get("type", "")
            type_counts[t] = type_counts.get(t, 0) + 1

        total = len(layer2)
        overrepresented: set[str] = set()
        for t, count in type_counts.items():
            if count / total > 0.6:
                overrepresented.add(t)

        if overrepresented:
            keep_count = max(1, int(total * 0.6))
            layer3: list[dict] = []
            kept_by_type: dict[str, int] = {}
            for item in layer2:
                t = item.get("type", "")
                if t in overrepresented:
                    if kept_by_type.get(t, 0) < keep_count:
                        layer3.append(item)
                        kept_by_type[t] = kept_by_type.get(t, 0) + 1
                else:
                    layer3.append(item)
            return layer3
        return layer2

    return layer2


async def hybrid_search(query: str, limit: int = 20) -> list[dict]:
    bm25_task = search_bm25(query, limit=40)
    vector_task = search_vector(query, limit=40)

    bm25_results, vector_results = await asyncio.gather(bm25_task, vector_task)

    fused = weighted_rrf_fusion(bm25_results, vector_results)

    deduped = deduplicate_4layer(fused)

    return deduped[:limit]


async def hybrid_search_v2(
    query: str,
    mode: str = "balanced",
    limit: int = 20,
    sources: list[str] | None = None,
    rerank_enabled: bool = True,
    graph_enabled: bool = True,
) -> list[dict]:
    """Unified hybrid search with mode toggle.

    Modes:
    - conservative: BM25 only, no rewrite, no rerank, no graph
    - balanced: intent detect + basic rewrite + BM25 + vector + weighted RRF + rerank + graph
    - tokenmax: LLM rewrite + 2x candidates + large rerank window + two-hop graph
    """
    # Step 1: Query rewriting
    from app.services.query_rewriter import rewrite_query
    rewritten_query, intent = await rewrite_query(query, mode)

    results = []

    if mode == "conservative":
        # BM25 only, fast path
        results = await search_bm25(query, limit=limit, sources=sources)

    elif mode == "balanced":
        # Full pipeline
        candidate_limit = 40
        bm25_task = search_bm25(rewritten_query, limit=candidate_limit, sources=sources)
        vector_task = search_vector(query, limit=candidate_limit)  # Original query for vector
        bm25_results, vector_results = await asyncio.gather(bm25_task, vector_task)

        fused = weighted_rrf_fusion(bm25_results, vector_results)
        deduped = deduplicate_4layer(fused)

        # Rerank
        if rerank_enabled:
            from app.services.reranker import rerank as do_rerank
            deduped = await do_rerank(query, deduped, top_n=min(limit + 10, len(deduped)))

        results = deduped[:limit]

        # Graph complement
        if graph_enabled:
            from app.services.graph_search import graph_complement
            graph_results = await graph_complement(results, max_complement=3, depth=1)
            # Append graph results after search results
            results = results + graph_results
            results = results[:limit + 3]

    elif mode == "tokenmax":
        # Maximum quality pipeline
        candidate_limit = 80  # 2x candidates
        bm25_task = search_bm25(rewritten_query, limit=candidate_limit, sources=sources)
        vector_task = search_vector(query, limit=candidate_limit)
        bm25_results, vector_results = await asyncio.gather(bm25_task, vector_task)

        fused = weighted_rrf_fusion(bm25_results, vector_results)
        deduped = deduplicate_4layer(fused)

        # Large rerank window
        if rerank_enabled:
            from app.services.reranker import rerank as do_rerank
            deduped = await do_rerank(query, deduped, top_n=min(50, len(deduped)))

        results = deduped[:limit]

        # Two-hop graph
        if graph_enabled:
            from app.services.graph_search import graph_complement
            graph_results = await graph_complement(results, max_complement=8, depth=2)
            results = results + graph_results
            results = results[:limit + 5]

    else:
        # Unknown mode, fallback to balanced
        results = await hybrid_search(query, limit=limit)

    return results