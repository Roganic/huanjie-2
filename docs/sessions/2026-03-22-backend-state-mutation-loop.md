# 2026-03-22 Backend State Mutation Loop

## Goal

Convert the backend from read-only bootstrap constants to a mutable in-memory state store, and apply action effects (HP, conditions, time) to that store after each `/action` resolution.

## What was done

### Model additions (additive, no breaking changes)

- `Actor.conditions: list[str]` — active status effects (empty by default)
- `Scene.time: int` — abstract time ticks elapsed (0 by default)

### Mutable state store (`src/state.py`)

Replaced the read-only `BOOTSTRAP_STATE` constant with module-level mutable singletons. All mutations go through `apply_effects(effects)`, which processes the same `Effect` objects the resolver returns.

Supported effect fields:
- `hp` (int delta) — clamped to `[0, hp_max]`
- `conditions_add` (str) — idempotent add
- `conditions_remove` (str) — safe remove
- `time` (int delta) — scene time accumulation

Unrecognised targets or fields are silently skipped so the resolver can emit forward-looking effect types without breaking current handling.

`reset_state()` provided for test isolation.

### Effect generation in resolver (`src/engine/resolver.py`)

- Every check (not auto-success) emits a `time +1` effect on the current scene.
- Failed physical checks (STR/DEX/CON) emit `hp -1` on the actor.
- Failed non-physical checks retain the `narrative_state: setback` placeholder.
- Auto-success actions produce no effects (no state mutation).

### Action router (`src/routers/action.py`)

Now calls `apply_effects(result.effects)` after resolution, before returning the response. This is the single write path.

### Tests (`tests/test_mutation.py`)

22 new tests covering:
- HP damage, healing, clamping (min 0, max hp_max)
- Condition add/remove/idempotency
- Time advancement and accumulation
- Unknown target/field silently skipped
- Reset restores initial state
- Bootstrap endpoint reflects live mutations
- `/action` endpoint integration: time advances, HP drops on failed physical check, auto-success is side-effect-free

Existing test files (`test_action.py`, `test_state.py`) updated with `reset_state()` autouse fixture.

## Verification

```
python3 -m pytest tests/ -v   # 34 passed
python3 -m compileall src tests
```

## Deliberately not done

- **Resource tracking** (spell slots, inventory, torches) — no resource system exists yet; infrastructure is ready when needed via new `field` types.
- **Condition mechanical effects** (e.g. poisoned → disadvantage) — requires resolver awareness; deferred to a rules-expansion task.
- **Persistence / session management** — still in-memory singletons; reset on server restart.
- **Richer effect heuristics** (variable damage, critical hits) — kept minimal; current generation is deterministic and testable.
- **API shape changes** — no new endpoints or request fields. `conditions` and `time` are additive on the bootstrap response only.

## Next steps

- `frontend-state-refresh-after-action` can now re-fetch `/state/bootstrap` after each action and display updated HP, conditions, and time.
- A future task could add condition-based modifiers to the resolver (e.g. disadvantage when poisoned).
- Resource tracking can reuse the same `apply_effects` infrastructure with new field types.
