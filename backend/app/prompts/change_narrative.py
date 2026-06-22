CHANGE_NARRATIVE_PROMPT = """基于以下画像变化信息，生成一段自然语言的变化描述。

变化类型：{change_type}
旧画像：{old_content}
新信号：{new_evidence}

要求：
1. 用温和、客观的语气描述变化
2. 指出变化的时间跨度
3. 不做价值判断
4. 50字以内

输出变化描述文本。
"""
