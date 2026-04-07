from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("global_bots", "0004_botprofile_active_in_worldcup"),
    ]

    operations = [
        migrations.AddField(
            model_name="botprofile",
            name="worldcup_country_code",
            field=models.CharField(
                blank=True,
                help_text="ISO 3166-1 alpha-3 country code of favourite World Cup team (e.g. BRA, FRA).",
                max_length=3,
                verbose_name="World Cup country code",
            ),
        ),
    ]
