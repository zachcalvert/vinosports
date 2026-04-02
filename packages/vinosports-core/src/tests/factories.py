"""Model factories for vinosports-core tests."""

from decimal import Decimal

import factory
from django.utils import timezone

from vinosports.betting.models import Badge, UserBalance, UserStats
from vinosports.bots.models import BotProfile, ScheduleTemplate, StrategyType
from vinosports.challenges.models import Challenge, ChallengeTemplate, UserChallenge
from vinosports.rewards.models import Reward
from vinosports.users.models import User

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"coreuser{n}@test.com")
    display_name = factory.Sequence(lambda n: f"CoreUser{n}")
    is_bot = False

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        if not create:
            return
        self.set_password(extracted or "testpass123")
        self.save(update_fields=["password"])


class BotUserFactory(UserFactory):
    display_name = factory.Sequence(lambda n: f"Bot{n}")
    is_bot = True


# ---------------------------------------------------------------------------
# Balance / Stats
# ---------------------------------------------------------------------------


class UserBalanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserBalance

    user = factory.SubFactory(UserFactory)
    balance = Decimal("100000.00")


class UserStatsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserStats

    user = factory.SubFactory(UserFactory)
    total_bets = 0
    total_wins = 0
    total_losses = 0
    total_staked = Decimal("0.00")
    total_payout = Decimal("0.00")
    net_profit = Decimal("0.00")
    current_streak = 0
    best_streak = 0


class BadgeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Badge

    slug = factory.Sequence(lambda n: f"badge-{n}")
    name = factory.Sequence(lambda n: f"Badge {n}")
    description = "A test badge"
    icon = "trophy"
    rarity = Badge.Rarity.COMMON


# ---------------------------------------------------------------------------
# Bots
# ---------------------------------------------------------------------------


class ScheduleTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ScheduleTemplate

    name = factory.Sequence(lambda n: f"Template {n}")
    slug = factory.Sequence(lambda n: f"template-{n}")
    windows = factory.LazyFunction(
        lambda: [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": list(range(24)),
                "bet_probability": 0.8,
                "comment_probability": 0.8,
                "max_bets": 5,
                "max_comments": 3,
            }
        ]
    )


class BotProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BotProfile

    user = factory.SubFactory(BotUserFactory)
    strategy_type = StrategyType.FRONTRUNNER
    is_active = True
    risk_multiplier = 1.0
    max_daily_bets = 5
    persona_prompt = "You are a confident betting personality."


# ---------------------------------------------------------------------------
# Challenges
# ---------------------------------------------------------------------------


class ChallengeTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ChallengeTemplate

    slug = factory.Sequence(lambda n: f"challenge-template-{n}")
    title = factory.Sequence(lambda n: f"Challenge Template {n}")
    description = "A test challenge"
    icon = "target"
    challenge_type = ChallengeTemplate.ChallengeType.DAILY
    criteria_type = ChallengeTemplate.CriteriaType.BET_COUNT
    criteria_params = factory.LazyFunction(lambda: {"target": 3})
    reward_amount = Decimal("50.00")
    is_active = True


class ChallengeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Challenge

    template = factory.SubFactory(ChallengeTemplateFactory)
    status = Challenge.Status.ACTIVE
    starts_at = factory.LazyFunction(timezone.now)
    ends_at = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=1))


class UserChallengeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserChallenge

    user = factory.SubFactory(UserFactory)
    challenge = factory.SubFactory(ChallengeFactory)
    progress = 0
    target = 3
    status = UserChallenge.Status.IN_PROGRESS


# ---------------------------------------------------------------------------
# Rewards
# ---------------------------------------------------------------------------


class RewardFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Reward

    name = factory.Sequence(lambda n: f"Reward {n}")
    amount = Decimal("100.00")
    description = "A test reward"
    created_by = factory.SubFactory(UserFactory)
