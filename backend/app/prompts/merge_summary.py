MERGE_SUMMARY_PROMPT = """将以下新旧两段摘要合并为一段，保留所有关键信息，去除重复。

旧摘要：{old_summary}
新摘要：{new_summary}

输出合并后的摘要文本。
"""
