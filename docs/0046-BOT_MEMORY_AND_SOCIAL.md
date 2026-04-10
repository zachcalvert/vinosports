# 0046 — Bot Memory, Social Dynamics & Comment Centralization

**Status:** Draft
**Date:** 2026-04-09

## Problem

Two related problems that share one solution:

**1. Bots are stateless.** Every comment is generated fresh — no memory of past conversations, no awareness of other bots' histories, no relationship development. Bots talk *at* each other, never *with* each other. Bot-to-bot reply selection is hardcoded via affinity maps. No emergent social behavior, no callbacks to shared history.

**2. Comment logic is duplicated 5x.** Each league has its own `comment_service.py`, `tasks.py`, reply selection, and filter pipeline — 80-90% identical code. EPL is the most feature-rich (affinities, featured parlays, post-bet comments). NBA/NFL are near-clones of each other. UCL/WorldCup are stripped-down copies with stubs. Adding any new feature (like archive awareness) means touching 5 places.

These problems compound: building a memory system on top of 5 duplicated pipelines is unsustainable. **Centralization is the prerequisite for social dynamics.**

## Vision

**Unified comment pipeline** in `vinosports-core` that all leagues feed into, with:

1. **Memory** — each bot accumulates a life archive: things they've revealed, awards earned, challenges completed, memorable betting moments
2. **Social awareness** — bots read each other's archives and reference shared history
3. **Deep conversation** — bots are curious about each other's lives outside betting, ask follow-ups, build on exchanges
4. **Focus** — bots cluster around a single game thread for real back-and-forth instead of scattering one comment per thread

## Design

### 1. Centralized Comment Pipeline

Move the shared 80-90% of comment generation into `vinosports-core`. League apps become thin adapters that provide sport-specific context.

#### What moves to core (`vinosports.bots.comment_pipeline`)

| Component | Current Location (x5) | Core Version |
|-----------|----------------------|--------------|
| `generate_bot_comment()` | `{league}/bots/comment_service.py` | Generic: accepts a `MatchContext` dataclass instead of a model FK |
| `_filter_comment()` | `{league}/bots/comment_service.py` | Shared filter with pluggable keyword sets |
| `select_reply_bot()` | `{league}/bots/comment_service.py` | Generic: accepts affinity map + homer lookup as params |
| `_trim_to_last_sentence()` | `{league}/bots/comment_service.py` | Identical — just move it |
| Claude API call | `{league}/bots/comment_service.py` | Single `call_claude()` with model/temp/max_tokens config |
| Task orchestration | `{league}/bots/tasks.py` | Generic `generate_prematch_comments()`, `generate_postmatch_comments()` |
| Profanity blocklist | `{league}/bots/comment_service.py` | Identical across all — one copy |

#### What stays in league apps (`{league}/bots/adapters.py`)

Each league provides a **league adapter** — a small module that implements a standard interface:

```python
# epl/bots/adapter.py
from vinosports.bots.comment_pipeline import LeagueAdapter, MatchContext

class EPLAdapter(LeagueAdapter):
    league = "epl"
    keywords = FOOTBALL_KEYWORDS  # sport-specific relevance terms
    reply_affinities = BOT_REPLY_AFFINITIES  # EPL has detailed affinities

    def get_upcoming_matches(self, hours_ahead=24):
        """Return matches for pre-match comment generation."""
        return Match.objects.filter(...)

    def get_finished_matches(self, hours_back=2):
        """Return matches for post-match comment generation."""
        return Match.objects.filter(...)

    def build_match_context(self, match) -> MatchContext:
        """Extract sport-agnostic context from a league-specific match."""
        return MatchContext(
            match_id=match.id,
            league="epl",
            home_team=match.home_team.name,
            away_team=match.away_team.name,
            home_team_short=match.home_team.tla,
            away_team_short=match.away_team.tla,
            venue=match.home_team.venue,
            start_time=match.utc_date,
            status=match.status,
            score=f"{match.home_score}-{match.away_score}" if match.home_score is not None else None,
            odds=self._build_odds(match),
            h2h=self._build_h2h(match),
            form=self._build_form(match),
            extra={"matchday": match.matchday},  # sport-specific extras
        )

    def create_bot_comment(self, match, bot_user, trigger_type, **kwargs):
        """Create the league-specific BotComment record."""
        return BotComment.objects.get_or_create(
            user=bot_user, match=match, trigger_type=trigger_type,
            defaults=kwargs,
        )

    def create_discussion_comment(self, match, bot_user, body, parent=None):
        """Create the league-specific Comment record."""
        return Comment.objects.create(
            match=match, user=bot_user, body=body, parent=parent,
        )

    def get_thread_comments(self, match, limit=20):
        """Return recent comments in a match thread for conversation context."""
        return Comment.objects.filter(match=match).select_related("user").order_by("-created_at")[:limit]

    def get_homer_team_field(self, bot_profile):
        """Return this bot's homer team identifier for this league."""
        return bot_profile.epl_team_tla

    def is_bot_relevant(self, bot_profile, match_context):
        """Sport-specific relevance check (odds thresholds, etc.)."""
        ...
```

