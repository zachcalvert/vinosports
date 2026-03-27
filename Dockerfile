FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install vinosports-core first (changes less frequently)
COPY packages/vinosports-core /packages/vinosports-core
RUN pip install -e /packages/vinosports-core

# Install additional dependencies
RUN pip install psycopg2-binary whitenoise gunicorn pytest pytest-django pytest-cov pytest-xdist factory-boy

# Copy project code
COPY config/ config/
COPY epl/ epl/
COPY nba/ nba/
COPY hub/ hub/
COPY manage.py .

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "--application-close-timeout", "10", "-t", "60", "config.asgi:application"]
