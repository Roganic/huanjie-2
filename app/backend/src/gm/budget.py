"""Conservative, durable API accounting. Amounts are integer micro-yuan.

Reserve before network I/O. Unknown outcomes keep their full reservation;
successful usage can reduce it even if subsequent game validation fails.
The development allocation is 20 yuan; hosted deployment has a separate 25.
"""
import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

LEDGER = Path(__file__).resolve().parents[2] / '.model-usage.sqlite'
# Official uncached prices, yuan / million tokens, 2026-09-09.
# Qwen3.7 Plus has the same output rate for bounded thinking and final answers.
# Unknown models are blocked until their pricing and context tier are checked.
PRICES = {'qwen3.7-plus': (2, 8), 'qwen3.8-max': (12, 36), 'glm-4-flash': (0, 0)}
ALLOWED_HOSTS = {'qwen3.7-plus': {'dashscope.aliyuncs.com'}, 'qwen3.8-max': {'dashscope.aliyuncs.com'}, 'glm-4-flash': {'open.bigmodel.cn'}}
LOCAL_CEILING = 20_000_000
SCHEMA = '''CREATE TABLE IF NOT EXISTS model_usage (
    id TEXT PRIMARY KEY, model TEXT NOT NULL, created_at INTEGER NOT NULL,
    reserved INTEGER NOT NULL, charged INTEGER NOT NULL,
    state TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER)'''


class BudgetError(Exception):
    pass


def validate_endpoint(model, url):
    host = urlparse(url).hostname or ''
    allowed = host in ALLOWED_HOSTS.get(model, set())
    if model in ('qwen3.7-plus', 'qwen3.8-max') and host.endswith('.cn-beijing.maas.aliyuncs.com'):
        allowed = True
    if not allowed:
        raise BudgetError('pricing_unknown')


@contextmanager
def connect():
    db = sqlite3.connect(LEDGER, timeout=10)
    try:
        with db:
            db.execute(SCHEMA)
            yield db
    finally:
        db.close()


def quote(payload):
    rates = PRICES.get(payload.get('model'))
    if rates is None:
        raise BudgetError('pricing_unknown')
    # UTF-8 bytes plus generous protocol overhead bound tokenization, including
    # tool schemas. Reject oversized input rather than entering a higher tier.
    input_bound = len(json.dumps(payload, ensure_ascii=False).encode()) + 8192
    output_bound = payload.get('max_tokens')
    if input_bound > 65536 or type(output_bound) is not int or not 1 <= output_bound <= 16384:
        raise BudgetError('budget_request_size')
    if payload.get('enable_thinking'):
        thinking = payload.get('thinking_budget')
        if payload.get('model') not in ('qwen3.7-plus', 'qwen3.8-max') or type(thinking) is not int or not 1 <= thinking <= 4096:
            raise BudgetError('budget_request_size')
        output_bound += thinking  # Conservative even if a provider counts it within max_tokens.
    return math.ceil(input_bound * rates[0] + output_bound * rates[1]), rates


def reserve(payload, config):
    amount, rates = quote(payload)
    try:
        limit = float(config.get('GM_BUDGET_YUAN', '2'))
        if not math.isfinite(limit) or not 0 <= limit <= 20:
            raise ValueError()
        limit = min(LOCAL_CEILING, math.floor(limit * 1_000_000))
    except (ValueError, TypeError):
        raise BudgetError('budget_configuration') from None
    token = uuid.uuid4().hex
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        used = db.execute('SELECT COALESCE(SUM(charged), 0) FROM model_usage').fetchone()[0]
        if used + amount > limit:
            raise BudgetError('budget_exhausted')
        db.execute('INSERT INTO model_usage VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)',
                   (token, payload['model'], int(time.time()), amount, amount, 'reserved'))
    return token, rates


def settle(reservation, usage):
    if not isinstance(usage, dict):
        return
    inputs, outputs = usage.get('prompt_tokens'), usage.get('completion_tokens')
    # A missing/invalid usage field must never be interpreted as zero spend.
    if type(inputs) is not int or type(outputs) is not int or inputs < 0 or outputs < 0:
        return
    token, rates = reservation
    actual = math.ceil(inputs * rates[0] + outputs * rates[1])
    with connect() as db:
        db.execute("UPDATE model_usage SET charged = ?, state = 'reported', input_tokens = ?, output_tokens = ? WHERE id = ? AND state = 'reserved'",
                   (actual, inputs, outputs, token))


def summary():
    with connect() as db:
        spent, held, count = db.execute("SELECT COALESCE(SUM(CASE WHEN state='reported' THEN charged ELSE 0 END),0), COALESCE(SUM(CASE WHEN state='reserved' THEN charged ELSE 0 END),0), COUNT(*) FROM model_usage").fetchone()
    return {'reported_yuan': spent / 1_000_000, 'reserved_yuan': held / 1_000_000,
            'requests': count, 'allocation_yuan': 20}
