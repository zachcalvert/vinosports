FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install curl (Tailwind CLI) + Node.js (npm for esbuild)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Download Tailwind CSS standalone CLI
RUN curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64 \
    && chmod +x tailwindcss-linux-x64 \
    && mv tailwindcss-linux-x64 /usr/local/bin/tailwindcss

# Install JS dependencies
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Install vinosports-core first (changes less frequently)
# Editable install so Django resolves imports from /packages/vinosports-core/src,
# which is volume-mounted in dev — migrations for core apps land in the repo.
COPY packages/vinosports-core /packages/vinosports-core
RUN pip install -e /packages/vinosports-core

# Install additional dependencies not in core
RUN pip install psycopg2-binary whitenoise

# Copy project code
COPY config/ config/
COPY epl/ epl/
COPY nba/ nba/
COPY nfl/ nfl/
COPY worldcup/ worldcup/
COPY ucl/ ucl/
COPY hub/ hub/
COPY news/ news/
COPY reddit/ reddit/
COPY manage.py .
COPY tailwind.config.js .
COPY frontend/ frontend/

# Test/dev dependencies — opt-in via build arg (default off for production)
ARG INSTALL_TEST_DEPS=false
COPY requirements-test.txt .
RUN if [ "$INSTALL_TEST_DEPS" = "true" ]; then \
      pip install -r requirements-test.txt; \
    fi

# Build Tailwind CSS
RUN tailwindcss -i /packages/vinosports-core/src/vinosports/static/vinosports/css/tailwind.css \
    -o /packages/vinosports-core/src/vinosports/static/vinosports/css/tailwind-out.css \
    --minify

# Build JS bundle
RUN npx esbuild frontend/main.js \
    --bundle --minify --sourcemap \
    --outfile=/packages/vinosports-core/src/vinosports/static/vinosports/js/app.js \
    --format=iife --target=es2020

# Collect static files at build time (WhiteNoise manifest for hashed filenames)
RUN SECRET_KEY=build-only WHITENOISE_MANIFEST=1 python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "--application-close-timeout", "10", "-t", "60", "config.asgi:application"]
