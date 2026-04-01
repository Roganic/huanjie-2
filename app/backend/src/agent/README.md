# GM Agent Module

This module handles AI-powered narrative generation for the 幻界 2.0 backend.

## Overview

The `narrator.py` module provides immersive, GM-style narrative text for player actions by calling the Kimi API. When the API is unavailable or misconfigured, it gracefully falls back to template narratives.

## Configuration

Set the following environment variables to configure the Kimi API:

```bash
# Required for AI generation (without this, fallback mode is used)
export KIMI_API_KEY="your-api-key-here"

# Optional overrides (defaults shown)
export KIMI_API_URL="https://api.moonshot.cn/v1/chat/completions"
export KIMI_MODEL="moonshot-v1-8k"
export KIMI_TIMEOUT_SECONDS="5"
```

## Usage

```python
from src.agent.narrator import generate_narration
from src.models.action import ActionRequest, Outcome
from src.state import get_actor, get_scene

actor = get_actor()
scene = get_scene()
req = ActionRequest(
    scene_id="scene-01",
    actor="Aldric",
    intent="pick the lock",
    approach="use my thieves tools",
    ability="dex",
)

narrative = generate_narration(
    req=req,
    actor=actor,
    scene=scene,
    outcome=Outcome.SUCCESS,
    check_result={"ability": "dex", "dc": 15, "roll": 18, "total": 21},
)
print(narrative)
```

## Features

- **AI-Powered**: Uses Kimi API for immersive, GM-style narratives
- **Graceful Fallback**: Template narratives when API is unavailable
- **Context-Aware**: Includes character, scene, action, and outcome in prompts
- **Combat Support**: Special handling for attack actions with damage details
- **Configurable**: Environment-based configuration, no hardcoded secrets

## Testing

Run the test suite:
```bash
cd app/backend
python -m pytest tests/test_narrative.py -v
```

Test with a real API key:
```bash
export KIMI_API_KEY="your-key"
python scripts/test_kimi_narrative.py
```

Test fallback mode (no API key):
```bash
unset KIMI_API_KEY
python scripts/test_kimi_narrative.py
```
