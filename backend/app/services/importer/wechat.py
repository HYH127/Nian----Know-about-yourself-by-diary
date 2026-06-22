from __future__ import annotations

import asyncio
import uuid
import hashlib
import base64
import json
from datetime import datetime
from collections import Counter, defaultdict
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.database import get_connection
from app.services.knowledge import extract_knowledge_from_import

_ENCRYPTION_KEY: Optional[bytes] = None


def _get_encryption_key() -> bytes:
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is None:
        from app.config import settings
        password = settings.llm.api_key.encode() or b"niannian-default-key"
        salt = b"niannian-wechat-tier2"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        _ENCRYPTION_KEY = key
    return _ENCRYPTION_KEY


def _encrypt(text: str) -> str:
    f = Fernet(_get_encryption_key())
    return f.encrypt(text.encode("utf-8")).decode("ascii")


def _decrypt(cipher_text: str) -> str:
    f = Fernet(_get_encryption_key())
    return f.decrypt(cipher_text.encode("ascii")).decode("utf-8")


async def import_wechat_stats(
    contact_name: str,
    messages: list[dict],
    privacy_tier: str = "tier1",
    import_batch_id: str | None = None,
) -> dict:
    if not import_batch_id:
        import_batch_id = uuid.uuid4().hex

    imported = 0
    async with get_connection() as db:
        for msg in messages:
            msg_id = uuid.uuid4().hex
            cursor = await db.execute(
                "SELECT id FROM wechat_message_stats WHERE message_hash = ?",
                (msg["message_hash"],),
            )
            if await cursor.fetchone():
                continue

            await db.execute(
                """INSERT INTO wechat_message_stats
                (id, contact_name, sender, timestamp, word_count, has_emoji, has_image, has_voice,
                 sentiment_score, topic_category, message_hash, response_delay_seconds, import_batch_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    msg_id,
                    contact_name,
                    msg["sender"],
                    msg["timestamp"],
                    msg.get("word_count", 0),
                    msg.get("has_emoji", False),
                    msg.get("has_image", False),
                    msg.get("has_voice", False),
                    msg.get("sentiment_score", 0),
                    msg.get("topic_category", ""),
                    msg["message_hash"],
                    msg.get("response_delay_seconds"),
                    import_batch_id,
                ),
            )
            imported += 1

        await db.execute(
            """INSERT OR REPLACE INTO wechat_privacy_tiers
            (contact_name, privacy_tier, tier2_authorized, tier3_authorized, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))""",
            (
                contact_name,
                privacy_tier,
                privacy_tier in ("tier2", "tier3"),
                privacy_tier == "tier3",
            ),
        )

        await db.commit()

    asyncio.create_task(extract_knowledge_from_import(
        {"title": contact_name, "type": "contact", "summary": f"微信联系人 {contact_name}，共 {len(messages)} 条消息"},
        "wechat"
    ))

    return {"import_batch_id": import_batch_id, "imported_count": imported}

async def import_wechat_tier2(
    contact_name: str,
    messages: list[dict],
    import_batch_id: str | None = None,
) -> dict:
    if not import_batch_id:
        import_batch_id = uuid.uuid4().hex

    imported = 0
    async with get_connection() as db:
        for msg in messages:
            msg_id = uuid.uuid4().hex
            cursor = await db.execute(
                "SELECT id FROM wechat_message_stats WHERE message_hash = ?",
                (msg["message_hash"],),
            )
            if await cursor.fetchone():
                continue

            await db.execute(
                """INSERT INTO wechat_message_stats
                (id, contact_name, sender, timestamp, word_count, has_emoji, has_image, has_voice,
                 sentiment_score, topic_category, message_hash, response_delay_seconds, import_batch_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    msg_id,
                    contact_name,
                    msg["sender"],
                    msg["timestamp"],
                    msg.get("word_count", 0),
                    msg.get("has_emoji", False),
                    msg.get("has_image", False),
                    msg.get("has_voice", False),
                    msg.get("sentiment_score", 0),
                    msg.get("topic_category", ""),
                    msg["message_hash"],
                    msg.get("response_delay_seconds"),
                    import_batch_id,
                ),
            )

            content = msg.get("content", "")
            if content:
                encrypted = _encrypt(content)
                await db.execute(
                    """INSERT INTO wechat_tier2_messages
                    (id, message_hash, contact_name, sender, timestamp, encrypted_content, import_batch_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uuid.uuid4().hex,
                        msg["message_hash"],
                        contact_name,
                        msg["sender"],
                        msg["timestamp"],
                        encrypted,
                        import_batch_id,
                    ),
                )

            imported += 1

        await db.execute(
            """INSERT OR REPLACE INTO wechat_privacy_tiers
            (contact_name, privacy_tier, tier2_authorized, tier3_authorized, updated_at)
            VALUES (?, 'tier2', 1, 0, datetime('now'))""",
            (contact_name,),
        )

        await db.commit()

    asyncio.create_task(extract_knowledge_from_import(
        {"title": contact_name, "type": "contact", "summary": f"微信联系人 {contact_name}，共 {len(messages)} 条消息"},
        "wechat"
    ))

    return {"import_batch_id": import_batch_id, "imported_count": imported}

async def import_wechat_tier3(
    contact_name: str,
    messages: list[dict],
    import_batch_id: str | None = None,
) -> dict:
    if not import_batch_id:
        import_batch_id = uuid.uuid4().hex

    imported = 0
    async with get_connection() as db:
        for msg in messages:
            msg_id = uuid.uuid4().hex
            cursor = await db.execute(
                "SELECT id FROM wechat_message_stats WHERE message_hash = ?",
                (msg["message_hash"],),
            )
            if await cursor.fetchone():
                continue

            await db.execute(
                """INSERT INTO wechat_message_stats
                (id, contact_name, sender, timestamp, word_count, has_emoji, has_image, has_voice,
                 sentiment_score, topic_category, message_hash, response_delay_seconds, import_batch_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    msg_id,
                    contact_name,
                    msg["sender"],
                    msg["timestamp"],
                    msg.get("word_count", 0),
                    msg.get("has_emoji", False),
                    msg.get("has_image", False),
                    msg.get("has_voice", False),
                    msg.get("sentiment_score", 0),
                    msg.get("topic_category", ""),
                    msg["message_hash"],
                    msg.get("response_delay_seconds"),
                    import_batch_id,
                ),
            )

            content = msg.get("content", "")
            if content:
                encrypted = _encrypt(content)
                await db.execute(
                    """INSERT INTO wechat_tier3_messages
                    (id, message_hash, contact_name, sender, timestamp, encrypted_content, import_batch_id, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now', '+24 hours'))""",
                    (
                        uuid.uuid4().hex,
                        msg["message_hash"],
                        contact_name,
                        msg["sender"],
                        msg["timestamp"],
                        encrypted,
                        import_batch_id,
                    ),
                )

            imported += 1

        await db.execute(
            """INSERT OR REPLACE INTO wechat_privacy_tiers
            (contact_name, privacy_tier, tier2_authorized, tier3_authorized, tier3_expires_at, updated_at)
            VALUES (?, 'tier3', 1, 1, datetime('now', '+24 hours'), datetime('now'))""",
            (contact_name,),
        )

        await db.commit()

    asyncio.create_task(extract_knowledge_from_import(
        {"title": contact_name, "type": "contact", "summary": f"微信联系人 {contact_name}，共 {len(messages)} 条消息"},
        "wechat"
    ))

    return {"import_batch_id": import_batch_id, "imported_count": imported}


