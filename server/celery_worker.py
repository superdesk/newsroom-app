import logging

from app import app


logger = logging.getLogger(__name__)
celery = app.celery
