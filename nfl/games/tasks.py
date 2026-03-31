"""
Celery tasks for NFL game data ingestion.

fetch_teams, fetch_players, fetch_schedule — periodic data sync from BDL.
fetch_live_scores — polls for in-progress game updates, broadcasts changes via WS.
fetch_standings — recomputes standings from final game results.
"""

import logging

from celery import shared_task

from nfl.games.services import (
    compute_standings,
    sync_games,
    sync_players,
    sync_teams,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_teams(self):
    """Sync all 32 NFL teams from the data API."""
    try:
        count = sync_teams()
        return {"synced": count}
    except Exception as exc:
        logger.error("fetch_teams failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_players(self):
    """Sync all NFL players from BDL."""
    try:
        count = sync_players()
        return {"synced": count}
    except Exception as exc:
        logger.error("fetch_players failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_schedule(self, season: int | None = None):
    """Sync full game schedule for a season (defaults to current)."""
    if season is None:
        season = _current_season()
    try:
        count = sync_games(season)
        return {"synced": count, "season": season}
    except Exception as exc:
        logger.error("fetch_schedule failed (season=%s): %s", season, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_standings(self, season: int | None = None):
    """Recompute NFL standings from final game results."""
    if season is None:
        season = _current_season()
    try:
        count = compute_standings(season)
        return {"computed": count, "season": season}
    except Exception as exc:
        logger.error("fetch_standings failed (season=%s): %s", season, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def fetch_live_scores(self):
    """Poll BDL for today's games and update scores/status.

    Detects score changes and broadcasts them via WebSocket.
    Triggers settlement for games that just became FINAL.
    """
    try:
        count = sync_live_scores()
        return {"updated": count}
    except Exception as exc:
        logger.error("fetch_live_scores failed: %s", exc)
        raise self.retry(exc=exc)


def sync_live_scores() -> int:
    """Fetch today's games from BDL and update scores/status in the DB.

    Returns count of games updated.
    Broadcasts score changes via WebSocket and creates activity events.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from nfl.activity.models import ActivityEvent
    from nfl.games.models import Game, GameStatus
    from nfl.games.services import NFLDataClient, today_et

    today = today_et()
    with NFLDataClient() as client:
        raw_games = client.get_games(_current_season(), game_date=today)

    if not raw_games:
        return 0

    count = 0
    changed_pks = []
    newly_final_pks = []

    for g in raw_games:
        external_id = g.pop("external_id")
        g.pop("home_team_external_id", None)
        g.pop("away_team_external_id", None)

        try:
            game_obj = Game.objects.get(external_id=external_id)
        except Game.DoesNotExist:
            continue

        new_status = g["status"]
        score_changed = (
            game_obj.home_score != g.get("home_score")
            or game_obj.away_score != g.get("away_score")
            or game_obj.status != new_status
        )

        was_live = game_obj.status in (
            GameStatus.IN_PROGRESS,
            GameStatus.HALFTIME,
            GameStatus.SCHEDULED,
        )
        is_now_final = new_status in (GameStatus.FINAL, GameStatus.FINAL_OT)

        # Build update fields from the normalized game data
        update_fields = {
            "home_score": g.get("home_score"),
            "away_score": g.get("away_score"),
            "status": new_status,
        }
        # Update quarter scores if present
        for qf in (
            "home_q1",
            "home_q2",
            "home_q3",
            "home_q4",
            "home_ot",
            "away_q1",
            "away_q2",
            "away_q3",
            "away_q4",
            "away_ot",
        ):
            if g.get(qf) is not None:
                update_fields[qf] = g[qf]

        Game.objects.filter(pk=game_obj.pk).update(**update_fields)
        count += 1

        if score_changed:
            changed_pks.append(game_obj.pk)

        if was_live and is_now_final and not game_obj.is_final:
            newly_final_pks.append(game_obj.pk)

    # Broadcast score updates via WebSocket
    if changed_pks:
        channel_layer = get_channel_layer()
        send = async_to_sync(channel_layer.group_send)

        for pk in changed_pks:
            try:
                game = Game.objects.select_related("home_team", "away_team").get(pk=pk)
            except Game.DoesNotExist:
                continue

            # Dashboard group
            send("nfl_live_scores", {"type": "score_update", "game_pk": pk})
            # Game detail group
            send(
                f"nfl_game_{game.id_hash}",
                {"type": "game_score_update", "game_pk": pk},
            )

            # Activity event for score changes
            ActivityEvent.objects.create(
                event_type=ActivityEvent.EventType.SCORE_CHANGE,
                message=(
                    f"{game.away_team.abbreviation} {game.away_score}"
                    f" - {game.home_team.abbreviation} {game.home_score}"
                ),
                url=game.get_absolute_url(),
                icon="football",
            )

    # Trigger settlement + standings update for newly-final games
    if newly_final_pks:
        from nfl.betting.tasks import settle_pending_bets

        settle_pending_bets.delay()
        fetch_standings.delay()

    logger.info(
        "sync_live_scores: updated %d games (%d changed)", count, len(changed_pks)
    )
    return count


def _current_season() -> int:
    """Return the NFL season year.

    NFL seasons start in September: Sep-Dec → current year, Jan-Aug → previous year.
    """
    from nfl.games.services import today_et

    today = today_et()
    if today.month >= 9:
        return today.year
    return today.year - 1
