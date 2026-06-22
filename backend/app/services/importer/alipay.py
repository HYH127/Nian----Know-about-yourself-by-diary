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


async def import_alipay_csv(csv_content: str, import_batch_id: str | None = None) -> dict:
    """
    解析支付宝 CSV 并提取消费信号
    CSV 字段：交易时间,交易对方,商品说明,金额,收支类型,交易状态
    """
    if not import_batch_id:
        import_batch_id = uuid.uuid4().hex

    reader = csv.DictReader(io.StringIO(csv_content))
    records = []

    for row in reader:
        if row.get("收支类型", "") == "支出" and "成功" in row.get("交易状态", ""):
            try:
                amount = float(row.get("金额", 0))
            except (ValueError, TypeError):
                amount = 0

            records.append({
                "timestamp": row.get("交易时间", ""),
                "merchant": row.get("交易对方", ""),
                "description": row.get("商品说明", ""),
                "amount": amount,
                "type": "expense",
                "source": "alipay",
                "batch_id": import_batch_id,
            })

    signals = extract_consumption_signals(records)

    for signal in signals:
        await create_consumption_timeline_event(signal, import_batch_id)

    await aggregate_consumption_stats(signals, import_batch_id)

    logger.info(
        "支付宝CSV导入完成",
        import_batch_id=import_batch_id,
        imported_count=len(records),
    )

    asyncio.create_task(extract_knowledge_from_import(
        {"title": f"支付宝消费记录 {datetime.now().strftime('%Y-%m')}", "type": "consumption", "summary": f"支付宝消费记录，共 {len(records)} 条"},
        "alipay"
    ))

    return {"import_batch_id": import_batch_id, "imported_count": len(records)}
