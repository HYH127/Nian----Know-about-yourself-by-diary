"""冻结快照服务 - 双层快照架构，利用 KV Cache 加速对话

架构设计：
- 核心层（Core Layer）：长期画像 + 高频实体，~800 tokens，会话内完全冻结，命中 KV Cache
- 情境层（Context Layer）：月/周画像 + 按情境相关实体，~2000 tokens，会话内缓存
- 动态区（Dynamic Zone）：变化提醒 + 中期记忆 + 近期时间线，每次对话可能变化

System Prompt 布局：
  [核心层 - 冻结]  ← KV Cache 命中
  [情境层 - 会话缓存] ← 同一会话内不变
  [动态区 - 每次重建] ← 每次对话可能不同

KV Cache 优化原理：
  同一会话内，核心层 + 情境层 的 token 只需计算一次 KV，
  后续对话复用已缓存的 KV，只重新计算动态区 + 用户消息 + 助手回复。
"""

import json
import os
from datetime import datetime

from app.utils.token_counter import count_tokens

SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "snapshots")

# 双层 Token 预算
CORE_TOKEN_LIMIT = 4000        # 核心层：长期画像 + 高频实体（命中 KV Cache，越丰富越好）
CONTEXT_TOKEN_LIMIT = 10000    # 情境层：月/周画像 + 按类型实体（会话内缓存）
TOTAL_TOKEN_LIMIT = 20000      # 总 Token 上限


class SnapshotLayers:
    """双层快照结果"""

    def __init__(self):
        self.core_text: str = ""          # 核心层文本（冻结，命中 KV Cache）
        self.context_text: str = ""       # 情境层文本（会话内缓存）
        self.core_tokens: int = 0
        self.context_tokens: int = 0
        self.sections: list[dict] = []    # 各 section 统计

    @property
    def full_text(self) -> str:
        """合并核心层 + 情境层"""
        parts = []
        if self.core_text:
            parts.append(self.core_text)
        if self.context_text:
            parts.append(self.context_text)
        return "\n\n".join(parts)

    @property
    def total_tokens(self) -> int:
        return self.core_tokens + self.context_tokens


async def _load_portrait(portrait_type: str) -> str | None:
    """从 portrait_records 加载画像"""
    try:
        from app.database import get_connection
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT modules_json FROM portrait_records WHERE portrait_type=? AND is_current=1 ORDER BY created_at DESC LIMIT 1",
                (portrait_type,)
            )
            row = await cursor.fetchone()
            if row:
                modules = json.loads(row["modules_json"])
                return "\n".join([m.get("content", "") for m in modules])
    except Exception:
        pass
    return None


async def _load_top_entities(limit: int = 20) -> list[dict]:
    """加载高频/高亲密度实体摘要"""
    try:
        from app.database import get_connection
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT title, summary, type FROM pages WHERE type != 'system' ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in await cursor.fetchall()]
    except Exception:
        return []


async def _load_entities_by_type(entity_type: str, limit: int = 10) -> list[dict]:
    """按类型加载实体摘要"""
    try:
        from app.database import get_connection
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT title, summary, type FROM pages WHERE type=? ORDER BY updated_at DESC LIMIT ?",
                (entity_type, limit)
            )
            return [dict(row) for row in await cursor.fetchall()]
    except Exception:
        return []


def _entities_to_text(entities: list[dict]) -> str:
    """将实体列表转为文本"""
    return "\n".join([f"- {e['title']}({e.get('type', '')}): {e['summary']}" for e in entities])


async def build_core_layer() -> tuple[str, int]:
    """构建核心层：长期画像 + 高频实体

    核心层在会话内完全冻结，是 KV Cache 命中的关键部分。
    只包含最稳定、最重要的信息。
    """
    parts = []

    # 1. 长期画像（最稳定的核心人格）
    long_term = await _load_portrait("long_term")
    if long_term:
        parts.append(f"【长期画像】\n{long_term}")

    # 2. 高频实体（最常出现的实体，top 30）
    entities = await _load_top_entities(limit=30)
    if entities:
        entity_text = _entities_to_text(entities)
        parts.append(f"【核心实体】\n{entity_text}")

    text = "\n\n".join(parts)

    # 裁剪到核心层 Token 限制
    while count_tokens(text) > CORE_TOKEN_LIMIT and parts:
        parts.pop()
        text = "\n\n".join(parts)

    return text, count_tokens(text)


