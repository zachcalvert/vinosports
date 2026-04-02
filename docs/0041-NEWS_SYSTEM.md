# News System

> Status: **Planning**
> Depends on: Game Notes (0040)

## Vision

Auto-generated news articles powered by game data, betting outcomes, and admin-authored game notes. Bots already react to games in comment threads — this extends them into standalone content creators, producing articles that feel like sports journalism written by opinionated personalities.

## Why This Is Interesting

- **Game notes double-dip**: The same notes Zach writes while watching a game feed both the post-game comment thread AND news articles. One input, two outputs.
- **Builds on what exists**: Bot personalities, Claude API integration, Celery tasks, game result data — all already in place.
- **Content without content creation**: The system generates a feed of articles from data that's already flowing through the platform. No editorial team needed.

## Potential Article Types

### Game Recaps
- Generated after a game finishes (like post-match comments, but long-form)
- Consumes: final score, box score stats, game notes, betting line/result
- Tone: written by a specific bot personality
- Example: *"The Lakers covered a 6.5-point spread in what can only be described as a masterclass in second-half adjustments..."*

### Betting Trend Pieces
- Generated on a schedule (weekly? mid-week?)
- Consumes: aggregate betting data — which teams are covering, which spreads are moving, user betting patterns
- Example: *"Arsenal have covered in 7 of their last 8 — here's why the market still isn't adjusting"*

### Weekly Roundups / Power Rankings
- Generated once per week per league
- Consumes: all game results from the week, standings changes, notable betting outcomes
- A bot's opinionated take on the state of the league

### Cross-League Takes
- The most ambitious format — a bot comments on trends across all three leagues
- Requires a bot that exists at the hub level, not scoped to a single league
- Example: *"Underdogs are eating across the board this week..."*

## Open Questions

- **Where do articles live?** New `news` app in each league? A single `news` app in hub with a league FK? Hub-level feels right for cross-league, but league-scoped articles might want league-specific models.
- **Who writes them?** Existing bot personalities, or a new "journalist" bot archetype? Could be both — game recaps by team-affiliated bots, trend pieces by a neutral analyst bot.
- **How are they surfaced?** A news feed on the hub homepage? A dedicated `/news/` section per league? Inline on the league dashboard?
- **Can users interact?** Comments on articles? Reactions? Or read-only?
- **Generation triggers**: Celery tasks on game completion (recaps), Celery beat schedule (weekly roundups), manual admin trigger (special pieces)?
- **Cost control**: Each article is a Claude API call. How many articles per week across three leagues? Need to estimate token usage and cost.
- **Quality control**: Auto-publish, or queue for admin review before publishing? Could start with admin review and graduate to auto-publish once quality is consistent.

## Rough Data Model Sketch

```
NewsArticle
    league          FK (nullable — null = cross-league)
    author          FK to BotProfile (nullable — could be system-generated)
    article_type    enum (RECAP, TREND, ROUNDUP, CROSS_LEAGUE)
    title           CharField
    body            TextField
    game            FK (nullable — only for recaps)
    published_at    DateTimeField (nullable — null = draft)
    status          enum (DRAFT, PUBLISHED, ARCHIVED)
```

## Not In Scope (Yet)

- User-submitted articles or tips
- External news API ingestion
- Real-time news (push notifications, breaking news)
- SEO optimization / public-facing articles (everything is behind auth for now)

## Implementation Sequence

1. **Game Notes across all leagues** (doc 0040) — prerequisite
2. **Game Recaps** — simplest article type, closest to what bots already do, just longer form
3. **Weekly Roundups** — introduces scheduled generation and multi-game aggregation
4. **Betting Trend Pieces** — requires querying aggregate betting data
5. **Cross-League Takes** — requires hub-level bot concept
