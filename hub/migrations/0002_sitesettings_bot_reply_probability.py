from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hub", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="bot_reply_probability",
            field=models.FloatField(
                default=0.7,
                help_text="Probability a bot replies to a human comment (0.0-1.0).",
            ),
        ),
    ]
