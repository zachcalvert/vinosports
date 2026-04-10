from django.apps import AppConfig


class BotsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vinosports.bots"
    label = "global_bots"
    verbose_name = "Bot Profiles"

    def ready(self):
        from django.apps import apps
        from django.db.models.signals import post_save

        from vinosports.bots.archive import (
            on_challenge_completed,
            on_reward_distributed,
        )

        RewardDistribution = apps.get_model("rewards", "RewardDistribution")
        post_save.connect(on_reward_distributed, sender=RewardDistribution)

        UserChallenge = apps.get_model("challenges", "UserChallenge")
        post_save.connect(on_challenge_completed, sender=UserChallenge)
