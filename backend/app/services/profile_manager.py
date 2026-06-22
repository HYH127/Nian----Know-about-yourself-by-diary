from __future__ import annotations

import json

import structlog

from app.config import settings
from app.prompts.personality_distillation import PERSONALITY_DISTILLATION_PROMPT
from app.services.vector_store import vector_store
from app.utils.llm import chat_completion

logger = structlog.get_logger()


class ProfileManager:
    """Agentic 画像生命周期管理"""

    async def distill_personality(
        self, contact_name: str, relationship_type: str = ""
    ) -> dict:
        """从画像片段中蒸馏出关系特定人格面"""
        relevant_profiles = await vector_store.search_profiles(
            query_vector=[0.0] * settings.llm.embedding_dimensions,
            limit=20,
            filter_dict={"is_active": True},
        )

        social_profiles = relevant_profiles

        if not social_profiles:
            return {
                "personality_facet": "暂无足够数据",
                "communication_style": "",
                "emotional_tendency": "",
                "behavioral_pattern": "",
                "key_traits": [],
            }

        fragments_text = "\n".join(
            [p['content'] for p in social_profiles]
        )

        response = await chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": PERSONALITY_DISTILLATION_PROMPT.format(
                        relationship_context=relationship_type or "日常交往",
                        contact_name=contact_name,
                        profile_fragments=fragments_text,
                    ),
                }
            ],
            temperature=0.3,
            purpose="画像更新",
        )

        try:
            return json.loads(response)
        except (json.JSONDecodeError, TypeError):
            return {
                "personality_facet": response,
                "communication_style": "",
                "emotional_tendency": "",
                "behavioral_pattern": "",
                "key_traits": [],
            }


profile_manager = ProfileManager()
