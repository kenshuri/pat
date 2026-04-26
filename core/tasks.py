from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def ping():
    logger.info("Celery ping task executed.")
    return "pong"