async def extract_wechat_signals(contact_name: str) -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT sender, timestamp, word_count, has_emoji, has_image, has_voice, "
            "sentiment_score, topic_category, response_delay_seconds "
            "FROM wechat_message_stats WHERE contact_name = ? ORDER BY timestamp",
            (contact_name,),
        )
        rows = await cursor.fetchall()

    if not rows:
        return []

    signals: list[dict] = []

    sender_counts: Counter = Counter()
    sender_word_counts: defaultdict = defaultdict(list)
    sender_sentiments: defaultdict = defaultdict(list)
    sender_response_delays: defaultdict = defaultdict(list)
    topic_counts: Counter = Counter()
    hourly_counts: Counter = Counter()

    for row in rows:
        sender = row["sender"]
        sender_counts[sender] += 1
        sender_word_counts[sender].append(row["word_count"] or 0)
        sender_sentiments[sender].append(row["sentiment_score"] or 0)
        if row["response_delay_seconds"] is not None:
            sender_response_delays[sender].append(row["response_delay_seconds"])
        if row["topic_category"]:
            topic_counts[row["topic_category"]] += 1
        try:
            ts = row["timestamp"]
            if ts and len(ts) >= 13:
                hour = int(ts[11:13])
                hourly_counts[hour] += 1
        except (ValueError, IndexError):
            pass

    total = sum(sender_counts.values())
    for sender, count in sender_counts.items():
        ratio = count / total if total > 0 else 0
        avg_words = sum(sender_word_counts[sender]) / len(sender_word_counts[sender]) if sender_word_counts[sender] else 0
        avg_sentiment = sum(sender_sentiments[sender]) / len(sender_sentiments[sender]) if sender_sentiments[sender] else 0
        avg_delay = sum(sender_response_delays[sender]) / len(sender_response_delays[sender]) if sender_response_delays[sender] else None

        signals.append({
            "type": "interaction_frequency",
            "content": f"{sender} 发送了 {count} 条消息（占比 {ratio:.1%}），平均字数 {avg_words:.1f}",
            "evidence": f"sender={sender}, count={count}, ratio={ratio:.2f}, avg_words={avg_words:.1f}",
            "sub_type": "frequency",
        })

        if avg_delay is not None:
            signals.append({
                "type": "response_pattern",
                "content": f"{sender} 平均回复时间 {avg_delay:.0f} 秒",
                "evidence": f"sender={sender}, avg_delay={avg_delay:.1f}s",
                "sub_type": "response_speed",
            })

        if avg_sentiment != 0:
            direction = "偏正面" if avg_sentiment > 0 else "偏负面"
            signals.append({
                "type": "sentiment_expression",
                "content": f"{sender} 情感表达{direction}（均值 {avg_sentiment:.2f}）",
                "evidence": f"sender={sender}, avg_sentiment={avg_sentiment:.2f}",
                "sub_type": "sentiment_tendency",
            })

    for topic, count in topic_counts.most_common(5):
        ratio = count / total if total > 0 else 0
        signals.append({
            "type": "topic_distribution",
            "content": f"话题「{topic}」出现 {count} 次（占比 {ratio:.1%}）",
            "evidence": f"topic={topic}, count={count}, ratio={ratio:.2f}",
            "sub_type": "topic",
        })

    if hourly_counts:
        peak_hour = hourly_counts.most_common(1)[0][0]
        signals.append({
            "type": "temporal_pattern",
            "content": f"活跃高峰时段为 {peak_hour}:00",
            "evidence": f"peak_hour={peak_hour}, distribution={dict(hourly_counts)}",
            "sub_type": "active_hours",
        })

    senders = list(sender_counts.keys())
    if len(senders) >= 2:
        for i in range(len(senders)):
            for j in range(i + 1, len(senders)):
                s1, s2 = senders[i], senders[j]
                c1, c2 = sender_counts[s1], sender_counts[s2]
                imbalance = abs(c1 - c2) / max(c1, c2) if max(c1, c2) > 0 else 0
                if imbalance > 0.3:
                    dominant = s1 if c1 > c2 else s2
                    signals.append({
                        "type": "interaction_imbalance",
                        "content": f"{s1} 与 {s2} 互动不平衡，{dominant} 更活跃（不平衡度 {imbalance:.1%}）",
                        "evidence": f"s1={s1}({c1}), s2={s2}({c2}), imbalance={imbalance:.2f}",
                        "sub_type": "imbalance",
                    })

    return signals


