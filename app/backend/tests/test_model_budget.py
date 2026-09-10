"""Financial boundaries: concurrent reservations, failures, and real transport."""
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from src.gm import budget, provider

PAYLOAD = {'model': 'qwen3.7-plus', 'messages': [], 'max_tokens': 800}


def test_concurrent_requests_share_persistent_limit_and_retry_keeps_hold():
    amount, _ = budget.quote(PAYLOAD)
    config = {'GM_BUDGET_YUAN': str(amount / 1_000_000)}
    def attempt(_):
        try:
            return budget.reserve(PAYLOAD, config)
        except budget.BudgetError:
            return None
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert sum(r is not None for r in results) == 1
    winner = next(r for r in results if r)
    # Restarting a provider/connection and absent usage must not release a hold.
    budget.settle(winner, {'prompt_tokens': 10})
    assert budget.summary()['reserved_yuan'] == amount / 1_000_000
    with pytest.raises(budget.BudgetError, match='exhausted'):
        budget.reserve(PAYLOAD, config)
    budget.settle(winner, {'prompt_tokens': 10, 'completion_tokens': 5})
    budget.settle(winner, {'prompt_tokens': 0, 'completion_tokens': 0})
    assert budget.summary()['reported_yuan'] == 60 / 1_000_000


def test_unknown_prices_oversized_requests_and_invalid_caps_fail_closed():
    with pytest.raises(budget.BudgetError, match='pricing_unknown'):
        budget.validate_endpoint('qwen3.7-plus', 'https://unpriced-reseller.invalid/chat/completions')
    for payload in ({**PAYLOAD, 'model': 'unpriced'}, {**PAYLOAD, 'messages': ['x' * 65536]}, {**PAYLOAD, 'max_tokens': 20000}):
        with pytest.raises(budget.BudgetError):
            budget.reserve(payload, {})
    for limit in ('nan', 'inf', '-1', '21'):
        with pytest.raises(budget.BudgetError, match='configuration'):
            budget.reserve(PAYLOAD, {'GM_BUDGET_YUAN': limit})
    assert budget.summary()['requests'] == 0


def test_authoring_reasoning_is_bounded_and_reserved_before_network():
    payload = {**PAYLOAD, 'enable_thinking': True, 'thinking_budget': 4096}
    amount, rates = budget.quote(payload)
    without_thinking, _ = budget.quote({**payload, 'enable_thinking': False})
    assert amount >= without_thinking + 4096 * rates[1] - 2
    for value in (None, 0, 4097, True):
        with pytest.raises(budget.BudgetError, match='budget_request_size'):
            budget.quote({**payload, 'thinking_budget': value})


@pytest.mark.asyncio
async def test_invalid_model_output_is_charged_and_budget_prevents_network(monkeypatch):
    model = provider.ToolProvider({'GM_MODEL': 'qwen3.7-plus', 'GM_API_URL': 'https://example.invalid/chat/completions',
                                  'GM_API_KEY': 'test', 'GM_BUDGET_YUAN': '1'})
    calls = 0
    async def post(self, url, **kwargs):
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': 'invalid tool reply'}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 20}})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    with pytest.raises(provider.ModelUnavailable):
        await model.complete([], [], 1)
    assert budget.summary()['reported_yuan'] == .00036
    model.config['GM_BUDGET_YUAN'] = '0'
    with pytest.raises(provider.ModelUnavailable, match='budget_exhausted'):
        await model.complete([], [], 1)
    assert calls == 1


@pytest.mark.asyncio
async def test_timeout_retains_reservation_and_settings_preserve_cap(monkeypatch, client):
    from tests.test_gm_settings import BODY
    client.base_url = 'http://127.0.0.1:8000'
    provider.CONFIG_FILE.write_text('GM_BUDGET_YUAN=0.5\n')
    assert (await client.put('/gm/settings', json=BODY)).status_code == 200
    assert provider.configuration()['GM_BUDGET_YUAN'] == '0.5'
    async def timeout(self, url, **kwargs):
        raise httpx.ReadTimeout('timeout')
    monkeypatch.setattr(httpx.AsyncClient, 'post', timeout)
    with pytest.raises(provider.ModelUnavailable, match='timeout'):
        await provider.ToolProvider().complete([], [], 1)
    assert budget.summary()['reserved_yuan'] > 0
