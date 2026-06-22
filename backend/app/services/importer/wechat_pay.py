from __future__ import annotations

import asyncio
import csv
import io
import uuid
from datetime import datetime

import structlog

from app.services.importer.consumption_base import (
    extract_consumption_signals,
    create_consumption_timeline_event,
    aggregate_consumption_stats,
)
from app.services.knowledge import extract_knowledge_from_import

logger = structlog.get_logger()


async def import_wechat_pay_csv(csv_content: str, import_batch_id: str | None = None) -> dict:
    """
    解析微信支付 CSV 并提取消费信号
    CSV 字段：交易时间,交易对方,商品,金额,支付方式,当前状态
    """
    if not import_batch_id:
        import_batch_id = uuid.uuid4().hex

    reader = csv.DictReader(io.StringIO(csv_content))
    records = []

    for row in reader:
        if "成功" not in row.get("当前状态", ""):
            continue

        try:
            amount = float(row.get("金额", 0))
        except (ValueError, TypeError):
            amount = 0

        if amount <= 0:
            continue

        records.append({
            "timestamp": row.get("交易时间", ""),
            "merchant": row.get("交易对方", ""),
            "description": row.get("商品", ""),
            "amount": amount,
            "type": "expense",
            "source": "wechat_pay",
            "batch_id": import_batch_id,
        })

    signals = extract_consumption_signals(records)

    for signal in signals:
        await create_consumption_timeline_event(signal, import_batch_id)

    await aggregate_consumption_stats(signals, import_batch_id)

    logger.info(
        "微信支付CSV导入完成",
        import_batch_id=import_batch_id,
        imported_count=len(records),
    )

    asyncio.create_task(extract_knowledge_from_import(
        {"title": f"微信支付消费记录 {datetime.now().strftime('%Y-%m')}", "type": "consumption", "summary": f"微信支付消费记录，共 {len(records)} 条"},
        "wechat_pay"
    ))

    return {"import_batch_id": import_batch_id, "imported_count": len(records)}
