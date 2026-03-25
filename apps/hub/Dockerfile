FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install vinosports-core first (changes less frequently)
COPY packages/vinosports-core /packages/vinosports-core
RUN pip install -e /packages/vinosports-core

# Install hub-specific deps
COPY apps/hub/pyproject.toml ./
RUN pip install psycopg2-binary whitenoise

# Copy hub project code
COPY apps/hub/ .

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
