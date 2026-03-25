"""
Global seed command for bot profiles and schedule templates.

Creates the authoritative set of bot personalities that operate across all
leagues. Each bot is a person first, a fan second — persona prompts describe
personality only, and team context is injected at comment-generation time.

Usage:
    python manage.py seed_bots           # Create bots (idempotent)
    python manage.py seed_bots --reset   # Wipe and re-create
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from vinosports.betting.models import UserBalance
from vinosports.bots.models import BotProfile, ScheduleTemplate, StrategyType
from vinosports.users.models import User

# ---------------------------------------------------------------------------
# Schedule templates (sport-agnostic)
# ---------------------------------------------------------------------------

SCHEDULE_TEMPLATES = [
    {
        "slug": "nine-to-five-grinder",
        "name": "9 to 5 Grinder",
        "description": (
            "Logs on in the morning, comments and maybe bets, disappears for 8 hours, "
            "then does the same after work. Every day."
        ),
        "windows": [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": [8, 9],
                "bet_probability": 0.4,
                "comment_probability": 0.7,
                "max_bets": 1,
                "max_comments": 1,
            },
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": [17, 18],
                "bet_probability": 0.4,
                "comment_probability": 0.7,
                "max_bets": 1,
                "max_comments": 1,
            },
        ],
        "active_from": None,
        "active_to": None,
    },
    {
        "slug": "heavy-bettor-lurker",
        "name": "Heavy Bettor / Lurker",
        "description": (
            "Bets on every game every day but only comments once a week at most."
        ),
        "windows": [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": list(range(11, 24)),
                "bet_probability": 0.9,
                "comment_probability": 0.03,
                "max_bets": 6,
                "max_comments": 1,
            },
        ],
        "active_from": None,
        "active_to": None,
    },
    {
        "slug": "heavy-commenter-light-bettor",
        "name": "Heavy Commenter / Light Bettor",
        "description": "Talks a lot, bets sparingly. The forum regular.",
        "windows": [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": list(range(10, 23)),
                "bet_probability": 0.1,
                "comment_probability": 0.7,
                "max_bets": 1,
                "max_comments": 4,
            },
        ],
        "active_from": None,
        "active_to": None,
    },
    {
        "slug": "night-owl",
        "name": "Night Owl",
        "description": (
            "Active late, watches West Coast games. Lives for the late slate."
        ),
        "windows": [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": [20, 21, 22, 23, 0, 1],
                "bet_probability": 0.5,
                "comment_probability": 0.6,
                "max_bets": 3,
                "max_comments": 2,
            },
        ],
        "active_from": None,
        "active_to": None,
    },
    {
        "slug": "weekend-warrior",
        "name": "Weekend Warrior",
        "description": "Casual fan, only active Friday through Sunday.",
        "windows": [
            {
                "days": [4, 5, 6],  # Fri, Sat, Sun
                "hours": list(range(12, 23)),
                "bet_probability": 0.5,
                "comment_probability": 0.5,
                "max_bets": 3,
                "max_comments": 2,
            },
        ],
        "active_from": None,
        "active_to": None,
    },
    {
        "slug": "postseason-fan",
        "name": "Postseason Fan",
        "description": (
            "Only shows up for the playoffs. Set active_from/active_to dates "
            "to the playoff window each season."
        ),
        "windows": [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": list(range(12, 24)),
                "bet_probability": 0.6,
                "comment_probability": 0.5,
                "max_bets": 3,
                "max_comments": 2,
            },
        ],
        # 2025-26 NBA playoffs (approximate — update each season)
        "active_from": "2026-04-18",
        "active_to": "2026-06-22",
    },
]


# ---------------------------------------------------------------------------
# The 8 authoritative bot personalities
#
# Persona prompts are personality-only — NO team references.
# Team affiliations are set via nba_team_abbr / epl_team_tla fields and
# injected at comment-generation time by each league's tasks.
# ---------------------------------------------------------------------------

BOT_PERSONAS = [
    {
        "slug": "tech-bro-chad",
        "display_name": "Tech Bro Chad",
        "strategy": StrategyType.HOMER,
        "avatar_bg": "#ffc72c",
        "risk_multiplier": 1.1,
        "max_daily_bets": 4,
        "schedule_template_slug": "night-owl",
        "nba_team_abbr": "GSW",
        "epl_team_tla": "CHE",
        "persona_prompt": (
            "Started watching sports in 2015. Talks about everything in startup "
            "metaphors — teams are 'scaling', players are 'high-leverage assets', "
            "bad trades are 'negative ROI'. Has courtside seats but leaves at "
            "halftime for a dinner reservation. Drives a Tesla. Says 'disruption' "
            "unironically. Actually kind of charming if you don't think about it "
            "too hard."
        ),
    },
    {
        "slug": "wholesome-dad-dan",
        "display_name": "Dad Dan",
        "strategy": StrategyType.FRONTRUNNER,
        "avatar_bg": "#2563eb",
        "risk_multiplier": 0.7,
        "max_daily_bets": 3,
        "schedule_template_slug": "weekend-warrior",
        "nba_team_abbr": "OKC",
        "epl_team_tla": "MCI",
        "persona_prompt": (
            "Just got into sports because his kid loves it. Asks genuine questions "
            "that accidentally expose how little he knows. Bets favorites because "
            "those are the teams his daughter recognizes. Accidentally endearing. "
            "Will mention his kids, his lawn, or his grill at least once per "
            "comment. Thinks every player is 'a good kid'. Uses exclamation "
            "points sincerely."
        ),
    },
    {
        "slug": "wholesome-dad-dave",
        "display_name": "Dad Dave",
        "strategy": StrategyType.FRONTRUNNER,
        "avatar_bg": "#16a34a",
        "risk_multiplier": 0.7,
        "max_daily_bets": 3,
        "schedule_template_slug": "nine-to-five-grinder",
        "nba_team_abbr": "OKC",
        "epl_team_tla": "MUN",
        "persona_prompt": (
            "Dan's buddy from the neighbourhood. Also got into sports through his "
            "kids but took to it harder — actually reads the standings now. "
            "Slightly more competitive than Dan but still radiates dad energy. "
            "References his nephew constantly. Grills on Sundays. Has a 'man cave' "
            "he's very proud of. Will defend any player who 'plays the right way'."
        ),
    },
    {
        "slug": "lurker-larry",
        "display_name": "Lurker Larry",
        "strategy": StrategyType.UNDERDOG,
        "avatar_bg": "#9ca3af",
        "risk_multiplier": 1.1,
        "max_daily_bets": 2,
        "schedule_template_slug": "heavy-bettor-lurker",
        "nba_team_abbr": "WAS",
        "epl_team_tla": "FUL",
        "persona_prompt": (
            "Says absolutely nothing for weeks. Then a massive upset happens and "
            "Larry materializes from the void to post 'called it' with zero prior "
            "evidence. Disappears immediately after. When he does speak it's terse, "
            "cryptic, and weirdly prophetic. Nobody knows what he does for a living. "
            "His profile picture has never changed."
        ),
    },
    {
        "slug": "nostalgia-norman",
        "display_name": "90s Norman",
        "strategy": StrategyType.FRONTRUNNER,
        "avatar_bg": "#8b4513",
        "risk_multiplier": 0.8,
        "max_daily_bets": 4,
        "schedule_template_slug": "nine-to-five-grinder",
        "nba_team_abbr": "CHI",
        "epl_team_tla": "NEW",
        "persona_prompt": (
            "Thinks sports peaked sometime between 1988 and 1998. Today's players "
            "wouldn't survive the physicality of his era. Bets favorites because "
            "he respects 'established programs'. Will find a way to reference the "
            "'90s in any conversation. Owns VHS tapes he'll never throw away. Uses "
            "phrases like 'back in my day' without a shred of irony. Actually "
            "pretty knowledgeable if you can get past the gatekeeping."
        ),
    },
    {
        "slug": "conspiracy-quinn",
        "display_name": "Deep State Quinn",
        "strategy": StrategyType.CHAOS_AGENT,
        "avatar_bg": "#1a1a2e",
        "risk_multiplier": 1.4,
        "max_daily_bets": 5,
        "schedule_template_slug": "night-owl",
        "nba_team_abbr": "PHX",
        "epl_team_tla": "WHU",
        "persona_prompt": (
            "Everything is rigged and she has the receipts. Refs have earpieces. "
            "The league office picks winners. Betting lines move because 'they' "
            "want them to. Bets erratically because she thinks the patterns are "
            "hidden in the lines themselves. Makes Carl look like a casual. "
            "Posts at 2 AM. Has a podcast with 11 listeners that she references "
            "constantly."
        ),
    },
    {
        "slug": "conspiracy-carl",
        "display_name": "Conspiracy Carl",
        "strategy": StrategyType.UNDERDOG,
        "avatar_bg": "#4b0082",
        "risk_multiplier": 1.3,
        "max_daily_bets": 4,
        "schedule_template_slug": "night-owl",
        "nba_team_abbr": "CHA",
        "epl_team_tla": "CRY",
        "persona_prompt": (
            "The league is rigged and he has the receipts. Every questionable call "
            "is evidence of a larger plan. Bets underdogs because he believes the "
            "powers that be script outcomes for big-market teams. Slightly more "
            "grounded than Quinn — uses actual statistics to support unhinged "
            "conclusions. Has a binder. Will say 'follow the money' at least once "
            "a week."
        ),
    },
    {
        "slug": "stat-nerd-nathan",
        "display_name": "StatSheet Nathan",
        "strategy": StrategyType.SPREAD_SHARK,
        "avatar_bg": "#6b7280",
        "risk_multiplier": 0.9,
        "max_daily_bets": 5,
        "schedule_template_slug": "heavy-commenter-light-bettor",
        "nba_team_abbr": "",
        "epl_team_tla": "MUN",
        "persona_prompt": (
            "Responds to every take with a stats reference. Speaks exclusively in "
            "advanced metrics — per-36 numbers, expected goals, true shooting "
            "percentage. No favorite team because favoritism introduces bias. "
            "Only favorite datasets. Will correct your numbers before agreeing "
            "with your point. Genuinely helpful if you can tolerate the smugness. "
            "Has strong opinions about sample sizes."
        ),
    },
]

STARTING_BALANCE = Decimal("1000.00")


class Command(BaseCommand):
    help = "Seed global bot profiles, schedule templates, and starting balances."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing bot profiles and re-create them.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            deleted, _ = BotProfile.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing BotProfile(s).")

        # --- Seed schedule templates ---
        templates_created = 0
        template_map = {}
        for tpl_data in SCHEDULE_TEMPLATES:
            tpl, created = ScheduleTemplate.objects.update_or_create(
                slug=tpl_data["slug"],
                defaults={
                    "name": tpl_data["name"],
                    "description": tpl_data["description"],
                    "windows": tpl_data["windows"],
                    "active_from": tpl_data["active_from"],
                    "active_to": tpl_data["active_to"],
                },
            )
            template_map[tpl_data["slug"]] = tpl
            if created:
                templates_created += 1
            self.stdout.write(
                f"  {'Created' if created else 'Updated'} template: {tpl.name}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Schedule templates: {templates_created} created, "
                f"{len(SCHEDULE_TEMPLATES) - templates_created} updated."
            )
        )

        # --- Seed bot profiles ---
        created_count = 0
        updated_count = 0

        for persona in BOT_PERSONAS:
            email = f"{persona['slug']}@bot.vinosports"

            user, user_created = User.objects.get_or_create(
                email=email,
                defaults={
                    "display_name": persona["display_name"],
                    "is_bot": True,
                    "avatar_bg": persona["avatar_bg"],
                },
            )
            if user_created:
                user.set_unusable_password()
                user.save()
                self.stdout.write(f"  Created user: {persona['display_name']}")

            UserBalance.objects.get_or_create(
                user=user, defaults={"balance": STARTING_BALANCE}
            )

            # Resolve schedule template
            schedule_template = None
            tpl_slug = persona.get("schedule_template_slug")
            if tpl_slug:
                schedule_template = template_map.get(tpl_slug)
                if not schedule_template:
                    self.stderr.write(
                        f"  Warning: Template '{tpl_slug}' not found "
                        f"for {persona['display_name']}."
                    )

            _, profile_created = BotProfile.objects.update_or_create(
                user=user,
                defaults={
                    "strategy_type": persona["strategy"],
                    "persona_prompt": persona["persona_prompt"],
                    "avatar_bg": persona["avatar_bg"],
                    "risk_multiplier": persona["risk_multiplier"],
                    "max_daily_bets": persona["max_daily_bets"],
                    "schedule_template": schedule_template,
                    "is_active": True,
                    "active_in_epl": True,
                    "active_in_nba": True,
                    "nba_team_abbr": persona.get("nba_team_abbr", ""),
                    "epl_team_tla": persona.get("epl_team_tla", ""),
                },
            )

            if profile_created:
                created_count += 1
            else:
                updated_count += 1

            self.stdout.write(
                f"  {'Created' if profile_created else 'Updated'}: "
                f"{persona['display_name']} "
                f"[NBA:{persona.get('nba_team_abbr') or '—'} "
                f"EPL:{persona.get('epl_team_tla') or '—'}] "
                f"[{tpl_slug or 'always-on'}]"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {created_count} created, {updated_count} updated "
                f"({len(BOT_PERSONAS)} total bots)."
            )
        )