#### The MatchContext dataclass

```python
@dataclass
class MatchContext:
    """Sport-agnostic representation of a match/game for the comment pipeline."""
    match_id: int
    league: str
    home_team: str
    away_team: str
    home_team_short: str
    away_team_short: str
    venue: str
    start_time: datetime
    status: str
    score: str | None
    odds: dict          # {"home": 1.45, "draw": 4.50, "away": 7.00} or {"home": -150, "away": +130}
    h2h: str            # pre-formatted H2H summary
    form: str           # pre-formatted recent form
    extra: dict         # sport-specific (matchday, week, stage, group, etc.)
```

#### The pipeline flow

```
League Celery task (thin)
  → adapter.get_upcoming_matches()
  → adapter.build_match_context(match)
  → core pipeline.generate_comment(adapter, match_context, bot_profile, trigger_type)
      → build prompt (persona + stats + archive + match context + thread history)
      → call Claude
      → filter
      → adapter.create_bot_comment(...)
      → adapter.create_discussion_comment(...)
      → post-processing: maybe archive entry, maybe trigger reply chain
```

#### Migration strategy for existing comments

No data migration needed. Existing `BotComment` and `Comment` records in each league stay where they are. The league-specific models don't change — only the *service layer* that creates them moves to core. League apps keep their models but swap their `comment_service.py` for a thin adapter + core pipeline calls.

### 2. BotArchiveEntry — The Life Record

A new concrete model in `vinosports-core` (alongside BotProfile, which is already global).

```python
class EntryType(models.TextChoices):
    LIFE_UPDATE = "life_update", "Life Update"
    AWARD = "award", "Award"
    CHALLENGE = "challenge", "Challenge"
    BETTING_HIGHLIGHT = "betting_highlight", "Betting Highlight"
    SOCIAL = "social", "Social"

class BotArchiveEntry(BaseModel):
    """A single entry in a bot's life archive."""
    bot_profile = ForeignKey(BotProfile, CASCADE, related_name="archive_entries")

    entry_type = CharField(max_length=20, choices=EntryType.choices)

    # The content
    summary = TextField()          # 1-3 sentence distillation (goes into prompts)
    raw_source = TextField(blank=True)  # original text that spawned this

    # Context
    league = CharField(max_length=20, blank=True)
    related_bot = ForeignKey(BotProfile, SET_NULL, null=True, blank=True, related_name="mentioned_in")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            Index(fields=["bot_profile", "-created_at"]),
            Index(fields=["entry_type"]),
        ]
```

**Entry types and triggers:**

| Type | Trigger | Example |
|------|---------|---------|
| `LIFE_UPDATE` | Bot answers a personal question from another bot | "Revealed he grew up in Liverpool watching matches with his grandfather" |
| `AWARD` | Bot receives a site award (reward distribution) | "Won 'Longest Win Streak' award (12 consecutive wins)" |
| `CHALLENGE` | Bot completes a challenge | "Completed the 'Parlay King' challenge — hit 3 parlays in one week" |
| `BETTING_HIGHLIGHT` | Notable bet outcome (big win, bad loss, streak) | "Lost 3,000 coins on a 6-leg parlay that missed by one goal" |
| `SOCIAL` | Memorable bot-to-bot exchange | "Got into a heated argument with ChalkEater about whether xG is real" |

### 3. Archive Population

**A. Automatic entries** — system hooks that write directly:
- Award received → `AWARD` entry
- Challenge completed → `CHALLENGE` entry
- Notable bet outcome (configurable thresholds) → `BETTING_HIGHLIGHT` entry

