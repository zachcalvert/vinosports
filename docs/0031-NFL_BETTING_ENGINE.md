# 0031: NFL Betting Engine

**Date:** 2026-03-30
**Status:** Planning
**Parent:** [0029-NFL_LEAGUE.md](0029-NFL_LEAGUE.md)
**Depends on:** [0030-NFL_FOUNDATION.md](0030-NFL_FOUNDATION.md) (Complete)
**API Tier:** Free tier for initial build; All-Star ($9.99/mo) needed for standings-driven odds engine if we want data-informed odds closer to season start

## Goal

Build the full NFL betting engine: concrete models (BetSlip, Parlay, Odds, Futures), settlement logic, house odds generation, futures markets, and parlay adapter. At the end of this phase, users should be able to place moneyline, spread, and total bets on NFL games, build parlays, and bet on futures markets — all settled correctly when games complete.

## Key Design Decision: Odds Format

**American odds** (like NBA, unlike EPL's decimal). NFL betting culture uses American odds universally. The NBA patterns give us a direct template.

## Markets

### Core Three (launch scope)

| Market | Selection | Line? | Notes |
|--------|-----------|-------|-------|
| **Moneyline** | HOME / AWAY | No | Straight up winner |
| **Spread** | HOME / AWAY | Yes (e.g., -3.5) | Point spread — the defining NFL bet |
| **Total** | OVER / UNDER | Yes (e.g., 44.5) | Over/under combined score |

### What We're Not Building (yet)

- **Player props**: Requires GOAT tier ($39.99/mo) + Player model stats integration. Defer.
- **Teasers**: New bet type not in the abstract model hierarchy. Fun feature but adds complexity — defer to post-launch.
- **Game props**: First to score, safety, etc. Would need a new market type. Defer.
- **Live betting**: Requires real-time odds updates. Defer to Phase 6 (WebSocket).

## Models

### BetSlip

Inherit from `AbstractBetSlip`. Follow NBA's multi-market pattern exactly.

```python
class BetSlip(AbstractBetSlip):
    class Market(models.TextChoices):
        MONEYLINE = "MONEYLINE", "Moneyline"
        SPREAD = "SPREAD", "Spread"
        TOTAL = "TOTAL", "Total"

    class Selection(models.TextChoices):
        HOME = "HOME", "Home"
        AWAY = "AWAY", "Away"
        OVER = "OVER", "Over"
        UNDER = "UNDER", "Under"

    game = FK("nfl_games.Game")
    market = CharField(choices=Market)
    selection = CharField(choices=Selection)
    odds_at_placement = IntegerField()          # American odds
    line = FloatField(null=True, blank=True)     # spread/total line at placement
```

Identical structure to NBA. This is intentional — NFL and NBA share the same three core markets with the same mechanics.

### Parlay + ParlayLeg

```python
class Parlay(AbstractParlay):
    combined_odds = IntegerField()  # American

class ParlayLeg(AbstractParlayLeg):
    parlay = FK(Parlay)
    game = FK("nfl_games.Game")
    market = CharField(choices=BetSlip.Market)
    selection = CharField(choices=BetSlip.Selection)
    odds_at_placement = IntegerField()  # American
    line = FloatField(null=True, blank=True)

    unique_together = [("parlay", "game")]
```

### Odds

Same structure as NBA — moneyline, spread, total in American format.

```python
class Odds(BaseModel):
    game = FK("nfl_games.Game", related_name="odds")
    bookmaker = CharField(100)                    # "House" for generated odds
    home_moneyline = IntegerField(null=True)
    away_moneyline = IntegerField(null=True)
    spread_line = FloatField(null=True)           # negative = home favored
    spread_home = IntegerField(null=True)         # typically -110
    spread_away = IntegerField(null=True)
    total_line = FloatField(null=True)            # e.g., 44.5
    over_odds = IntegerField(null=True)
    under_odds = IntegerField(null=True)
    fetched_at = DateTimeField()

    unique_together = [("game", "bookmaker")]
```

### Futures

NFL-specific futures markets. These are a big deal in football — futures betting opens months before the season.

```python
class FuturesMarket(AbstractFuturesMarket):
    class MarketType(models.TextChoices):
        SUPER_BOWL = "SUPER_BOWL", "Super Bowl Winner"
        AFC_CHAMPION = "AFC_CHAMPION", "AFC Champion"
        NFC_CHAMPION = "NFC_CHAMPION", "NFC Champion"
        DIVISION = "DIVISION", "Division Winner"

    market_type = CharField(choices=MarketType)
    division = CharField(choices=Division, null=True, blank=True)  # for DIVISION markets

    unique_together = [("season", "market_type", "division")]

class FuturesOutcome(AbstractFuturesOutcome):
    market = FK(FuturesMarket)
    team = FK("nfl_games.Team")
    odds = IntegerField()                        # American
    odds_updated_at = DateTimeField(null=True)

    unique_together = [("market", "team")]

class FuturesBet(AbstractFuturesBet):
    outcome = FK(FuturesOutcome)
    odds_at_placement = IntegerField()           # American
```

**Why DIVISION as a market type?** NFL has 8 divisions with clear winners. Division winner futures are one of the most popular NFL futures markets — more granular than conference, more accessible than Super Bowl. EPL doesn't have this; NBA doesn't either. This is NFL-specific and worth supporting.

## Odds Engine

### House Odds Generation

Follow NBA's `odds_engine.py` pattern: algorithmic odds from standings data.

**NFL-specific considerations:**
- **Spread is king**: The spread line is the most important number. NFL games cluster around a 3-point home advantage with tight margins. The odds engine should produce realistic spreads (typically -1 to -14, clustered around -3 to -7).
- **Totals are lower**: NFL totals are typically 38-54 (vs. NBA's 195-250). The engine needs football-appropriate ranges.
- **Home field advantage**: Historically ~57% home win rate in NFL (vs. ~60% in NBA). Smaller edge.

**Inputs (from Phase 1 data):**
- Team win_pct from Standing
- Division/conference record
- Points for / points against (point differential is predictive in NFL)
- Home/away split (when available from All-Star tier)

**Algorithm sketch:**

```python
def generate_nfl_odds(game, season):
    home_standing = Standing.objects.get(team=game.home_team, season=season)
    away_standing = Standing.objects.get(team=game.away_team, season=season)

    # Team strength: blend win% and point differential
    home_strength = 0.50 * home_standing.win_pct + 0.50 * _norm_point_diff(home_standing)
    away_strength = 0.50 * away_standing.win_pct + 0.50 * _norm_point_diff(away_standing)

    # Home field advantage (~3 points)
    home_edge = 0.03

    # Win probability
    p_home = (home_strength + home_edge) / (home_strength + away_strength + home_edge)
    p_away = 1 - p_home

    # Moneyline (American, with ~5% vig)
    home_ml = _prob_to_american(p_home * 1.05)
    away_ml = _prob_to_american(p_away * 1.05)

    # Spread: derived from probability gap
    raw_spread = -(p_home - 0.5) * 28.0  # NFL-calibrated (smaller range than NBA)
    spread_line = round(raw_spread * 2) / 2  # nearest 0.5

    # Total: base ~44, adjusted by combined offensive strength
    base_total = 44.0
    offense_factor = (home_standing.points_for + away_standing.points_for) / games_played
    total_adjustment = (offense_factor - league_avg_ppg) * 2.0
    total_line = round((base_total + total_adjustment) * 2) / 2  # nearest 0.5
    total_line = max(35.0, min(60.0, total_line))

    return {
        "home_moneyline": home_ml,
        "away_moneyline": away_ml,
        "spread_line": spread_line,
        "spread_home": -110,
        "spread_away": -110,
        "total_line": total_line,
        "over_odds": -110,
        "under_odds": -110,
    }
```

**Key numbers to get right:**
- Spreads should cluster around 3 (pick'em/slight favorite) with tails up to ~14 (massive favorite)
- Totals should range 38-54, centered around 44-46
- Moneylines for close games: -130/+110 range. For mismatches: -300/+250 range.
- Standard juice on spreads/totals: -110 both sides

### Early Season / No Standings

Before the season starts (or early weeks with insufficient data), we need a fallback:

**Option A:** Use previous season standings as a proxy.
**Option B:** Use static power rankings (hardcoded preseason estimates).
**Option C:** Generate flat odds (all games -110/+100 with 3-point home spread).

**Recommendation:** Option A with a blend — weight previous season heavily in weeks 1-4, then fade to current season by week 8. This gives realistic preseason odds without requiring manual curation.

## Settlement Engine

### `nfl/betting/settlement.py`

Follow NBA's `settlement.py` closely. The bet evaluation logic for moneyline/spread/total is identical:

```python
def _evaluate_bet_outcome(market, selection, line, game):
    home_score, away_score = game.home_score, game.away_score

    if market == MONEYLINE:
        if home_score == away_score:
            return BetStatus.VOID  # NFL ties → void moneyline
        if selection == HOME:
            return BetStatus.WON if home_score > away_score else BetStatus.LOST
        return BetStatus.WON if away_score > home_score else BetStatus.LOST

    elif market == SPREAD:
        adjusted = (home_score + line) if selection == HOME else (away_score - line)
        opponent = away_score if selection == HOME else home_score
        diff = adjusted - opponent
        if diff == 0:
            return BetStatus.VOID  # push
        return BetStatus.WON if diff > 0 else BetStatus.LOST

    elif market == TOTAL:
        total = home_score + away_score
        diff = total - line
        if diff == 0:
            return BetStatus.VOID  # push
        if selection == OVER:
            return BetStatus.WON if total > line else BetStatus.LOST
        return BetStatus.WON if total < line else BetStatus.LOST
```

**NFL-specific settlement note:** Moneyline ties are possible (NFL games can end in ties after overtime). These should void the moneyline bet. Spread and total bets are unaffected by the tie/OT distinction — they just use the final score.

### Parlay evaluation

Identical to NBA/EPL — the abstract logic is the same:
- Any leg LOST → parlay LOST
- All legs WON → parlay WON, payout capped at $50k
- Mix of WON + VOID → recalculate from WON legs only
- All VOID → refund

### Balance integration

Use NBA's wrapper pattern (`nfl/betting/balance.py`):
```python
def log_transaction(user, amount, transaction_type, description=""):
    with transaction.atomic():
        balance = UserBalance.objects.select_for_update().get(user=user)
        if balance.balance + amount < 0:
            raise ValueError("Insufficient balance")
        core_log_transaction(balance, amount, transaction_type, description)
```

### Bankruptcy / Bailout

Reuse the core `Bankruptcy` and `Bailout` models. Same threshold ($0.50), same bailout amount ($500).

## Parlay Adapter

Implement `LeagueAdapter` for the core `ParlayBuilder`:

```python
class NFLParlayAdapter(LeagueAdapter):
    """NFL adapter for the league-agnostic ParlayBuilder."""

    def resolve_event(self, event_id):
        return Game.objects.get(pk=event_id)

    def is_bettable(self, event):
        return event.status == GameStatus.SCHEDULED

    def resolve_odds(self, event, selection, extras):
        odds = Odds.objects.filter(game=event).order_by("-fetched_at").first()
        market = extras.get("market", "MONEYLINE")
        american = _get_american_odds(odds, market, selection)
        return _american_to_decimal(american), {"line": _get_line(odds, market)}

    def create_parlay(self, user, stake, combined_decimal_odds, legs_data):
        combined_american = _decimal_to_american(combined_decimal_odds)
        parlay = Parlay.objects.create(
            user=user, stake=stake, combined_odds=combined_american,
        )
        # ... create legs
        return parlay
```

## Futures Odds Engine

### `nfl/betting/futures_odds_engine.py`

**Markets to generate:**
1. **Super Bowl Winner** — all 32 teams
2. **AFC Champion** — 16 AFC teams
3. **NFC Champion** — 16 NFC teams
4. **Division Winners** — 4 teams per division (8 markets)

**Algorithm:** Softmax over team strength, same as NBA but with NFL-calibrated margins:
- Super Bowl: 30% margin (long-shot market, wide field)
- Conference: 20% margin
- Division: 15% margin (smaller field, more predictable)

**Inputs:** Win_pct + point differential from standings. For preseason, use previous season data.

### Futures Settlement

Same flow as NBA: `settle_futures_market(market_pk, winner_team_pk)` → mark winner, pay winning bets, fail losing bets, all atomic with balance transactions.

### Seed Command

`seed_nfl_futures` management command to generate initial markets + outcomes for a season.

## Signals

Post-save on BetSlip for challenge progress tracking (same as NBA):
```python
@receiver(post_save, sender=BetSlip)
def track_bet_for_challenges(sender, instance, created, **kwargs):
    if created:
        check_challenge_progress(instance.user)
```

## Admin

- BetSlip: list_display = user, game, market, selection, odds, stake, status, payout
- Parlay + ParlayLeg: inline legs on parlay admin
- Odds: list_display = game, bookmaker, moneyline, spread, total
- FuturesMarket: list_display = name, market_type, season, status
- FuturesOutcome: list_display = market, team, odds, is_winner
- FuturesBet: list_display = user, outcome, odds, stake, status, payout

## Forms

- `BetForm`: market, selection, line (read-only display), odds (hidden), stake
- `ParlayAddForm`: market, selection (used by parlay builder slide-out)

Follow NBA patterns. These will be fully wired up in Phase 4 (website).

## Task Breakdown

1. **Models + migrations** — BetSlip, Parlay, ParlayLeg, Odds, FuturesMarket, FuturesOutcome, FuturesBet
2. **Settlement engine** — `_evaluate_bet_outcome`, `settle_game_bets`, parlay evaluation
3. **Balance wrapper** — `nfl/betting/balance.py`
4. **Odds engine** — House odds generation from standings
5. **Futures odds engine** — Super Bowl, conference, division markets
6. **Futures settlement** — `settle_futures_market`, `void_futures_market`
7. **Parlay adapter** — `NFLParlayAdapter` for ParlayBuilder
8. **Admin** — All betting model registrations
9. **Forms** — BetForm, ParlayAddForm (used in Phase 4)
10. **Seed command** — `seed_nfl_futures` for initial markets
11. **Signals** — Challenge progress tracking on bet placement
12. **Tests** — Settlement logic, odds engine, futures, parlay adapter, balance

## Dependencies on Other Phases

- **Phase 1 (Complete)**: Team, Game, Standing models + data
- **Phase 4 (Website)**: Views and templates that use these models/forms — betting engine is backend-only
- **Phase 5 (Celery)**: Tasks that trigger settlement + odds generation on schedule

## Resolved Questions

1. **Spread key numbers**: Favor key numbers (3, 7, 10). The odds engine should snap to these when the raw spread is close (e.g., raw 2.8 → snap to 3.0, raw 6.7 → snap to 7.0). Makes the simulation feel authentic.
2. **Overtime scoring for totals**: Include OT in the total. Settlement uses `game.home_score` + `game.away_score` which is the final score including any overtime. This matches real sportsbook behavior.
3. **Division futures timing**: Generate from day one using preseason/previous-season data. Same approach as core odds engine — blend previous season heavily early, fade to current season by mid-season.
