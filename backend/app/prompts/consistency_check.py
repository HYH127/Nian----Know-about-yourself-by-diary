"""Prompts for consistency checking and quality evaluation."""

ENTITY_CONSISTENCY_PROMPT = """检查以下新编译的实体描述与相关实体描述是否存在矛盾。

新实体：{entity_tag}
新描述：{new_truth}

相关实体描述：
{related_truths}

请判断是否存在矛盾。注意区分以下情况：
1. 真正矛盾：对同一事实的描述互相排斥（如"是同事" vs "是陌生人"）
2. 时间变化：描述反映了关系随时间的变化（如"是同事" vs "是前同事"），这不算矛盾，应标记为auto_resolve
3. 互补描述：从不同角度描述同一事物，可以共存

输出JSON格式：
{{"has_conflict": true, "conflicts": [{{"entity": "实体名", "description": "矛盾描述", "old_statement": "旧描述", "new_statement": "新描述"}}], "suggested_action": "none"}}
suggested_action取值：none（无冲突）、flag（记录但不处理）、auto_resolve（时间变化类可自动解决）、user_confirm（需要用户确认）

如果无矛盾，输出：
{{"has_conflict": false, "conflicts": [], "suggested_action": "none"}}
"""

PROFILE_QUALITY_PROMPT = """评价以下画像的质量。

画像类型：{profile_type}
画像内容：
{profile_text}

原始输入材料摘要：
{source_materials}

请从以下维度评分（0-1）：
1. 信号覆盖率：是否覆盖了输入材料中的关键信息
2. 结构完整度：是否包含了所有要求的段落
3. 内部一致性：是否存在自相矛盾的描述
4. 避免重复：是否有冗余重复的内容

输出JSON格式：
{{"score": 0.8, "issues": ["问题1"], "suggestions": ["建议1"]}}

score为综合评分（0-1），issues为发现的问题列表，suggestions为改进建议列表。
"""

CROSS_PROFILE_CONSISTENCY_PROMPT = """检查新生成的画像与已有同级/上级画像是否存在矛盾。

新画像类型：{profile_type}
新画像内容：
{new_profile}

已有相关画像：
{existing_profiles}

请判断是否存在矛盾。注意区分真正矛盾与合理变化（如近期行为变化是正常的，不算矛盾）。

输出JSON格式：
{{"has_conflict": true, "conflicts": [{{"entity": "相关实体", "conflict_description": "矛盾描述", "old_statement": "旧画像中的描述", "new_statement": "新画像中的描述"}}], "suggested_action": "none"}}
suggested_action取值：none、flag、auto_resolve、user_confirm

如果无矛盾，输出：
{{"has_conflict": false, "conflicts": [], "suggested_action": "none"}}
"""
