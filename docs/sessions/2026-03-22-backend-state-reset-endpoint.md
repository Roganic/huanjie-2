# 2026-03-22 Backend State Reset Endpoint

## Goal

Add an explicit reset endpoint for the mutable in-memory actor and scene used by the local prototype. Return fresh bootstrap state after reset so the frontend can resync in one request.

## What was done

### New endpoint (`src/routers/state.py`)

Added `POST /state/reset` that:
1. Calls the existing `reset_state()` function to restore actor and scene to initial values
2. Returns the fresh `BootstrapState` in the response body

This gives the frontend a single-request path to reset the game state and receive the updated bootstrap in one call, avoiding a separate round-trip to `/state/bootstrap`.

The endpoint has no request body and returns the same `BootstrapState` schema as the existing `GET /state/bootstrap` endpoint.

### Tests (`tests/test_mutation.py`)

Added three integration tests:

- **`test_reset_endpoint_restores_initial_state`** — verifies that after mutations (HP damage, condition addition, time advancement), calling the reset endpoint restores all state to initial values (HP=12, conditions=[], time=0)
- **`test_reset_endpoint_returns_fresh_bootstrap`** — confirms the response body contains the correct bootstrap state with all initial values
- **`test_reset_clears_accumulated_mutations`** — tests that multiple accumulated mutations from several actions are all cleared by a single reset call

All tests use the existing test fixtures and httpx AsyncClient for end-to-end HTTP testing.

## Verification

```bash
python -m pytest tests/ -v   # 37 passed (34 existing + 3 new)
```

All existing tests continue to pass. The new endpoint does not break any existing functionality.

## Deliberately not done

- **Authentication / authorization** — this is a local prototype; no auth layer exists yet
- **Partial state reset** — currently resets everything; selective reset (e.g. only HP, only conditions) is not needed for the current use case
- **Reset history / undo** — no state versioning or rollback; reset always goes to the hardcoded initial state
- **Frontend integration** — this task only adds the backend endpoint; frontend consumption is a separate task

## Next steps

- Frontend can call `POST /state/reset` when the user requests a game state reset
- A "reset game" button in the UI could trigger this endpoint and refresh the display with the returned bootstrap state
- If multiplayer or sessions are added later, this endpoint may need to be scoped to a specific session/room