async def build_context_layer() -> tuple[str, int]:
    """构建情境层：月/周画像 + 按类型实体

    情境层在同一会话内缓存不变，但不同会话可能不同
    （如用户更新画像后，新会话会加载新的情境层）。
    """
    parts = []

    # 1. 本月画像
    monthly = await _load_portrait("monthly")
    if monthly:
        parts.append(f"【本月画像】\n{monthly}")

    # 2. 本周画像
    weekly = await _load_portrait("weekly")
    if weekly:
        parts.append(f"【本周画像】\n{weekly}")

    # 3. 细致画像
    detailed = await _load_portrait("detailed")
    if detailed:
        parts.append(f"【细致画像】\n{detailed}")

    # 4. 深度画像
    deep = await _load_portrait("deep")
    if deep:
        parts.append(f"【深度画像】\n{deep}")

    # 5. 按类型加载重要实体（人物、习惯、情绪模式、价值观）
    person_entities = await _load_entities_by_type("person", limit=15)
    if person_entities:
        parts.append(f"【重要人物】\n{_entities_to_text(person_entities)}")

    habit_entities = await _load_entities_by_type("habit", limit=10)
    if habit_entities:
        parts.append(f"【习惯模式】\n{_entities_to_text(habit_entities)}")

    emotion_entities = await _load_entities_by_type("emotion_pattern", limit=8)
    if emotion_entities:
        parts.append(f"【情绪模式】\n{_entities_to_text(emotion_entities)}")

    value_entities = await _load_entities_by_type("value_signal", limit=5)
    if value_entities:
        parts.append(f"【价值观信号】\n{_entities_to_text(value_entities)}")

    media_entities = await _load_entities_by_type("media", limit=10)
    if media_entities:
        parts.append(f"【书影音记录】\n{_entities_to_text(media_entities)}")

    text = "\n\n".join(parts)

    # 裁剪到情境层 Token 限制
    while count_tokens(text) > CONTEXT_TOKEN_LIMIT and parts:
        parts.pop()
        text = "\n\n".join(parts)

    return text, count_tokens(text)


async def build_snapshot_layers() -> SnapshotLayers:
    """构建双层快照"""
    result = SnapshotLayers()

    # 核心层
    core_text, core_tokens = await build_core_layer()
    result.core_text = core_text
    result.core_tokens = core_tokens
    result.sections.append({"name": "核心层", "token_count": core_tokens, "limit": CORE_TOKEN_LIMIT})

    # 情境层
    context_text, context_tokens = await build_context_layer()
    result.context_text = context_text
    result.context_tokens = context_tokens
    result.sections.append({"name": "情境层", "token_count": context_tokens, "limit": CONTEXT_TOKEN_LIMIT})

    return result


async def build_snapshot() -> str:
    """编译画像快照（兼容旧接口），返回合并文本"""
    layers = await build_snapshot_layers()
    return layers.full_text


async def get_or_build_snapshot() -> str:
    """获取缓存的快照，如果过期或不存在则重新编译

    缓存策略：
    - 核心层缓存 6 小时（长期画像变化缓慢）
    - 情境层缓存 1 小时（月/周画像可能更新）
    - 返回合并文本（兼容旧接口）
    """
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    core_file = os.path.join(SNAPSHOT_DIR, "core_layer.txt")
    context_file = os.path.join(SNAPSHOT_DIR, "context_layer.txt")
    meta_file = os.path.join(SNAPSHOT_DIR, "snapshot_meta.json")

    core_text = None
    context_text = None

    # 尝试从缓存加载
    if os.path.exists(meta_file):
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        now = datetime.now()

        # 核心层缓存 6 小时
        core_built_at = datetime.fromisoformat(meta.get("core_built_at", "2000-01-01"))
        if (now - core_built_at).total_seconds() < 21600 and os.path.exists(core_file):
            with open(core_file, "r", encoding="utf-8") as f:
                core_text = f.read()

        # 情境层缓存 1 小时
        context_built_at = datetime.fromisoformat(meta.get("context_built_at", "2000-01-01"))
        if (now - context_built_at).total_seconds() < 3600 and os.path.exists(context_file):
            with open(context_file, "r", encoding="utf-8") as f:
                context_text = f.read()

    # 构建缺失的层
    meta_updated = False
    now = datetime.now()

    if core_text is None:
        core_text, _ = await build_core_layer()
        with open(core_file, "w", encoding="utf-8") as f:
            f.write(core_text)
        meta_updated = True

    if context_text is None:
        context_text, _ = await build_context_layer()
        with open(context_file, "w", encoding="utf-8") as f:
            f.write(context_text)
        meta_updated = True

    # 更新 meta
    if meta_updated or not os.path.exists(meta_file):
        meta = {}
        if os.path.exists(meta_file):
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

        if core_text is not None and (not meta.get("core_built_at") or meta_updated):
            meta["core_built_at"] = now.isoformat()
        if context_text is not None and (not meta.get("context_built_at") or meta_updated):
            meta["context_built_at"] = now.isoformat()

        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    # 合并返回
    parts = []
    if core_text:
        parts.append(core_text)
    if context_text:
        parts.append(context_text)
    return "\n\n".join(parts)


