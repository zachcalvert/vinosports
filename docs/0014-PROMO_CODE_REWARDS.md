# 0014: Promo Code Rewards

**Date:** 2026-03-24

## Context

VinoSports is a free game and we enjoy shipping fun, surprising features. The registration flow is functional but straightforward — enter email, password, done. We want to add a moment of delight at signup that hints at the personality of the platform.

## Feature

An optional **promo code** field on the signup form. Users can enter any creative text they want. The code is sent to the Claude API, which judges its "creativeness" and awards bonus tokens (250-1000) on top of the standard signup balance.

This is intentionally arbitrary and playful — there are no "real" promo codes. The fun is in the surprise of getting a score back.

## Architecture Decisions

### Synchronous Claude call during signup
No need to add Celery/workers to the hub container. With `max_tokens=10` (only a number is returned), latency is <2 seconds. If this becomes a concern, it can be refactored to an async task later.

### Skip the Reward model
The `Reward` model is designed for predefined, reusable rewards (e.g., bet milestones). A promo bonus is dynamic (variable amount per user) and one-time. Using `log_transaction` directly — the same pattern the existing signup bonus uses — is cleaner and avoids cluttering the rewards table.

### Store the promo code on User
A new optional `promo_code` CharField on the User model provides a record of what was entered, useful for analytics.

### New PROMO_CODE transaction type
Added to `BalanceTransaction.Type` so promo bonuses are distinguishable in transaction history and the activity feed.

### Graceful degradation
If the Claude API call fails (network error, rate limit, missing key), the user is still created normally with their standard signup bonus. No bonus is awarded, no error is shown.

## Claude Prompt Design

**System prompt:**
> You are a judge for a sports betting simulation site called VinoSports. Users enter a promo code when signing up. Your job is to rate the creativeness of the promo code and assign a bonus token amount.
>
> Rules:
> - Return ONLY a single integer between 250 and 1000
> - 250 = generic/boring (e.g., "test", "promo", "abc123")
> - 500 = decent effort (e.g., "ParlaKing", "BetBoss2024")
> - 750 = creative and fun (e.g., "HedgeFundOfOne", "DegenerateScholar")
> - 1000 = exceptional creativity, humor, or sports reference (e.g., "VinoVeritasVictory", "LeBronzeAge")
> - Sports references, wordplay, and humor should score higher
> - Generic words, simple numbers, or keyboard mashing should score lower
> - Return ONLY the number, nothing else

**User prompt:** `Rate this promo code: {code}`

**Parameters:** `model=claude-sonnet-4-20250514`, `max_tokens=10`, `temperature=0.7`

## Implementation

### Files changed

| File | Change |
|------|--------|
| `packages/vinosports-core/.../users/models.py` | Add `promo_code` CharField to User |
| `packages/vinosports-core/.../betting/models.py` | Add `PROMO_CODE` to BalanceTransaction.Type |
| `apps/hub/config/settings.py` | Add `ANTHROPIC_API_KEY` setting |
| `apps/hub/hub/forms.py` | Add `promo_code` field + validation |
| `apps/hub/hub/promo.py` | New file: `evaluate_promo_code()` |
| `apps/hub/hub/views.py` | Wire promo code into `SignupView.post` |
| `apps/hub/hub/templates/hub/signup.html` | Add promo code input to form |

### Transaction ordering

The Claude API call happens **outside** the DB transaction to avoid holding a lock during a network call:

1. `transaction.atomic()` — create user, balance, signup bonus, save promo_code on user
2. Outside atomic — call `evaluate_promo_code()`
3. New `transaction.atomic()` — `select_for_update` on balance, `log_transaction` for the bonus

### Validation

- Promo code must not contain spaces
- Field is optional (blank is fine, skips the entire flow)
- Claude response is parsed for the first integer, clamped to 250-1000
- Unparseable responses are treated as 0 bonus

## Testing

- **Unit:** Mock Anthropic client, verify `evaluate_promo_code` returns correct/clamped/fallback values
- **Unit:** Form validation — spaces rejected, blank accepted, normal strings pass
- **Integration:** Signup with promo code produces both SIGNUP and PROMO_CODE transactions, balance reflects both