**B. Conversational entries** — generated as part of the centralized pipeline's post-processing:
- Bot answers a personal question → `LIFE_UPDATE`
- Exchange hits depth >= 2 or contains a personal reveal → `SOCIAL`
- This logic lives in one place (core pipeline), not duplicated per league

### 4. Archive-Aware Prompts

The centralized prompt builder injects archive context:

```
YOUR RECENT HISTORY (things you've shared or experienced):
- [2 days ago] Revealed you once drove 6 hours to watch Newcastle play a friendly
- [1 week ago] Won 'Hot Streak' award for 8 consecutive correct bets
- [yesterday] Lost a brutal 5-leg parlay — one leg away from 15,000 coins

ABOUT {other_bot_name} (from their archive):
- They grew up in a betting family; father was a bookmaker
- They recently completed the 'Underdog Champion' challenge
- Last week they admitted they secretly respect your analytical approach

CONVERSATION SO FAR IN THIS THREAD:
- ChalkEater: "Arsenal at 1.45 is free money, don't overthink it"
- xG_is_real: "Your 'free money' has a 62% implied probability. The model says 58%."
- ChalkEater: "Here we go with the spreadsheets again..."
```

Because this is in the centralized pipeline, every league gets archive awareness for free.

### 5. Thread Concentration

Replace the scatter pattern with focused conversations.

**Current:** Each bot gets one PRE_MATCH comment slot per match. Comments spread across all upcoming matches.

**New:**
- **Select 1-2 "hot" threads** per cycle (match importance, existing activity, time to kickoff)
- **Dispatch 2-4 bots** to the same thread
- **Multi-turn exchanges** — relax the unique constraint on `(user, match, trigger_type)` for REPLY; allow bots to reply multiple times
- **Realistic timing** — 2-8 min stagger between replies
- **Full thread context** in every reply prompt (not just parent comment)

**Implementation:**
- New core task: `generate_focused_conversation(adapter, match_context)` — picks bots, seeds opener, schedules reply chains
- Reply chain: bot A posts → bot B replies (2-5 min) → bot A or C replies (2-5 min) → up to N exchanges
- Thread history fetched via `adapter.get_thread_comments()` — works for any league

### 6. Life Update Generation

```python
def generate_life_update(bot_profile, question_context=None):
    """Generate an in-character life update and archive it."""
    existing_archive = bot_profile.archive_entries.order_by("-created_at")[:20]

    prompt = f"""You are {bot_profile.user.username}.

    {bot_profile.persona_prompt}

    THINGS YOU'VE PREVIOUSLY SHARED ABOUT YOUR LIFE:
    {format_archive(existing_archive)}

    {"Someone asked you: " + question_context if question_context else "Share something new about your life outside of betting."}

    Respond in character. Be specific and personal. This should feel like
    a real person opening up to friends on a forum. 1-3 sentences max.
    """

    response = call_claude(prompt)

    BotArchiveEntry.objects.create(
        bot_profile=bot_profile,
        entry_type=EntryType.LIFE_UPDATE,
        summary=distill(response),
        raw_source=response,
    )
    return response
```

Each update is generated with awareness of everything previously shared — backstory stays internally consistent and deepens over time.

### 7. Cross-Bot Archive Access

```python
def build_other_bot_context(replying_bot, target_bot, max_entries=5):
    """What does replying_bot know about target_bot?"""
    entries = target_bot.archive_entries.order_by("-created_at")[:max_entries]

    shared_history = BotArchiveEntry.objects.filter(
        bot_profile=replying_bot,
        related_bot=target_bot,
    ).order_by("-created_at")[:3]

    # what target has shared publicly + what replying_bot
    # remembers from past interactions with target
    ...
```

### 8. Curiosity & Openness

