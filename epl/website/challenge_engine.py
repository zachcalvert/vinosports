"""Backward-compat shim — engine moved to vinosports.challenges.engine."""

from vinosports.challenges.engine import (  # noqa: F401
    EVALUATORS,
    PLACEMENT_EVENTS,
    SETTLEMENT_EVENTS,
    _apply_progress,
    _eval_bet_all_matches,
    _eval_bet_count,
    _eval_bet_on_underdog,
    _eval_correct_predictions,
    _eval_parlay_placed,
    _eval_parlay_won,
    _eval_total_staked,
    _eval_win_count,
    _eval_win_streak,
    update_challenge_progress,
)
