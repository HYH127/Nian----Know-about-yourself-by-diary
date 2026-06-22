from __future__ import annotations

import json
import os


class MemoryManager:
    def __init__(self):
        self.memory_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            "memory",
        )
        os.makedirs(self.memory_dir, exist_ok=True)

    async def get_mid_term_memory(self, session_id: str) -> str:
        """获取中期记忆（近期对话摘要）"""
        summary_file = os.path.join(self.memory_dir, f"{session_id}_summary.json")
        if os.path.exists(summary_file):
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("summary", "")
        return ""


memory_manager = MemoryManager()