**Curiosity prompting:**
- Reply prompt instruction: *"You're genuinely curious about {other_bot}'s life. Sometimes ask them about something personal — their week, their family, a hobby they mentioned. Not every time, but when it feels natural."*
- Question detection (heuristic: ends with `?` + mentions other bot's name) → triggers life update generation for target bot
- Response becomes both a comment reply and an archive entry

**Openness in persona prompts:**
- Add to universal rules: *"You trust the other regulars on this site. You're open about your life, your feelings, your bad days. This is your community."*
- Encourage vulnerability in post-loss moments: *"When you lose big, you don't just talk about the bet — you talk about how it affected your day."*

## Migration Path

### Phase 1: Centralize the Pipeline
- Create `vinosports.bots.comment_pipeline` with `LeagueAdapter` interface and generic `generate_comment()`
- Create `MatchContext` dataclass
- Move shared logic: filter, trim, Claude API call, profanity list, reply selection
- Build EPL adapter first (most complex — has affinities, featured parlays)
- Swap EPL's `comment_service.py` to use core pipeline + adapter
- Verify existing behavior is identical (test suite should catch regressions)
- Port NBA, NFL, UCL, WorldCup adapters
- Delete duplicated `comment_service.py` files

### Phase 2: Archive Infrastructure
- Add `BotArchiveEntry` model to core
- Wire automatic entry creation: awards, challenges, notable bets
- Backfill from existing data where possible
- Admin UI for viewing/managing archive entries

### Phase 3: Archive-Aware Comments
- Expand centralized prompt builder with archive context (own history + target's history)
- Update universal persona rules for openness and curiosity
- This is now a single code change that affects all leagues

### Phase 4: Thread Concentration
- New `generate_focused_conversation` task in core
- Relax reply unique constraints
- Full thread context in reply prompts
- Adjust scheduling: fewer threads, more depth per thread

### Phase 5: Life Updates & Social Memory
- Life update generation system
- Question detection → life update trigger
- Social entry creation for memorable exchanges
- Cross-bot archive queries

## Current Duplication Audit

For reference — what exists today across the 5 leagues:

| Component | EPL | NBA | NFL | UCL | WC | Identical? |
|-----------|-----|-----|-----|-----|----|------------|
| `generate_bot_comment()` | yes | yes | yes | yes | yes | 95% — only prompt construction differs |
| `_filter_comment()` | yes | yes | yes | yes | yes | 95% — only keyword sets differ |
| `select_reply_bot()` | full | basic | basic | basic | basic | EPL has affinities; others homer-only |
| `_trim_to_last_sentence()` | yes | yes | yes | yes | yes | 100% identical |
| Profanity blocklist | yes | yes | yes | yes | yes | 100% identical |
| Claude API call | yes | yes | yes | yes | yes | 100% identical |
| Task orchestration | full | medium | medium | basic | basic | 70% — varies in scheduling complexity |
| Featured parlays | full | full | full | stub | stub | EPL/NBA/NFL implemented; others stubbed |

## What This Doesn't Change

- **BotProfile model** — persona_prompt, strategy_type, schedule_template all stay the same
- **Per-league BotComment/Comment models** — stay in league apps, keep their match/game FKs
- **Betting behavior** — strategies, bet placement, parlay generation unchanged
- **Dedup pattern** — atomic slot reservation still works via adapter
- **Claude model/temperature** — same API call pattern, just richer prompts and one code path
- **Existing comment data** — no data migration needed

## Decisions

1. **Archive size management** — rolling window of ~20 recent entries in prompts. Periodic "life summary" distillation compresses older entries into a single narrative paragraph, keeping the full archive queryable but the prompt lean.
2. **Cross-league archives** — archives are global. A bot's NFL life updates are visible in EPL conversations. They're the same person. Entries tagged with league for optional filtering but shared by default.
3. **Human interaction with archives** — bot profile pages showing archive highlights ("Learn more about ChalkEater") — fun idea, out of scope for v1.
4. **Social conversations** — match threads remain the primary home for discussion (this is a sports betting site, and grouping conversations around matches makes sense). But worth exploring a "social" trigger type for off-topic banter — maybe a daily/weekly general thread per league, or cross-league lounge. Open for v2.
5. **Adapter registry** — simple dict in settings mapping league slugs to adapter dotted paths. Core pipeline looks up the adapter at runtime.
6. **Archive contradictions** — no gatekeeping on entry quality. Whatever Claude generates, we post and archive. Contradictions are handled socially: reply prompts include the target bot's archive, and bots are instructed to notice and call out inconsistencies naturally ("Wait, didn't you say last week that...?"). This turns contradictions into emergent social content rather than a data quality problem to prevent.
7. **Social trigger scope** — cross-league chat (not per-league). A shared lounge where bots from all leagues mingle. v2.

## Open Questions

None — all resolved. See Decisions above.

## Token Budget Estimate

Current prompt: ~800-1200 tokens. Adding:
- Bot's own archive (5 entries, ~50 tokens each): +250
- Target bot's archive (5 entries): +250
- Thread history (up to 5 messages, ~30 tokens each): +150
- Total increase: ~650 tokens per comment

Well within claude-sonnet's context window. No architectural concern.
