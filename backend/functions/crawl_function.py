"""
Queue-triggered function that crawls a single court URL.

Triggered by: CRAWL_QUEUE_NAME
Message format: {"court_id": <int>}
"""

import json
import logging
from datetime import datetime, timezone

import azure.functions as func
from azure.storage.queue.aio import QueueClient as AsyncQueueClient
from services import content_extractor, crawler, differ
from services.blob_client import save_snapshot
from services.crawler import CrawlError
from shared.config import config
from shared.database import get_db_session
from shared.models import Change, Court, ScanHistory

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.queue_trigger(
    arg_name="msg",
    queue_name="%CRAWL_QUEUE_NAME%",
    connection="AzureWebJobsStorage",
)
async def crawl_court(msg: func.QueueMessage) -> None:
    """Crawl a single court URL and detect content changes."""
    body = msg.get_body().decode("utf-8")
    try:
        payload = json.loads(body)
        court_id = int(payload["court_id"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.error("Invalid crawl queue message: %s - %s", body[:200], exc)
        return

    logger.info("Processing crawl for court_id=%d", court_id)

    async with get_db_session() as session:
        court = await session.get(Court, court_id)
        if court is None:
            logger.error("Court %d not found in database", court_id)
            return

        scan_time = datetime.now(timezone.utc).replace(tzinfo=None)

        try:
            html, response_time_ms = await crawler.fetch_page(
                url=court.url,
                js_required=court.js_required,
                css_selector=court.css_selector,
            )
            clean_text = content_extractor.extract_and_clean(html, court.url)
            content_hash = differ.compute_hash(clean_text)

            if court.last_content_hash is None:
                # First scan ever — store baseline, no change to report
                logger.info(
                    "First scan for court %d (%s); storing baseline hash",
                    court_id, court.name,
                )
                history = ScanHistory(
                    court_id=court_id,
                    scanned_at=scan_time,
                    content_hash=content_hash,
                    status="success",
                    response_time_ms=response_time_ms,
                )
                session.add(history)
                court.last_content_hash = content_hash
                court.last_scanned_at = scan_time
                court.consecutive_errors = 0
                await session.commit()
                return

            if content_hash == court.last_content_hash:
                # No change
                logger.info(
                    "No change detected for court %d (%s)", court_id, court.name
                )
                history = ScanHistory(
                    court_id=court_id,
                    scanned_at=scan_time,
                    content_hash=content_hash,
                    status="success",
                    response_time_ms=response_time_ms,
                )
                session.add(history)
                court.last_scanned_at = scan_time
                court.consecutive_errors = 0
                await session.commit()
                return

            # Content has changed
            logger.info(
                "Content change detected for court %d (%s)", court_id, court.name
            )

            # Save old snapshot (if we have a previous hash, try to find old snapshot)
            old_content = ""
            old_snapshot_path = ""
            if court.last_content_hash:
                # We don't store the old text in the court row, so we create a
                # placeholder path. The analyze function will compare using the
                # blobs we save here.
                old_content = ""  # Will be reconstructed from previous blob if available

            # Save new snapshot
            new_snapshot_path = await save_snapshot(
                court_id=court_id,
                scan_time=scan_time,
                content=clean_text,
                version="new",
            )

            # Also save old content snapshot (empty if first scan)
            old_snapshot_path = await save_snapshot(
                court_id=court_id,
                scan_time=scan_time,
                content=old_content,
                version="old",
            )

            # Compute initial diff stats for the Change record
            diff_text = differ.generate_diff(old_content, clean_text)
            stats = differ.get_diff_stats(diff_text)

            # Create a Change record
            change = Change(
                court_id=court_id,
                detected_at=scan_time,
                old_snapshot_path=old_snapshot_path,
                new_snapshot_path=new_snapshot_path,
                diff_text=diff_text,
                diff_line_count=stats["total_changed"],
                status="new",
            )
            session.add(change)

            # Update court
            court.last_content_hash = content_hash
            court.last_scanned_at = scan_time
            court.last_changed_at = scan_time
            court.consecutive_errors = 0

            history = ScanHistory(
                court_id=court_id,
                scanned_at=scan_time,
                content_hash=content_hash,
                status="changed",
                response_time_ms=response_time_ms,
            )
            session.add(history)
            await session.flush()  # Assigns change.id

            change_id = change.id

        except CrawlError as exc:
            logger.error(
                "Crawl error for court %d (%s): %s", court_id, court.name, exc
            )
            court.consecutive_errors = (court.consecutive_errors or 0) + 1
            history = ScanHistory(
                court_id=court_id,
                scanned_at=scan_time,
                status="error" if exc.status_code != 408 else "timeout",
                error_message=str(exc)[:1000],
            )
            session.add(history)
            await session.commit()
            return

        except Exception as exc:
            logger.exception(
                "Unexpected error crawling court %d (%s): %s",
                court_id,
                court.name,
                exc,
            )
            court.consecutive_errors = (court.consecutive_errors or 0) + 1
            history = ScanHistory(
                court_id=court_id,
                scanned_at=scan_time,
                status="error",
                error_message=str(exc)[:1000],
            )
            session.add(history)
            await session.commit()
            return

        await session.commit()

    # Enqueue to analyze queue
    analyze_payload = json.dumps({"court_id": court_id, "change_id": change_id})
    queue_client = AsyncQueueClient.from_connection_string(
        conn_str=config.AZURE_WEBJOBS_STORAGE,
        queue_name=config.ANALYZE_QUEUE_NAME,
    )
    try:
        await queue_client.create_queue()
    except Exception:
        pass
    await queue_client.send_message(analyze_payload)
    await queue_client.close()

    logger.info(
        "Enqueued change %d for analysis (court %d)", change_id, court_id
    )
