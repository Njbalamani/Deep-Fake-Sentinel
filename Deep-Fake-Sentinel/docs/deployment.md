# Deployment Guide for DEEPFAKE SENTINEL

## Scope

This guide covers the implemented container stack defined in `docker/`: PostgreSQL, Redis, Django under Gunicorn with the REST API and workspace UI, a Celery worker for media processing, and Nginx. `config/settings.py` reads environment variables from `.env.example`; Compose passes `REDIS_URL`, and settings derive `CELERY_BROKER_URL` from it and `CELERY_RESULT_BACKEND` from the broker URL unless you override them explicitly. When `REDIS_URL` is unset, the fallback is `redis://localhost:6379/0`.

## Prerequisites

- Docker 24+ with Compose v2.
- A populated `.env` copied from `.env.example`.
- A strong `SECRET_KEY` and database password.
- No trained weights are required to start the stack; analysis results will remain `INCONCLUSIVE`.

## Files

| File | Purpose |
| --- | --- |
| `docker/Dockerfile` | Python base image for `web` and `celery`. |
| `docker/docker-compose.yml` | Service definitions, health checks, and volumes. |
| `docker/nginx/nginx.conf` | Reverse proxy, static asset serving, and proxying of protected API download requests. |
| `.env.example` | Configuration template at repository root. |

## 1. Prepare configuration

From the repository root:

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```text
DEBUG=False
ALLOWED_HOSTS=your-domain.example,localhost
SECRET_KEY=generate-a-new-secret
DB_NAME=deepfake_sentinel
DB_USER=deepfake
DB_PASSWORD=replace-with-strong-password
DB_HOST=db
DB_PORT=5432
REDIS_URL=redis://redis:6379/0
CELERY_TASK_ALWAYS_EAGER=False
MAX_UPLOAD_SIZE_MB=100
MEDIAPIPE_FACE_MODEL=
```

`CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` are optional overrides. Omit them to derive both from `REDIS_URL`; set them explicitly only when the broker and result backend differ. `MEDIAPIPE_FACE_MODEL` is optional; the bundled asset at `ml_models/mediapipe/blaze_face_short_range.tflite` is used when it is blank. Never commit `.env`.

Compose passes `REDIS_URL` to both `web` and `celery`. Django derives `CELERY_BROKER_URL` from `REDIS_URL` and `CELERY_RESULT_BACKEND` from `CELERY_BROKER_URL`, so no Compose override is needed for the bundled `redis` service. If `REDIS_URL` is unset, Celery falls back to `redis://localhost:6379/0`.

## 2. Build and start services

```bash
docker compose --env-file .env -f docker/docker-compose.yml up --build -d
```

Services:

| Service | Image/build | Role |
| --- | --- | --- |
| `db` | `postgres:16-alpine` | Durable relational data. |
| `redis` | `redis:7-alpine` | Celery broker and result backend. |
| `web` | local `docker/Dockerfile` | Gunicorn serving Django. |
| `celery` | local `docker/Dockerfile` | Celery worker. |
| `nginx` | `nginx:1.27-alpine` | Public HTTP entry point. |

## 3. Initialize the database

```bash
docker compose --env-file .env -f docker/docker-compose.yml exec web python manage.py migrate
docker compose --env-file .env -f docker/docker-compose.yml exec web python manage.py collectstatic --noinput
docker compose --env-file .env -f docker/docker-compose.yml exec web python manage.py createsuperuser
```

## 4. Verify health

```bash
docker compose --env-file .env -f docker/docker-compose.yml ps
```

Expected health checks:

- `db`: `pg_isready` succeeds.
- `redis`: `redis-cli ping` returns `PONG`.
- `web`: the Gunicorn port accepts a TCP connection on `127.0.0.1:8000`.
- `nginx`: `GET /` returns a page.
- `celery`: `celery -A config inspect ping` succeeds once the worker has started.

There is no separate health or readiness API route in this implementation. Web and Nginx container checks are transport-level checks, so also verify `/api/auth/me/`, `/api/analytics/dashboard/`, and the workspace pages with an authenticated browser session or token.

## 5. Volumes and persistence

| Volume | Mounted at | Purpose |
| --- | --- | --- |
| `db_data` | `/var/lib/postgresql/data` | PostgreSQL data. |
| `redis_data` | `/data` | Redis persistence. |
| `media_data` | `/app/media` | Uploads, derived artifacts, reports. |
| `static_data` | `/app/staticfiles` | Collected static assets for Nginx. |

