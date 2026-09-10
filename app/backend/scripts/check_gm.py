"""One real tool call using the configured service; no game state is read or changed."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.gm.provider import ToolProvider, ModelUnavailable, ERRORS
from src.gm.host import tool_definitions, ReplyArgs

async def main():
    provider = ToolProvider()
    if not provider.ready:
        print('模型尚未配置：请填写后端 .env.gm 的地址、模型和密钥。')
        return 1
    try:
        name, args, _, usage = await provider.complete([
            {'role': 'system', 'content': '请调用 respond，用中文简短问候玩家。'},
            {'role': 'user', 'content': '你好，主持人。'}], tool_definitions(['respond']), 18)
        if name != 'respond':
            raise ValueError('wrong tool')
        reply = ReplyArgs.model_validate(args)
        print('模型工具调用已连通：', provider.model)
        print(reply.message)
        print('本次 token 用量：', usage)
        return 0
    except ModelUnavailable as exc:
        print(ERRORS.get(str(exc), '模型调用未通过验证。'))
        return 1
    except ValueError:
        print('模型未返回符合要求的工具调用。')
        return 1

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
