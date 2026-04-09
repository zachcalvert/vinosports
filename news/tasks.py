"""Celery tasks for news article generation."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from news.models import NewsArticle

logger = logging.getLogger(__name__)


@shared_task
def generate_pending_recaps():
    """
    Poll all leagues for recently completed games without recaps.
    Dispatches async generation tasks for each.

    Runs hourly at :45 (offset from postgame comments at :30/:35).
    """
    cutoff = timezone.now() - timedelta(hours=24)
    cutoff_date = cutoff.date()

    dispatched = 0

    # --- EPL ---
    try:
        from epl.matches.models import Match

        epl_existing = set(
            NewsArticle.objects.filter(
                article_type=NewsArticle.ArticleType.RECAP,
                league="epl",
                created_at__gte=cutoff,
            ).values_list("game_id_hash", flat=True)
        )
        epl_matches = Match.objects.filter(
            status=Match.Status.FINISHED,
            kickoff__gte=cutoff,
        ).exclude(id_hash__in=epl_existing)
        for match in epl_matches:
            generate_game_recap_task.delay(match.id_hash, "epl")
            dispatched += 1
    except Exception as exc:
        logger.error("Error querying EPL matches for recaps: %s", exc)

    # --- NBA ---
    try:
        from nba.games.models import Game, GameStatus

        nba_existing = set(
            NewsArticle.objects.filter(
                article_type=NewsArticle.ArticleType.RECAP,
                league="nba",
                created_at__gte=cutoff,
            ).values_list("game_id_hash", flat=True)
        )
        nba_games = Game.objects.filter(
            status=GameStatus.FINAL,
            game_date__gte=cutoff_date,
        ).exclude(id_hash__in=nba_existing)
        for game in nba_games:
            generate_game_recap_task.delay(game.id_hash, "nba")
            dispatched += 1
    except Exception as exc:
        logger.error("Error querying NBA games for recaps: %s", exc)

    # --- NFL ---
    try:
        from nfl.games.models import Game as NflGame
        from nfl.games.models import GameStatus as NflGameStatus

        nfl_existing = set(
            NewsArticle.objects.filter(
                article_type=NewsArticle.ArticleType.RECAP,
                league="nfl",
                created_at__gte=cutoff,
            ).values_list("game_id_hash", flat=True)
        )
        nfl_games = NflGame.objects.filter(
            status__in=[NflGameStatus.FINAL, NflGameStatus.FINAL_OT],
            game_date__gte=cutoff_date,
        ).exclude(id_hash__in=nfl_existing)
        for game in nfl_games:
            generate_game_recap_task.delay(game.id_hash, "nfl")
            dispatched += 1
    except Exception as exc:
        logger.error("Error querying NFL games for recaps: %s", exc)

    logger.info("generate_pending_recaps: dispatched %d recap tasks", dispatched)
    return {"dispatched": dispatched}


@shared_task(bind=True, max_retries=1, default_retry_delay=300)
def generate_cross_league_task(self):
    """
    Generate a cross-league weekend preview article.
    Runs Friday 10am ET via Celery beat. Articles start as drafts for admin review.
    """
    from news.article_service import generate_cross_league_article

    try:
        article = generate_cross_league_article()
    except Exception as exc:
        logger.error("Cross-league generation failed: error=%s", exc)
        raise self.retry(exc=exc)

    if article:
        logger.info("Cross-league article created: %s (draft)", article.id_hash)
        return {"status": "created", "article_id": article.id_hash}
    return {"status": "skipped"}


@shared_task(bind=True, max_retries=1, default_retry_delay=300)
def generate_betting_trend_task(self, league):
    """
    Generate a mid-week betting trend article for a single league.
    Runs Wednesday 10am ET via Celery beat. Articles start as drafts for admin review.
    """
    from news.article_service import generate_betting_trend

    try:
        article = generate_betting_trend(league)
    except Exception as exc:
        logger.error("Trend generation failed: league=%s, error=%s", league, exc)
        raise self.retry(exc=exc)

    if article:
        logger.info(
            "Trend created: league=%s, article=%s (draft)",
            league,
            article.id_hash,
        )
        return {"status": "created", "article_id": article.id_hash}
    return {"status": "skipped"}


@shared_task(bind=True, max_retries=1, default_retry_delay=300)
def generate_weekly_roundup_task(self, league):
    """
    Generate a weekly roundup article for a single league.
    Runs Monday 10am ET via Celery beat. Articles start as drafts for admin review.
    """
    from news.article_service import generate_weekly_roundup

    try:
        article = generate_weekly_roundup(league)
    except Exception as exc:
        logger.error("Roundup generation failed: league=%s, error=%s", league, exc)
        raise self.retry(exc=exc)

    if article:
        logger.info(
            "Roundup created: league=%s, article=%s (draft)",
            league,
            article.id_hash,
        )
        return {"status": "created", "article_id": article.id_hash}
    return {"status": "skipped"}


@shared_task(bind=True, max_retries=1, default_retry_delay=300)
def generate_league_preview_task(self, league):
    """
    Generate a league/tournament preview article.
    Triggered manually via management command. Articles start as drafts for admin review.
    """
    from news.article_service import generate_league_preview

    try:
        article = generate_league_preview(league)
    except Exception as exc:
        logger.error("Preview generation failed: league=%s, error=%s", league, exc)
        raise self.retry(exc=exc)

    if article:
        logger.info(
            "Preview created: league=%s, article=%s (draft)",
            league,
            article.id_hash,
        )
        return {"status": "created", "article_id": article.id_hash}
    return {"status": "skipped"}


@shared_task(bind=True, max_retries=1, default_retry_delay=300)
def generate_game_recap_task(self, game_id_hash, league):
    """
    Generate a recap article for a single completed game.
    Resolves the game object from id_hash + league, then calls the service.
    """
    from news.article_service import generate_game_recap

    game_obj = _resolve_game(game_id_hash, league)
    if game_obj is None:
        logger.warning("Game not found: id_hash=%s, league=%s", game_id_hash, league)
        return {"status": "not_found"}

    try:
        article = generate_game_recap(league, game_obj)
    except Exception as exc:
        logger.error(
            "Recap generation failed: league=%s, game=%s, error=%s",
            league,
            game_id_hash,
            exc,
        )
        raise self.retry(exc=exc)

    if article:
        return {"status": "created", "article_id": article.id_hash}
    return {"status": "skipped"}


def _resolve_game(game_id_hash, league):
    """Resolve a game/match object from id_hash and league string."""
    if league == "epl":
        from epl.matches.models import Match

        try:
            return Match.objects.select_related("home_team", "away_team").get(
                id_hash=game_id_hash
            )
        except (Match.DoesNotExist, ValueError):
            logger.info("EPL match not found: id_hash=%s", game_id_hash)
            return None
    elif league == "nba":
        from nba.games.models import Game

        try:
            return Game.objects.select_related("home_team", "away_team").get(
                id_hash=game_id_hash
            )
        except (Game.DoesNotExist, ValueError):
            logger.info("NBA game not found: id_hash=%s", game_id_hash)
            return None
    elif league == "nfl":
        from nfl.games.models import Game

        try:
            return Game.objects.select_related("home_team", "away_team").get(
                id_hash=game_id_hash
            )
        except (Game.DoesNotExist, ValueError):
            logger.info("NFL game not found: id_hash=%s", game_id_hash)
            return None

    logger.warning("Unknown league for game resolution: %s", league)
    return None
