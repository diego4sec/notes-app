FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY . .
RUN uv pip install --system --no-cache .

# Never run the app as root.
USER 1000

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
