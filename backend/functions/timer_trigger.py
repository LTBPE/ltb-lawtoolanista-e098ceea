"""
Weekday timer trigger that enqueues all active courts for crawling.

Schedule: 0 0 8 * * 1-5  (Monday–Friday 08:00 UTC)
"""

import json
import logging

import azure.functions as func
from azure.storage.queue.aio import QueueClient as AsyncQueueClient
from shared.config import config
from shared.database import get_db_session
from shared.models import Court
from sqlalchemy import select

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.timer_trigger(
    schedule="0 0 8 * * 1-5",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
async def weekly_scan_timer(timer: func.TimerRequest) -> None:
    """Enqueue all active courts to the crawl queue."""
    if timer.past_due:
        logger.warning("Timer is running late (past_due=True)")

    async with get_db_session() as session:
        result = await session.execute(
            select(Court).where(Court.active == True).order_by(Court.id)
        )
        courts = result.scalars().all()

    if not courts:
        logger.info("No active courts found; nothing to enqueue")
        return

    queue_client = AsyncQueueClient.from_connection_string(
        conn_str=config.AZURE_WEBJOBS_STORAGE,
        queue_name=config.CRAWL_QUEUE_NAME,
    )

    # Ensure queue exists
    try:
        await queue_client.create_queue()
    except Exception:
        pass  # Already exists

    enqueued = 0
    errors = 0
    for court in courts:
        message = json.dumps({"court_id": court.id})
        try:
            await queue_client.send_message(message)
            enqueued += 1
        except Exception as exc:
            logger.error(
                "Failed to enqueue court %d (%s): %s", court.id, court.name, exc
            )
            errors += 1

    await queue_client.close()

    logger.info(
        "Enqueued %d courts for daily scan (%d errors)", enqueued, errors
    )