async def get_import_batches() -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT import_batch_id as id, contact_name, COUNT(*) as message_count, "
            "MIN(timestamp) as first_message, MAX(timestamp) as last_message, "
            "MIN(created_at) as created_at "
            "FROM wechat_message_stats GROUP BY import_batch_id ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        privacy_tier = "tier1"
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT privacy_tier FROM wechat_privacy_tiers WHERE contact_name = ?",
                (row["contact_name"],),
            )
            tier_row = await cursor.fetchone()
            if tier_row:
                privacy_tier = tier_row["privacy_tier"]

        results.append({
            "id": row["id"],
            "contact_name": row["contact_name"],
            "message_count": row["message_count"],
            "privacy_tier": privacy_tier,
            "created_at": row["created_at"],
        })

    return results


async def delete_import_batch(batch_id: str) -> bool:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT contact_name FROM wechat_message_stats WHERE import_batch_id = ? LIMIT 1",
            (batch_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return False

        contact_name = row["contact_name"]

        await db.execute(
            "DELETE FROM wechat_message_stats WHERE import_batch_id = ?",
            (batch_id,),
        )
        await db.execute(
            "DELETE FROM wechat_tier2_messages WHERE import_batch_id = ?",
            (batch_id,),
        )
        await db.execute(
            "DELETE FROM wechat_tier3_messages WHERE import_batch_id = ?",
            (batch_id,),
        )

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM wechat_message_stats WHERE contact_name = ?",
            (contact_name,),
        )
        remaining = await cursor.fetchone()
        if remaining and remaining["cnt"] == 0:
            await db.execute(
                "DELETE FROM wechat_privacy_tiers WHERE contact_name = ?",
                (contact_name,),
            )

        await db.commit()

    return True


