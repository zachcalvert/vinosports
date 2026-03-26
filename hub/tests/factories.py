"""Model factories for hub tests."""

from decimal import Decimal

import factory

from vinosports.betting.models import UserBalance
from vinosports.users.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"hubuser{n}@test.com")
    display_name = factory.Sequence(lambda n: f"HubUser{n}")
    is_bot = False

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        if not create:
            return
        self.set_password(extracted or "testpass123")
        self.save(update_fields=["password"])


class UserBalanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserBalance

    user = factory.SubFactory(UserFactory)
    balance = Decimal("1000.00")
