# Prop Bets

Created: 2026-04-11

Status: Complete

Summary
- Site-wide proposition markets where registered users can create binary (Yes/No) props that all users may bet on.
- Superusers settle prop markets via Django admin actions.

What was built
- `PropBet` model (core betting): title, description, creator, open/close times, yes/no odds, totals, settlement fields.
- `PropBetSlip` model (core betting): concrete bet tied to a `PropBet`, binary selection, stake, odds at placement.
- Migration: `packages/vinosports-core/src/vinosports/betting/migrations/0006_propbets.py`.
- Admin: `PropBetAdmin` with settle_yes, settle_no, cancel_prop actions that pay out winners / refund cancelled bets.
- `PropBetSlipAdmin` for viewing individual bets.
- Hub page (`/prop-bets/`): shows open markets, user's bets, recently settled props.
- HTMX partials: create prop form, place bet form, bet confirmation.
- API endpoints: list/create, detail, place bet (JSON).
- My Bets integration: prop bets appear in the cross-league activity feed (desktop table + mobile cards).
- Homepage: featured prop bets section with community sentiment bars, quick bet forms for authenticated users.
- Global navbar: "Prop Bets" link added to user dropdown.
- Admin groups: PropBet and PropBetSlip in "General" group.
- Settlement notifications: per-user inbox notifications on win, loss, or cancellation.
- Seeding: `seed_prop_bets` management command with 5 sample props, wired into `make seed`.
- Tests: 32 tests covering models, views, APIs, settlement payouts, cancellation refunds, and notifications.

Notes
- Initial implementation supports only binary outcomes (Yes / No).
- Models live in core betting so parlays and balance transactions integrate easily.
- Creation policy: any authenticated (registered) user may create prop bets via the site UI; superusers are required to settle markets.
- Settlement pays out winners (`stake * odds`) and marks losers as LOST.
- Cancellation refunds all pending bets via BET_VOID transactions.
