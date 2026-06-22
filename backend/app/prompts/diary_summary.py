DIARY_SUMMARY_PROMPT = """为以下日记生成摘要和标签。

输出 JSON：
{{
  "summary": "约{target_chars}字的摘要（不超过{max_chars}字）",
  "tags": ["标签1", "标签2", "标签3"],
  "sentiment_score": 0.5,
  "emotional_keywords": ["关键词1", "关键词2"]
}}

摘要要求：根据日记长度动态调整摘要长度，短日记保持简洁，长日记要有足够信息量覆盖主要内容和情感变化。
sentiment_score 范围 -1.0 到 1.0，-1.0 为极度消极，1.0 为极度积极。

日记内容：
{content}

日记日期：{date}
"""