Repository folders such as `ml_models/`, `docs/`, and `static/models/` are copied into the image during build. To make local checkpoints available without rebuilding, add a bind mount in your local Compose override:

```yaml
services:
  web:
    volumes:
      - ../ml_models:/app/ml_models:ro
  celery:
    volumes:
      - ../ml_models:/app/ml_models:ro
```

Do not publish these volumes publicly.

## 6. PostgreSQL notes

- Use a dedicated role with a strong password.
- Do not use the `postgres` superuser for application connections.
- Enable SSL between services if they run on different hosts.
- Back up `db_data` and `media_data` together so case records and evidence stay consistent.
- Test restore procedures regularly.

Manual connection example:

```bash
docker compose --env-file .env -f docker/docker-compose.yml exec db psql -U deepfake -d deepfake_sentinel
```

## 7. Redis notes

- `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` must be reachable from both `web` and `celery`; by default both derive from the Compose-provided `REDIS_URL`.
- `REDIS_URL` is passed by Compose and read by Django settings as the broker default; explicit Celery variables take precedence.
- Use a dedicated database index for Celery if sharing Redis with other workloads.
- Set `CELERY_TASK_ALWAYS_EAGER=False` in production so work runs in workers.
- Monitor queue depth and failed tasks.
- Secure Redis with a password or private network when exposed beyond Compose.

## 8. Celery notes

The worker command is:

```bash
celery -A config worker --loglevel=info --concurrency=2
```

Operational guidance:

- Scale `celery` replicas for more throughput.
- Keep video jobs on workers with more memory if needed.
- Ensure `web` and `celery` use the same media volume and checkpoint store.
- Use idempotent task design so retries do not duplicate findings.
- Celery task IDs are recorded in `AnalysisEvent` messages created during upload and reprocessing.

## 9. Gunicorn notes

The web command is:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
```

Tune `--workers` based on CPU and memory. PDF report generation runs synchronously in the web process, so increase `--timeout` if large reports approach the limit. Long media analysis runs in Celery and should never run inside a Gunicorn worker.

## 10. Nginx notes

`nginx.conf` provides:

- Proxying of dynamic requests to `web:8000`.
- Static file serving from `/app/staticfiles/`.
- No public `/media/` serving. Private media files are accessible only through authenticated, object-scoped API download endpoints such as `GET /api/media/{id}/download/`.
- `client_max_body_size 100m`, matching the default `MAX_UPLOAD_SIZE_MB`.

If you change `MAX_UPLOAD_SIZE_MB`, update `client_max_body_size` to match.

For production, terminate TLS at Nginx or an upstream load balancer. Use HSTS, a modern cipher suite, and secure cookie flags.

## 11. Manual non-Docker deployment

If running services directly:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MEDIAPIPE_FACE_MODEL=/absolute/path/to/blaze_face_short_range.tflite
export DEBUG=False
export DB_HOST=localhost
export REDIS_URL=redis://localhost:6379/0
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

In another terminal:

```bash
celery -A config worker --loglevel=info
```

Configure Nginx to proxy to Gunicorn and serve collected static files.

## 12. Production checklist

- [ ] `DEBUG=False`
- [ ] New `SECRET_KEY`
- [ ] Correct `ALLOWED_HOSTS`
- [ ] CORS and CSRF origins restricted
- [ ] PostgreSQL backups scheduled and tested
- [ ] Redis private or authenticated
- [ ] Media volume access restricted
- [ ] Upload size aligned across Django and Nginx
- [ ] TLS enabled with HSTS
- [ ] Object-level authorization verified for media, analysis/evidence, investigations, and HTML workspace routes
- [ ] Container health checks and Celery ping verified
- [ ] Celery monitoring enabled
- [ ] Logs centralized without secrets or file contents
- [ ] Retention and deletion policy documented
- [ ] Model checkpoints produced by your own training/evaluation runs
- [ ] Reports state that model output is decision support only

## 13. Shutdown and cleanup

Stop services without deleting data:

```bash
docker compose --env-file .env -f docker/docker-compose.yml down
```

Remove named volumes only when you intentionally want to destroy data:

```bash
docker compose --env-file .env -f docker/docker-compose.yml down --volumes
```

## Related documents

- [Architecture](architecture.md)
- [REST API](api.md)
- [Model evaluation](model-evaluation.md)
