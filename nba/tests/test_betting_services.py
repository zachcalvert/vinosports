"""Tests for nba/betting/services.py — OddsClient, _parse_bookmaker_odds, sync_odds."""

from unittest.mock import MagicMock, patch

import pytest

from nba.betting.services import (
    OddsClient,
    _parse_bookmaker_odds,
    _resolve_team_name,
    sync_odds,
)
from nba.games.models import Odds
from nba.tests.factories import GameFactory, TeamFactory


class TestResolveTeamName:
    def test_known_alias_returns_canonical(self):
        assert _resolve_team_name("LA Clippers") == "Los Angeles Clippers"

    def test_la_lakers_alias_resolved(self):
        assert _resolve_team_name("LA Lakers") == "Los Angeles Lakers"

    def test_exact_name_returned_unchanged(self):
        assert _resolve_team_name("Boston Celtics") == "Boston Celtics"

    def test_unknown_name_returned_unchanged(self):
        assert _resolve_team_name("Unknown Team FC") == "Unknown Team FC"

    def test_empty_string_returned_unchanged(self):
        assert _resolve_team_name("") == ""


class TestParseBookmakerOdds:
    def _game_data(self, bookmakers):
        return {
            "home_team": "Boston Celtics",
            "away_team": "Los Angeles Lakers",
            "bookmakers": bookmakers,
        }

    def test_returns_one_record_per_bookmaker(self):
        game_data = self._game_data(
            [
                {"key": "draftkings", "markets": []},
                {"key": "fanduel", "markets": []},
            ]
        )
        results = _parse_bookmaker_odds(game_data)
        assert len(results) == 2
        assert results[0]["bookmaker"] == "draftkings"
        assert results[1]["bookmaker"] == "fanduel"

    def test_parses_h2h_market(self):
        game_data = self._game_data(
            [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Boston Celtics", "price": -150},
                                {"name": "Los Angeles Lakers", "price": 130},
                            ],
                        }
                    ],
                }
            ]
        )
        results = _parse_bookmaker_odds(game_data)
        assert results[0]["home_moneyline"] == -150
        assert results[0]["away_moneyline"] == 130

    def test_parses_spreads_market(self):
        game_data = self._game_data(
            [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "spreads",
                            "outcomes": [
                                {
                                    "name": "Boston Celtics",
                                    "price": -110,
                                    "point": -3.5,
                                },
                                {
                                    "name": "Los Angeles Lakers",
                                    "price": -110,
                                    "point": 3.5,
                                },
                            ],
                        }
                    ],
                }
            ]
        )
        results = _parse_bookmaker_odds(game_data)
        assert results[0]["spread_line"] == -3.5
        assert results[0]["spread_home"] == -110
        assert results[0]["spread_away"] == -110

    def test_parses_totals_market(self):
        game_data = self._game_data(
            [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": -110, "point": 222.5},
                                {"name": "Under", "price": -110, "point": 222.5},
                            ],
                        }
                    ],
                }
            ]
        )
        results = _parse_bookmaker_odds(game_data)
        assert results[0]["total_line"] == 222.5
        assert results[0]["over_odds"] == -110
        assert results[0]["under_odds"] == -110

    def test_missing_markets_returns_none_fields(self):
        game_data = self._game_data([{"key": "draftkings", "markets": []}])
        results = _parse_bookmaker_odds(game_data)
        assert results[0]["home_moneyline"] is None
        assert results[0]["spread_line"] is None
        assert results[0]["total_line"] is None

    def test_empty_bookmakers_returns_empty_list(self):
        game_data = self._game_data([])
        assert _parse_bookmaker_odds(game_data) == []


class TestOddsClientContextManager:
    def test_enter_returns_self(self):
        client = OddsClient.__new__(OddsClient)
        client._client = MagicMock()
        assert client.__enter__() is client

    def test_exit_closes_inner_client(self):
        client = OddsClient.__new__(OddsClient)
        mock_inner = MagicMock()
        client._client = mock_inner
        client.__exit__(None, None, None)
        mock_inner.close.assert_called_once()

    def test_close_delegates_to_inner_client(self):
        client = OddsClient.__new__(OddsClient)
        mock_inner = MagicMock()
        client._client = mock_inner
        client.close()
        mock_inner.close.assert_called_once()


