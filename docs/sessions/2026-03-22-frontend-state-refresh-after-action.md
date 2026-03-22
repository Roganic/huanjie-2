# Frontend State Refresh After Action

Date: 2026-03-22
Task: `frontend-state-refresh-after-action`
Branch: `wt/frontend-state-refresh-after-action`

## Goal

After a successful `/api/action` call, the frontend status panel should reflect any state mutations applied by the backend (HP loss, condition changes, time advancement, etc.) instead of remaining frozen at the initial bootstrap values.

## What was done

Added a single re-fetch of `/api/state/bootstrap` immediately after a successful action response is processed in `App.tsx`. The fresh `BootstrapState` replaces the previous value, causing React to re-render the status panel with updated HP, abilities, and other actor/scene data.

### Key design decision

The frontend does **not** apply effects locally. It re-fetches the full authoritative state from the backend. This:
- Avoids duplicating rules or effect-application logic in the frontend
- Ensures the UI always reflects the backend's canonical state
- Keeps the frontend as a pure presentation layer

### Changed files

- `app/frontend/src/App.tsx` — Added `fetch("/api/state/bootstrap")` + `setBootstrap()` after successful action processing (~10 lines)

## Verification

- `npx tsc -b` — type check passed
- `npx eslint src/` — lint passed
- `npm run build` — build succeeded

## Deliberately not done

- No local effect application or optimistic UI update — the task explicitly requires server-authoritative state
- No loading/spinner indicator during the state refresh — the fetch is fast (local) and the status panel keeps its previous values until the response arrives
- No retry logic on refresh failure — consistent with existing bootstrap fetch behavior
- No API service layer extraction — out of scope; the codebase uses raw fetch throughout

## Next steps

- Consider adding a visual flash/highlight on changed values (e.g., HP bar animation) so the player notices mutations
- If latency becomes an issue, consider returning the updated state inline in the `/action` response to avoid the second round-trip
