# Frontend Reset Control Implementation

**Date:** 2026-03-22  
**Scope:** Frontend prototype state reset control  
**Branch:** wt/frontend-state-reset-control

## Objective

Add a small reset control that calls the backend reset endpoint and refreshes the rendered state. Clear or reconcile local chat and event log state after reset so the prototype does not show stale turns.

## Implementation

### Backend Changes

Added a new endpoint to `app/backend/src/routers/state.py`:

```python
@router.post("/state/reset")
async def reset():
    """Reset mutable state to its initial values and return fresh bootstrap."""
    reset_state()
    return {"status": "ok", "bootstrap": get_bootstrap_state()}
```

This endpoint:
- Calls the existing `reset_state()` function from `state.py`
- Returns the fresh bootstrap state so the frontend can immediately update

### Frontend Changes

#### App.tsx

Added a `reset()` handler function that:
1. Calls `POST /api/state/reset`
2. On success:
   - Clears `messages` array (chat history)
   - Clears `log` array (event log)
   - Updates `bootstrap` state with fresh data from response
   - Adds a system message confirming reset
3. On error: Shows system message with error details
4. Respects `sending` state to prevent concurrent operations

Added a reset button in the header:
- Positioned next to the health indicator and subtitle
- Disabled during sending operations
- Styled with hover and disabled states

#### App.css

Added styles for `.reset-btn`:
- Small button with border
- Consistent with existing UI styling
- Hover effect for better UX
- Disabled state opacity

## Files Modified

| File | Change |
|------|--------|
| `app/backend/src/routers/state.py` | Added POST /state/reset endpoint |
| `app/frontend/src/App.tsx` | Added reset handler and button |
| `app/frontend/src/App.css` | Added reset button styles |

## Verification

The reset control:
- [x] Calls the backend reset endpoint
- [x] Refreshes the rendered state from response
- [x] Clears local chat messages
- [x] Clears local event log
- [x] Shows system confirmation message
- [x] Handles errors gracefully
- [x] Respects operation-in-progress state

## Out of Scope

Following the session rules, no shared docs were modified. The backend endpoint addition was necessary to support the frontend functionality.
