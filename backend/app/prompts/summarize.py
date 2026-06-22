SUMMARIZE_PROMPT = """将以下对话历史压缩为简洁的摘要，保留关键信息和行为信号。

输出：
{{
  "summary": "摘要内容",
  "key_signals": ["关键行为信号1", "关键行为信号2"],
  "topics": ["话题1", "话题2"],
  "mentioned_contacts": ["提及的联系人"],
  "mentioned_media": ["提及的媒体作品"]
}}

对话历史：
{messages}
"""
