"""Reusable host workflows. These describe tool use; Python owns all permissions."""
WORKFLOWS = {
    'conversation': '先分清表达、询问、目的性行动。单纯情绪/姿态走 expression，无骰、无奖惩、无任务触发；问话走 talk。改变局势先匹配具体目标挑战，再选择允许做法/后果组合；通用社交仅影响态度。npc_memory 是已结算事实，player_intent_not_fact 是当时愿望，不等于发生。',
    'exploration': '先看当前位置和对象。已有互动走 act；新增做法匹配 challenges 后用 adjudicate。无风险观察用 observe；缺少对象/方法用 clarify。不存在的目标或尚无规则的行为用 unavailable。',
    'combat': '任何伤害人物的意图先表达为 attack，不能替换成 talk、威吓或描写躲闪。规则决定目标权限；可攻击时执行现有先攻/战斗。法术与技能使用 actions 中对应规则。',
    'continuity': 'last_action 是上次明确尝试，last_result 是已结算结果。短句重试用 retry；代词结合 last_action.target_id 或 speaker_id，无法唯一确定则 clarify。不同目标分别处理；受限目标不能换成其他目标伪装完成。失败后承接真实后果和新线索；pending_events 尚未发生。',
}


def workflows(session):
    names = ['conversation', 'exploration', 'continuity']
    if session.game_phase.value == 'combat':
        names = ['combat', 'continuity']
    else:
        names.append('combat')  # An attempted attack remains expressible in a peaceful scene.
    return [{'name': name, 'procedure': WORKFLOWS[name]} for name in names]