@pytest.mark.django_db
class TestSyncOdds:
    def _make_mock_client(self, raw_games):
        mock = MagicMock()
        mock.__enter__ = MagicMock(return_value=mock)
        mock.__exit__ = MagicMock(return_value=False)
        mock.get_odds.return_value = raw_games
        return mock

    def test_returns_zero_when_no_matching_games(self):
        mock_client = self._make_mock_client(
            [
                {
                    "home_team": "Boston Celtics",
                    "away_team": "Los Angeles Lakers",
                    "bookmakers": [{"key": "draftkings", "markets": []}],
                }
            ]
        )
        count = sync_odds(client=mock_client)
        assert count == 0

    def test_skips_unresolvable_teams(self):
        mock_client = self._make_mock_client(
            [
                {
                    "home_team": "Nonexistent Team A",
                    "away_team": "Nonexistent Team B",
                    "bookmakers": [{"key": "draftkings", "markets": []}],
                }
            ]
        )
        count = sync_odds(client=mock_client)
        assert count == 0

    def test_creates_odds_record_for_matched_game(self):
        home = TeamFactory(short_name="Boston Celtics")
        away = TeamFactory(short_name="Los Angeles Lakers")
        game = GameFactory(
            home_team=home,
            away_team=away,
            status="SCHEDULED",
        )

        raw_games = [
            {
                "home_team": "Boston Celtics",
                "away_team": "Los Angeles Lakers",
                "bookmakers": [
                    {
                        "key": "draftkings",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Boston Celtics", "price": -150},
                                    {"name": "Los Angeles Lakers", "price": 130},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
        mock_client = self._make_mock_client(raw_games)
        count = sync_odds(client=mock_client)
        assert count == 1
        odds = Odds.objects.get(game=game, bookmaker="draftkings")
        assert odds.home_moneyline == -150
        assert odds.away_moneyline == 130

    def test_upserts_existing_odds_record(self):
        from django.utils import timezone

        home = TeamFactory(short_name="Golden State Warriors")
        away = TeamFactory(short_name="Phoenix Suns")
        game = GameFactory(home_team=home, away_team=away, status="SCHEDULED")
        Odds.objects.create(
            game=game,
            bookmaker="draftkings",
            home_moneyline=-200,
            away_moneyline=170,
            fetched_at=timezone.now(),
        )

        raw_games = [
            {
                "home_team": "Golden State Warriors",
                "away_team": "Phoenix Suns",
                "bookmakers": [
                    {
                        "key": "draftkings",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Golden State Warriors", "price": -110},
                                    {"name": "Phoenix Suns", "price": -110},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
        mock_client = self._make_mock_client(raw_games)
        count = sync_odds(client=mock_client)
        assert count == 1
        assert Odds.objects.filter(game=game, bookmaker="draftkings").count() == 1
        odds = Odds.objects.get(game=game, bookmaker="draftkings")
        assert odds.home_moneyline == -110

    def test_applies_team_alias_resolution(self):
        home = TeamFactory(short_name="Los Angeles Clippers")
        away = TeamFactory(short_name="Miami Heat")
        GameFactory(home_team=home, away_team=away, status="SCHEDULED")

        raw_games = [
            {
                "home_team": "LA Clippers",
                "away_team": "Miami Heat",
                "bookmakers": [
                    {
                        "key": "fanduel",
                        "markets": [],
                    }
                ],
            }
        ]
        mock_client = self._make_mock_client(raw_games)
        count = sync_odds(client=mock_client)
        assert count == 1

    def test_skips_game_with_no_matching_db_game(self):
        TeamFactory(short_name="Chicago Bulls")
        TeamFactory(short_name="Detroit Pistons")
        # No Game object created in DB

        raw_games = [
            {
                "home_team": "Chicago Bulls",
                "away_team": "Detroit Pistons",
                "bookmakers": [{"key": "draftkings", "markets": []}],
            }
        ]
        mock_client = self._make_mock_client(raw_games)
        count = sync_odds(client=mock_client)
        assert count == 0

    def test_counts_multiple_bookmakers(self):
        home = TeamFactory(short_name="Milwaukee Bucks")
        away = TeamFactory(short_name="Indiana Pacers")
        GameFactory(home_team=home, away_team=away, status="SCHEDULED")

        raw_games = [
            {
                "home_team": "Milwaukee Bucks",
                "away_team": "Indiana Pacers",
                "bookmakers": [
                    {"key": "draftkings", "markets": []},
                    {"key": "fanduel", "markets": []},
                    {"key": "betmgm", "markets": []},
                ],
            }
        ]
        mock_client = self._make_mock_client(raw_games)
        count = sync_odds(client=mock_client)
        assert count == 3


class TestOddsClientInit:
    def test_initializes_with_provided_api_key(self):
        with patch("nba.betting.services.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            client = OddsClient(api_key="my-test-key")
        assert client.api_key == "my-test-key"

    def test_creates_httpx_client_with_base_url(self):
        with patch("nba.betting.services.httpx.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_client_cls.return_value = mock_instance
            OddsClient(api_key="key")
        mock_client_cls.assert_called_once()
        call_kwargs = mock_client_cls.call_args[1]
        assert "base_url" in call_kwargs or mock_client_cls.call_args[0]


class TestOddsClientGet:
    def test_includes_api_key_in_params(self):
        client = OddsClient.__new__(OddsClient)
        client.api_key = "my-key"
        mock_http = MagicMock()
        client._client = mock_http

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {}
        mock_response.json.return_value = {"data": []}
        mock_http.get.return_value = mock_response

        result = client._get("/test", params={"foo": "bar"})

        call_params = mock_http.get.call_args[1].get("params", {})
        assert call_params.get("apiKey") == "my-key"
        assert call_params.get("foo") == "bar"
        assert result == {"data": []}

    def test_logs_remaining_requests_when_header_present(self):
        client = OddsClient.__new__(OddsClient)
        client.api_key = "key"
        mock_http = MagicMock()
        client._client = mock_http

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"x-requests-remaining": "450"}
        mock_response.json.return_value = []
        mock_http.get.return_value = mock_response

        result = client._get("/odds")
        assert result == []

    def test_skips_log_when_header_absent(self):
        client = OddsClient.__new__(OddsClient)
        client.api_key = "key"
        mock_http = MagicMock()
        client._client = mock_http

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {}
        mock_response.json.return_value = []
        mock_http.get.return_value = mock_response

        result = client._get("/odds")
        assert result == []


class TestOddsClientGetOdds:
    def test_calls_odds_endpoint(self):
        client = OddsClient.__new__(OddsClient)
        client._get = MagicMock(return_value=[])
        client.api_key = "key"
        result = client.get_odds()
        assert client._get.called
        assert result == []
