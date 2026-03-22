FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install vinosports-core first (changes less frequently)
COPY packages/vinosports-core /packages/vinosports-core
RUN pip install /packages/vinosports-core

# Install league-specific deps
COPY apps/epl/pyproject.toml ./
RUN pip install psycopg2-binary whitenoise gunicorn

# Copy league project code
COPY apps/epl/ .

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "--application-close-timeout", "10", "-t", "60", "config.asgi:application"]
