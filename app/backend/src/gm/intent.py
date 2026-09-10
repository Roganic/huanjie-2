"""Short retries refer to persisted action records, never to narrator prose."""
import re
from ..game.commands import GameCommand

REPEAT = re.compile(r'^(?:再试一次|再试试|再来一次|再做一次|重试|继续刚才的动作|try again|repeat)[。！!?？\s]*$', re.I)


def resolve_repeat(session, command, *, explicit=False):
    if not explicit and (command.kind != 'text' or not command.text or not REPEAT.fullmatch(command.text.intent.strip())):
        return command, ''
    previous = session.discourse.get('last_action')
    if not previous:
        return command, '还没有可以明确重试的行动记录，请说明动作和对象。'
    if previous['scene_id'] != session.scene.id or previous['phase'] != session.game_phase.value:
        return command, '位置或和平／战斗状态已经变化，请明确现在要执行的行动。'
    stored = previous.get('command')
    if not stored:
        return command, '上一次请求没有形成明确行动，请补充动作和对象。'
    return GameCommand.model_validate(stored).model_copy(update={
        'request_id': command.request_id, 'expected_scene_id': session.scene.id}), ''
