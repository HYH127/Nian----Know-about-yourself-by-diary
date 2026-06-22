PROFILE_EXTRACTION_PROMPT = """基于以下行为信号，提取或更新用户的画像片段。

输出 JSON 数组，每个画像片段：
{{
  "content": "画像内容描述（≤200字，自然语言）",
  "confidence": "explicit|frequent|implied|inferred",
  "evidence": ["证据1", "证据2"],
  "trigger": "触发条件（情境行为相关时必填）",
  "behavior": "行为表现（情境行为相关时必填）"
}}

置信度规则（严格遵守）：
- explicit：用户明确表述（如"我是程序员"、"我每天6点起床"）
- frequent：10+独立信号，来自2+数据源
- implied：5-9个信号，模式清晰
- inferred：2-4个信号，待观察

注意事项：
1. 同一方面的画像可以产生多个片段（不同方面或情境）
2. 情境行为相关的画像必须填写 trigger 和 behavior 字段
3. 不要编造没有信号支撑的画像
4. 如果已有画像与新信号一致，可以输出更新版本（内容更丰富、置信度更高）
5. 如果已有画像与新信号矛盾，输出新版本并标注更高置信度
6. evidence 中每条证据必须包含日期信息（格式：[YYYY-MM-DD]），例如 "[2025-10-17] 出门跑步3.8公里"，不要使用模糊时间标签如"上午"、"周五"、"今天"等

已有画像：
{existing_profiles}

新信号：
{signals}
"""

DECISION_SUB_PROFILE_PROMPT = """基于以下决策信号，提取用户的决策模式画像。

四个方面：
1. decision_speed：决策速度。基于首次提及到最终决定的间隔天数均值判断。
   - 输出格式："快（<1天）/中等（1-7天）/慢（>7天）"，附具体均值
2. decision_basis：决策依据。判断主要依据类型。
   - 分类：理性分析/直觉感受/他人建议/混合型
   - 附依据描述
3. decision_regret_rate：决策后悔率。
   - 计算：后悔表述次数 / 决策事件总数
   - 输出格式："低（<20%）/中（20-50%）/高（>50%）"，附具体比率
4. decision_trigger：决策触发模式。从决策前的日记/对话内容中提取共同触发模式。
   - 输出格式：触发模式描述

输出 JSON 数组，每个方面一个片段：
{{
  "content": "决策模式画像描述（≤200字）",
  "confidence": "explicit|frequent|implied|inferred",
  "evidence": ["证据1", "证据2"]
}}

决策信号：
{decision_signals}

决策事件统计：
- 犹豫表述次数：{hesitation_count}
- 决定表述次数：{decision_count}
- 后悔表述次数：{regret_count}
- 决策事件总数：{total_decisions}
"""
