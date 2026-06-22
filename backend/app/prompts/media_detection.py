MEDIA_DETECTION_PROMPT = """从以下文本中检测提及的媒体作品（书籍、电影、电视剧、音乐、播客）。

输出 JSON 数组：
[
  {{
    "title": "作品名称",
    "media_type": "book|movie|tv_series|music|podcast",
    "confidence": "explicit|implied",
    "evidence": "原文依据"
  }}
]

文本内容：
{text}
"""
