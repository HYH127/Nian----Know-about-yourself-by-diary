KNOWLEDGE_EXTRACTION_PROMPT = """从以下搜索结果中结构化提取媒体作品信息。

作品名称：{title}
媒体类型：{media_type}

搜索结果：
{search_results}

输出 JSON：
{{
  "title": "作品名称",
  "type": "book|movie|tv_series|music|podcast",
  "summary": "200字以内的摘要",
  "genres": "类型1,类型2",
  "key_characters": "角色1,角色2",
  "themes": "主题1,主题2",
  "creator": "作者/导演/歌手",
  "year": 2024,
  "source_url": "来源URL"
}}
"""

DEEP_KNOWLEDGE_EXTRACTION_PROMPT = """从以下搜索结果中提取深度知识信息。

作品名称：{title}
基础信息：{basic_info}

搜索结果：
{search_results}

输出 JSON：
{{
  "plot_detail": "详细剧情/内容描述（500字以内）",
  "cultural_impact": "文化影响（200字以内）",
  "reviews_summary": "评价摘要（200字以内）",
  "similar_works": "相似作品1,相似作品2,相似作品3"
}}
"""
