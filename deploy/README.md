# Deployment

From this directory copy `.env.example` to `.env` and supply secrets/hosts. Production uses PostgreSQL; never set CONTROL_LOCAL. Terminate HTTPS at a trusted ingress that forwards only to localhost:8088; Secure cookies intentionally do not work over plain public HTTP. Nginx has login throttling. The inspection ingress must independently enforce GET-only access; no assumption is made that a Bearer header is accepted by upstream.

```sh
docker compose --env-file .env build
docker compose --env-file .env up -d db
docker compose --env-file .env run --rm api python manage.py migrate --noinput
docker compose --env-file .env run --rm api python manage.py collectstatic --noinput
docker compose --env-file .env run --rm api python manage.py createsuperuser
docker compose --env-file .env run --rm api python manage.py bootstrap_access
docker compose --env-file .env up -d api worker web
```

Static frontend is mounted read-only; demo directory is not copied into the image. API never starts a polling thread. One worker holds a database lease; do not run more than one intentionally. Health endpoints expose no catalog. Back up the PostgreSQL database before migration with pg_dump; retain the previous image and frontend artifact together. To roll back code, stop the worker, restore prior image/frontend and, if schema compatibility is not guaranteed, restore the database backup into a separate database first. Do not reverse migrations against production without backup and compatibility review.

This configuration is a deployment artifact, not evidence of real inspection integration or production rollout. M0/M5 remain blocked until real environment, read credentials, provenance and one complete chain are validated.