async def get_privacy_info(contact_name: str) -> dict | None:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT contact_name, privacy_tier, tier2_authorized, tier3_authorized, tier3_expires_at "
            "FROM wechat_privacy_tiers WHERE contact_name = ?",
            (contact_name,),
        )
        row = await cursor.fetchone()

    if not row:
        return None

    return {
        "contact_name": row["contact_name"],
        "privacy_tier": row["privacy_tier"],
        "tier2_authorized": bool(row["tier2_authorized"]),
        "tier3_authorized": bool(row["tier3_authorized"]),
        "tier3_expires_at": row["tier3_expires_at"],
    }


async def update_privacy(
    contact_name: str,
    privacy_tier: str,
    tier2_authorized: bool = False,
    tier3_authorized: bool = False,
) -> dict:
    async with get_connection() as db:
        if privacy_tier == "tier1" and not tier2_authorized:
            await db.execute(
                "DELETE FROM wechat_tier2_messages WHERE contact_name = ?",
                (contact_name,),
            )
            await db.execute(
                "DELETE FROM wechat_tier3_messages WHERE contact_name = ?",
                (contact_name,),
            )

        if not tier3_authorized:
            await db.execute(
                "DELETE FROM wechat_tier3_messages WHERE contact_name = ?",
                (contact_name,),
            )

        await db.execute(
            """INSERT OR REPLACE INTO wechat_privacy_tiers
            (contact_name, privacy_tier, tier2_authorized, tier3_authorized, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))""",
            (contact_name, privacy_tier, int(tier2_authorized), int(tier3_authorized)),
        )

        await db.commit()

    return await get_privacy_info(contact_name) or {}


async def cleanup_expired_tier3() -> int:
    async with get_connection() as db:
        cursor = await db.execute(
            "DELETE FROM wechat_tier3_messages WHERE expires_at IS NOT NULL AND expires_at < datetime('now')"
        )
        deleted = cursor.rowcount
        await db.commit()

    return deleted


async def analyze_tier2_data(contact_name: str) -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT message_hash, sender, timestamp, encrypted_content FROM wechat_tier2_messages "
            "WHERE contact_name = ? ORDER BY timestamp",
            (contact_name,),
        )
        rows = await cursor.fetchall()

    if not rows:
        return []

    signals: list[dict] = []
    topic_content: defaultdict = defaultdict(list)
    sender_style: defaultdict = defaultdict(list)

    for row in rows:
        try:
            content = _decrypt(row["encrypted_content"])
        except Exception:
            continue

        sender = row["sender"]
        sender_style[sender].append(content)

        from app.services.signal_extractor import detect_decision_signals, detect_media_signals
        decision_sigs = detect_decision_signals(content)
        media_sigs = detect_media_signals(content)
        for sig in decision_sigs + media_sigs:
            signals.append({
                "type": sig.type,
                "content": sig.content,
                "evidence": sig.evidence,
                "sub_type": sig.sub_type,
                "source": "tier2",
            })

    for sender, contents in sender_style.items():
        total_chars = sum(len(c) for c in contents)
        avg_len = total_chars / len(contents) if contents else 0
        emoji_count = sum(1 for c in contents for ch in c if ord(ch) > 0x1F000)
        signals.append({
            "type": "language_style",
            "content": f"{sender} 语言风格：平均消息长度 {avg_len:.0f} 字，emoji 使用 {emoji_count} 次",
            "evidence": f"sender={sender}, avg_len={avg_len:.0f}, emoji_count={emoji_count}",
            "sub_type": "style_analysis",
            "source": "tier2",
        })

    return signals


async def analyze_tier3_data(contact_name: str) -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT message_hash, sender, timestamp, encrypted_content FROM wechat_tier3_messages "
            "WHERE contact_name = ? ORDER BY timestamp",
            (contact_name,),
        )
        rows = await cursor.fetchall()

    if not rows:
        return []

    signals: list[dict] = []

    for row in rows:
        try:
            content = _decrypt(row["encrypted_content"])
        except Exception:
            continue

        from app.services.signal_extractor import extract_signals
        extracted = await extract_signals(content, "wechat_tier3", row["message_hash"])
        for sig in extracted:
            signals.append({
                "type": sig.type,
                "content": sig.content,
                "evidence": sig.evidence,
                "sub_type": sig.sub_type,
                "source": "tier3",
            })

    await cleanup_tier3_by_contact(contact_name)

    return signals


async def cleanup_tier3_by_contact(contact_name: str) -> int:
    async with get_connection() as db:
        cursor = await db.execute(
            "DELETE FROM wechat_tier3_messages WHERE contact_name = ?",
            (contact_name,),
        )
        deleted = cursor.rowcount

        await db.execute(
            "UPDATE wechat_privacy_tiers SET tier3_authorized = 0 WHERE contact_name = ?",
            (contact_name,),
        )
        await db.commit()

    return deleted
