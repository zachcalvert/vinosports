from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nfl_bots", "0002_initial_models"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="botcomment",
            name="unique_nfl_bot_comment_per_trigger",
        ),
        migrations.AlterField(
            model_name="botcomment",
            name="trigger_type",
            field=models.CharField(
                choices=[
                    ("PRE_MATCH", "Pre-match hype"),
                    ("POST_BET", "Post-bet reaction"),
                    ("POST_MATCH", "Post-match reaction"),
                    ("REPLY", "Reply to comment"),
                    ("CONVERSATION", "Multi-turn conversation"),
                ],
                max_length=20,
                verbose_name="trigger type",
            ),
        ),
        migrations.AddConstraint(
            model_name="botcomment",
            constraint=models.UniqueConstraint(
                condition=~models.Q(trigger_type="CONVERSATION"),
                fields=("user", "game", "trigger_type"),
                name="unique_nfl_bot_comment_per_trigger",
            ),
        ),
    ]
