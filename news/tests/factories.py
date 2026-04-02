"""Model factories for news tests."""

import factory
from django.utils import timezone

from news.models import NewsArticle
from vinosports.bots.models import BotProfile, StrategyType
from vinosports.users.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"newsuser{n}@test.com")
    display_name = factory.Sequence(lambda n: f"NewsUser{n}")
    is_bot = False

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        if not create:
            return
        self.set_password(extracted or "testpass123")
        self.save(update_fields=["password"])


class BotUserFactory(UserFactory):
    display_name = factory.Sequence(lambda n: f"NewsBot{n}")
    is_bot = True


class NewsArticleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NewsArticle

    league = "nba"
    author = factory.SubFactory(BotUserFactory)
    article_type = NewsArticle.ArticleType.RECAP
    title = factory.Sequence(lambda n: f"Test Article {n}")
    subtitle = "A test subtitle"
    body = "This is the article body with enough content to be meaningful."
    status = NewsArticle.Status.PUBLISHED
    published_at = factory.LazyFunction(timezone.now)


class DraftArticleFactory(NewsArticleFactory):
    status = NewsArticle.Status.DRAFT
    published_at = None


class BotProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BotProfile

    user = factory.SubFactory(BotUserFactory)
    strategy_type = StrategyType.HOMER
    is_active = True
    active_in_epl = True
    active_in_nba = True
    active_in_nfl = True
    risk_multiplier = 1.0
    max_daily_bets = 5
    persona_prompt = "You are an opinionated sports commentator."
