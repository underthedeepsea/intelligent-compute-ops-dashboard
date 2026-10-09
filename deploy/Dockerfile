# Build from the project root with deploy/build.sh or an explicit --target.
FROM python:3.13-slim AS api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock /app/
RUN pip install --no-cache-dir -r requirements.lock \
    && groupadd --gid 10001 control \
    && useradd --uid 10001 --gid 10001 --no-create-home control
COPY backend /app/backend
COPY templates /app/templates
COPY deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod 0555 /app/entrypoint.sh && mkdir -p /app/backend/staticfiles /data \
    && chown 10001:10001 /data
USER 10001:10001
WORKDIR /app/backend
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "1", "--worker-class", "sync", "--worker-tmp-dir", "/tmp", "--timeout", "30", "--access-logfile", "-"]

FROM api AS assets
USER root
# Build-only configuration: collectstatic never opens the runtime NAS database.
RUN DJANGO_SECRET_KEY=build-only-not-a-runtime-secret DATABASE_ENGINE=sqlite \
    SQLITE_PATH=/tmp/collectstatic.sqlite3 python manage.py collectstatic --noinput

FROM nginx:1.28-alpine AS web
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY frontend /usr/share/nginx/html
COPY --from=assets /app/backend/staticfiles /usr/share/nginx/static
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
