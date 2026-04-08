.PHONY: up down restart logs shell migrations migrate seed lint format test test-ci tw tw-watch js js-watch

up:
	docker compose up --build -d
	docker compose run --rm tailwind tailwindcss \
		-i /packages/vinosports-core/src/vinosports/static/vinosports/css/tailwind.css \
		-o /packages/vinosports-core/src/vinosports/static/vinosports/css/tailwind-out.css \
		--minify

down:
	docker compose down

restart:
	docker compose down && docker compose up --build -d

logs:
	docker compose logs -f

shell:
	docker compose exec web bash

# Use exec (not run --rm) so migrations land in the volume-mounted source tree.
# vinosports-core is installed as an editable package (-e), so core app migrations
# (global_bots, users, betting, etc.) are written directly into
# packages/vinosports-core/src/vinosports/.../migrations/ — i.e., into the repo.
migrations:
	docker compose exec web python manage.py makemigrations

migrate:
	docker compose run --rm web python manage.py migrate --noinput

seed:
	docker compose exec web python manage.py seed
	docker compose exec web python manage.py seed_nba
	docker compose exec web python manage.py seed_nfl --offline
	docker compose exec web python manage.py seed_challenge_templates
	docker compose exec web python manage.py seed_challenges
	docker compose exec web python manage.py seed_epl_futures
	docker compose exec web python manage.py seed_nba_futures
	docker compose exec web python manage.py seed_nfl_futures
	docker compose exec web python manage.py seed_worldcup --offline --skip-odds
	docker compose exec web python manage.py seed_worldcup_futures
	docker compose exec web python manage.py seed_ucl --offline --skip-odds
	docker compose exec web python manage.py seed_ucl_futures

tw:
	docker compose exec tailwind tailwindcss \
		-i /packages/vinosports-core/src/vinosports/static/vinosports/css/tailwind.css \
		-o /packages/vinosports-core/src/vinosports/static/vinosports/css/tailwind-out.css \
		--minify

tw-watch:
	docker compose up tailwind

js:
	npx esbuild frontend/main.js \
		--bundle --minify --sourcemap \
		--outfile=packages/vinosports-core/src/vinosports/static/vinosports/js/app.js \
		--format=iife --target=es2020

js-watch:
	npx esbuild frontend/main.js \
		--bundle --sourcemap \
		--outfile=packages/vinosports-core/src/vinosports/static/vinosports/js/app.js \
		--format=iife --target=es2020 \
		--watch

lint:
	ruff check . --fix
	ruff format .

format:
	ruff format .

test:
	docker compose run --rm web python -m pytest -n auto --reuse-db

test-ci:
	docker compose run --rm web python -m pytest -n auto --dist worksteal --cov=vinosports --cov=hub --cov=nba --cov=epl --cov=nfl --cov=worldcup --cov=ucl --cov-report=term-missing:skip-covered --cov-config=pyproject.toml
