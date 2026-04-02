# Game Notes (NBA + NFL)

> Status: **Ready to implement**

## Summary

Extend EPL's match notes feature to NBA and NFL. A superuser-only free-text field on each game detail page, editable inline via HTMX. Bot comment generation consumes these notes for post-game and reply triggers, producing richer, more grounded commentary.

EPL has had this since the epl-bets days. NBA and NFL have zero notes infrastructure today.

## What Exists (EPL)

| Component | File |
|-----------|------|
| `MatchNotes` model | `epl/matches/models.py` |
| `MatchNotesForm` | `epl/matches/forms.py` |
| `MatchNotesView` | `epl/matches/views.py` |
| URL route | `epl/matches/urls.py` — `match/<slug>/notes/` |
| Admin | `epl/matches/admin.py` |
| Notes panel template | `epl/matches/templates/matches/partials/match_notes_panel.html` |
| Game detail include | `epl/matches/templates/matches/match_detail.html` |
| Bot prompt injection | `epl/bots/comment_service.py` — `_build_user_prompt()` |

## Implementation Plan

### 1. Models

Create `GameNotes` in both `nba/games/models.py` and `nfl/games/models.py`:

```python
class GameNotes(BaseModel):
    """Admin-authored game notes injected into bot comment prompts."""
    game = models.OneToOneField(
        Game, on_delete=models.CASCADE,
        related_name="notes", verbose_name=_("game"),
    )
    body = models.TextField(_("notes"), blank=True,
        help_text=_("Free-form game observations for bot context"))

    class Meta:
        verbose_name = "game notes"
        verbose_name_plural = "game notes"

    def __str__(self):
        return f"Notes for {self.game}"
```

Then `makemigrations nba_games nfl_games` and `migrate`.

### 2. Forms

Create `nba/games/forms.py` and `nfl/games/forms.py` (neither exists today):

```python
class GameNotesForm(forms.ModelForm):
    class Meta:
        model = GameNotes
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={...})}
```

Sport-appropriate placeholders:
- NBA: *"Key moments, big plays, injuries, clutch shots, drama..."*
- NFL: *"Key moments, touchdowns, turnovers, big plays, injuries, drama..."*

### 3. Views

Add `GameNotesView` to both `nba/games/views.py` and `nfl/games/views.py`:

- `UserPassesTestMixin` — superuser only
- POST handler: `get_or_create` GameNotes, bind form, save, return rendered partial
- Lookup by `id_hash` (not `slug` — EPL uses slug, NBA/NFL use id_hash)

Update `GameDetailView.get()` in both leagues to add `game_notes_form` and `game_notes` to context for superusers.

### 4. URL Routes

Add to both `nba/games/urls.py` and `nfl/games/urls.py`:

```python
path("<str:id_hash>/notes/", GameNotesView.as_view(), name="game_notes"),
```

Must be placed **before** the catch-all `<str:id_hash>/` pattern.

### 5. Admin

Register `GameNotes` in both `nba/games/admin.py` and `nfl/games/admin.py`:

```python
@admin.register(GameNotes)
class GameNotesAdmin(admin.ModelAdmin):
    list_display = ["game", "created_at", "updated_at"]
    list_select_related = ["game__home_team", "game__away_team"]
    search_fields = ["game__home_team__name", "game__away_team__name"]
    raw_id_fields = ["game"]
```

### 6. Templates

**Notes panel partial** — create in both leagues:
- `nba/games/templates/games/partials/game_notes_panel.html`
- `nfl/games/templates/nfl_games/partials/game_notes_panel.html`

Follow EPL's `match_notes_panel.html` exactly, substituting:
- `match` -> `game`, `match_notes` -> `game_notes`, `match_notes_form` -> `game_notes_form`
- `hx-post` URL: `{% url 'nba_games:game_notes' game.id_hash %}` / `{% url 'nfl_games:game_notes' game.id_hash %}`

**Game detail include** — add to bottom of content block in both:
- `nba/games/templates/games/game_detail.html`
- `nfl/games/templates/nfl_games/game_detail.html`

```html
{% if game_notes_form %}
    <div class="mb-6">
        {% include "games/partials/game_notes_panel.html" %}
    </div>
{% endif %}
```

### 7. Bot Comment Service Integration

Add notes injection to `_build_user_prompt()` in both `nba/bots/comment_service.py` and `nfl/bots/comment_service.py`:

```python
if trigger_type in (BotComment.TriggerType.POST_MATCH, BotComment.TriggerType.REPLY):
    try:
        notes = GameNotes.objects.get(game=game)
        if notes.body.strip():
            lines.append("")
            lines.append("Game notes (from a real viewer):")
            lines.append(notes.body.strip())
    except GameNotes.DoesNotExist:
        pass
```

Place after the H2H/form stats block, before trigger-specific context.

### 8. Tests

Per league:
- **Model**: OneToOne constraint, `__str__`
- **View**: superuser access (403 for non-superuser), create notes, update notes, invalid form 400, context presence for superusers, context absence for regular users
- **Comment service**: notes included in prompt for POST_MATCH and REPLY triggers, excluded for PRE_MATCH/POST_BET, graceful when no notes exist

## Key Differences from EPL

| Aspect | EPL | NBA / NFL |
|--------|-----|-----------|
| Game URL param | `slug` | `id_hash` |
| Model name | `MatchNotes` | `GameNotes` |
| Template namespace | `matches/` | `games/` / `nfl_games/` |
| URL namespace | `epl_matches` | `nba_games` / `nfl_games` |
| Forms file | exists | must create |
