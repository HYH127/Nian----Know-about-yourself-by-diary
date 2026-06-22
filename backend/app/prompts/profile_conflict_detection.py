PROFILE_CONFLICT_DETECTION_PROMPT = """判断以下两个画像描述是否矛盾冲突。

旧画像：{old_content}

新画像：{new_content}

如果两者描述的是相反、矛盾、互斥的特征，回答"是"；如果两者可以共存或互补，回答"否"。

只回答"是"或"否"。
"""
