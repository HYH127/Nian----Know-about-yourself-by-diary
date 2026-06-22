SIGNAL_EXTRACTION_V2_PROMPT = """从以下文本中提取行为信号。要求精确、结构化。

提取以下8类信号，每类有特定输出格式：

1. 情绪信号：识别情绪倾向、强度、关键词。注意否定表达（"不开心""并不高兴"）和转折（"虽然累了，但开心"）。识别委婉表达（"心里有点堵""提不起劲"）。
   {{"type": "emotion", "sub_type": "positive|negative|mixed|neutral", "content": "情绪摘要", "evidence": "原文依据", "emotion_detail": {{"emotion": "positive|negative|mixed|neutral", "intensity": 7, "keywords": ["关键词"]}}}}

2. 决策信号：识别决定、犹豫、后悔。区分确定性（high/medium/low）。识别隐含决策（"我想了很久，还是……""算了，就这样吧"）。区分"决定"是动作还是状态（"还没决定"不算决策）。
   {{"type": "decision", "sub_type": "decision|hesitation|regret", "content": "决策摘要", "evidence": "原文依据", "decision_detail": {{"certainty": "high|medium|low", "options": ["选项A", "选项B"]}}}}

3. 消费信号：提取金额、商品、模糊表达。中文数字转阿拉伯数字（"三百五十"→350）。处理模糊表达（"大概两百""两千多"）。识别无动词情况（"咖啡30元"）。
   {{"type": "expense", "sub_type": "shopping", "content": "消费摘要", "evidence": "原文依据", "expense_detail": {{"amount": 350, "raw_amount": "原文金额", "item": "商品名", "is_estimated": false}}}}

4. 媒体信号：识别书影音作品，包括无书名号的口语表达（"刚刷完狂飙""有个电影叫……"）。
   {{"type": "media", "sub_type": "completed|ongoing|evaluated|reference", "content": "媒体摘要", "evidence": "原文依据", "media_info": {{"title": "作品名", "media_type": "book|movie|tv_series|music|podcast", "action": "watched|reading|listening"}}}}

5. 反思信号：识别反思、领悟、体会。覆盖同义词（"认识到""悟了""体会到""感触"）。
   {{"type": "reflection", "sub_type": "insight", "content": "反思摘要", "evidence": "原文依据"}}

6. 关系信号：识别人际互动和关系变化。区分关系类型（同事/朋友/家人/伴侣）。判断情感倾向。识别抽象关系变化（"我们关系更近了""疏远了"）。
   {{"type": "relationship", "sub_type": "interaction|change", "content": "关系摘要", "evidence": "原文依据", "relationship_detail": {{"relation_type": "friend|family|colleague|partner", "sentiment": "positive|negative|neutral", "event": "事件描述"}}}}

7. 目标信号：识别目标计划。区分短期目标和长期愿望。判断完成状态。
   {{"type": "goal", "sub_type": "intention|plan|achieved", "content": "目标摘要", "evidence": "原文依据", "goal_detail": {{"timeframe": "short|long", "status": "planned|in_progress|achieved"}}}}

8. 犹豫信号：识别纠结、两难。提取选项对（"我既想……又怕……"）。
   {{"type": "hesitation", "sub_type": "dilemma", "content": "犹豫摘要", "evidence": "原文依据", "hesitation_detail": {{"options": ["选项A", "选项B"]}}}}

输出 JSON 数组。只提取文本中明确存在的信号，不要臆测。如果某类信号不存在则不输出。
每条信号必须包含 type, sub_type, content, evidence 字段，对应 detail 字段按类型填写。

文本内容：
{text}

数据源类型：{source_type}
"""
