FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install vinosports-core first (changes less frequently)
COPY packages/vinosports-core /packages/vinosports-core
RUN pip install /packages/vinosports-core

# Install additional dependencies not in core
RUN pip install psycopg2-binary whitenoise

# Copy project code
COPY config/ config/
COPY epl/ epl/
COPY nba/ nba/
COPY hub/ hub/
COPY manage.py .

# Test/dev dependencies — opt-in via build arg (default off for production)
ARG INSTALL_TEST_DEPS=false
COPY requirements-test.txt .
RUN if [ "$INSTALL_TEST_DEPS" = "true" ]; then \
      pip install -r requirements-test.txt; \
    fi

# Collect static files at build time
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "--application-close-timeout", "10", "-t", "60", "config.asgi:application"]