async def get_or_build_snapshot_layers() -> SnapshotLayers:
    """获取双层快照（新接口），分别返回核心层和情境层

    用于 chat.py 中将核心层和情境层分别注入 System Prompt，
    确保核心层在最前面，命中 KV Cache。
    """
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    core_file = os.path.join(SNAPSHOT_DIR, "core_layer.txt")
    context_file = os.path.join(SNAPSHOT_DIR, "context_layer.txt")
    meta_file = os.path.join(SNAPSHOT_DIR, "snapshot_meta.json")

    result = SnapshotLayers()
    core_text = None
    context_text = None

    # 尝试从缓存加载
    if os.path.exists(meta_file):
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        now = datetime.now()

        core_built_at = datetime.fromisoformat(meta.get("core_built_at", "2000-01-01"))
        if (now - core_built_at).total_seconds() < 21600 and os.path.exists(core_file):
            with open(core_file, "r", encoding="utf-8") as f:
                core_text = f.read()

        context_built_at = datetime.fromisoformat(meta.get("context_built_at", "2000-01-01"))
        if (now - context_built_at).total_seconds() < 3600 and os.path.exists(context_file):
            with open(context_file, "r", encoding="utf-8") as f:
                context_text = f.read()

    # 构建缺失的层
    meta_updated = False
    now = datetime.now()

    if core_text is None:
        core_text, core_tokens = await build_core_layer()
        result.core_text = core_text
        result.core_tokens = core_tokens
        with open(core_file, "w", encoding="utf-8") as f:
            f.write(core_text)
        meta_updated = True
    else:
        result.core_text = core_text
        result.core_tokens = count_tokens(core_text)

    if context_text is None:
        context_text, context_tokens = await build_context_layer()
        result.context_text = context_text
        result.context_tokens = context_tokens
        with open(context_file, "w", encoding="utf-8") as f:
            f.write(context_text)
        meta_updated = True
    else:
        result.context_text = context_text
        result.context_tokens = count_tokens(context_text)

    # 更新 meta
    if meta_updated or not os.path.exists(meta_file):
        meta = {}
        if os.path.exists(meta_file):
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

        if core_text is not None and meta_updated:
            meta["core_built_at"] = now.isoformat()
        if context_text is not None and meta_updated:
            meta["context_built_at"] = now.isoformat()

        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    result.sections = [
        {"name": "核心层", "token_count": result.core_tokens, "limit": CORE_TOKEN_LIMIT},
        {"name": "情境层", "token_count": result.context_tokens, "limit": CONTEXT_TOKEN_LIMIT},
    ]

    return result


def invalidate_snapshot():
    """标记快照为过期（删除 meta 文件，下次请求时重新构建）"""
    meta_file = os.path.join(SNAPSHOT_DIR, "snapshot_meta.json")
    if os.path.exists(meta_file):
        os.remove(meta_file)


async def get_snapshot_stats() -> dict:
    """获取快照统计信息（token数、各section）"""
    layers = await build_snapshot_layers()
    return {
        "core_tokens": layers.core_tokens,
        "context_tokens": layers.context_tokens,
        "total_tokens": layers.total_tokens,
        "core_limit": CORE_TOKEN_LIMIT,
        "context_limit": CONTEXT_TOKEN_LIMIT,
        "total_limit": TOTAL_TOKEN_LIMIT,
        "within_limit": layers.total_tokens <= TOTAL_TOKEN_LIMIT,
        "sections": layers.sections,
    }


async def export_snapshot(filepath: str) -> dict:
    """导出快照到指定文件，返回统计信息"""
    layers = await build_snapshot_layers()
    stats = await get_snapshot_stats()

    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(layers.full_text)

    stats["filepath"] = filepath
    return stats
