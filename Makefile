.PHONY: up down restart logs shell-epl shell-nba shell-hub migrate migrate-epl migrate-nba seed seed-epl seed-nba lint format test

up:
	docker compose up --build -d

down:
	docker compose down

restart:
	docker compose down && docker compose up --build -d

logs:
	docker compose logs -f

shell-epl:
	docker compose exec epl-web bash

shell-nba:
	docker compose exec nba-web bash

shell-hub:
	docker compose exec hub-web bash

migrate: migrate-epl migrate-nba

migrate-epl:
	docker compose run --rm epl-web python manage.py migrate --noinput

migrate-nba:
	docker compose run --rm nba-web python manage.py migrate --noinput

seed: seed-epl seed-nba

seed-epl:
	docker compose exec epl-web python manage.py seed

seed-nba:
	docker compose exec nba-web python manage.py seed_nba
	docker compose exec nba-web python manage.py seed_challenge_templates

lint:
	ruff check . --fix
	ruff format .

format:
	ruff format .

test:
	docker compose run --rm epl-web python -m pytest
	docker compose run --rm nba-web python -m pytest

test-epl:
	docker compose run --rm epl-web python -m pytest

test-nba:
	docker compose run --rm nba-web python -m pytest --cov-report=term-missing

