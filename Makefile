.PHONY: up down restart logs shell migrate seed lint format test test-ci

up:
	docker compose up --build -d

down:
	docker compose down

restart:
	docker compose down && docker compose up --build -d

logs:
	docker compose logs -f

shell:
	docker compose exec web bash

migrate:
	docker compose run --rm web python manage.py migrate --noinput

seed:
	docker compose exec web python manage.py seed
	docker compose exec web python manage.py seed_nba
	docker compose exec web python manage.py seed_challenge_templates
	docker compose exec web python manage.py seed_challenges
	docker compose exec web python manage.py seed_epl_futures
	docker compose exec web python manage.py seed_nba_futures

lint:
	ruff check . --fix
	ruff format .

format:
	ruff format .

test:
	docker compose run --rm web python -m pytest -n auto --reuse-db

test-ci:
	docker compose run --rm web python -m pytest -n auto --dist worksteal --cov=vinosports --cov=hub --cov=nba --cov=epl --cov=nfl --cov-report=term-missing:skip-covered --cov-config=pyproject.toml
