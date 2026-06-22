PERSONALITY_DISTILLATION_PROMPT = """基于以下画像片段，蒸馏出用户在特定关系情境下的人格面。

关系情境：{relationship_context}
相关联系人：{contact_name}

画像片段：
{profile_fragments}

输出 JSON：
{{
  "personality_facet": "关系特定人格面描述（200字以内）",
  "communication_style": "沟通风格",
  "emotional_tendency": "情感倾向",
  "behavioral_pattern": "行为模式",
  "key_traits": ["核心特质1", "核心特质2", "核心特质3"]
}}
"""
