#!/bin/sh
set -e

# ponytail: migrate in the entrypoint. Alembic takes a transactional lock so a
# couple of replicas racing is safe. Move this to a Helm pre-upgrade Job if the
# replica count or migration runtime grows.
alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
