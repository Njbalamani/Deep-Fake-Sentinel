import os

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("deepfake_sentinel")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.broker_url = getattr(settings, "CELERY_BROKER_URL", None) or getattr(settings, "REDIS_URL", None)
app.conf.result_backend = getattr(settings, "CELERY_RESULT_BACKEND", None) or app.conf.broker_url
app.autodiscover_tasks()
