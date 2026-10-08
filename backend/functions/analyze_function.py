"""
Queue-triggered function that analyzes a detected content change.

Triggered by: ANALYZE_QUEUE_NAME
Message format: {"court_id": <int>, "change_id": <int>}
"""

import json
import logging

import azure.functions as func
from services import ai_analyzer, differ
from services.blob_client import load_snapshot
from services.graph_client import add_change_to_sharepoint, send_change_notification
from shared.config import config
from shared.database import get_db_session
from shared.models import AlertConfig, Change, Court
from sqlalchemy import select

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.queue_trigger(
    arg_name="msg",
    queue_name="%ANALYZE_QUEUE_NAME%",
    connection="AzureWebJobsStorage",
)
async def analyze_change(msg: func.QueueMessage) -> None:
    """Analyze a content change and notify stakeholders if relevant."""
    body = msg.get_body().decode("utf-8")
    try:
        payload = json.loads(body)
        court_id = int(payload["court_id"])
        change_id = int(payload["change_id"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.error("Invalid analyze queue message: %s - %s", body[:200], exc)
        return

    logger.info("Analyzing change %d for court %d", change_id, court_id)

    async with get_db_session() as session:
        change = await session.get(Change, change_id)
        if change is None:
            logger.error("Change %d not found", change_id)
            return

        court = await session.get(Court, court_id)
        if court is None:
            logger.error("Court %d not found", court_id)
            return

        # Load content from blobs
        old_content = await load_snapshot(change.old_snapshot_path)
        new_content = await load_snapshot(change.new_snapshot_path)

        # Re-generate diff with actual content
        diff_text = differ.generate_diff(old_content, new_content)
        stats = differ.get_diff_stats(diff_text)

        change.diff_text = diff_text
        change.diff_line_count = stats["total_changed"]

        # Check if diff is meaningful
        if not differ.is_meaningful_diff(diff_text, config.MIN_DIFF_LINES):
            logger.info(
                "Diff for change %d is below threshold (%d lines); marking false_positive",
                change_id,
                stats["total_changed"],
            )
            change.status = "false_positive"
            await session.commit()
            return

        # Get alert config to check AI filter setting
        alert_result = await session.execute(select(AlertConfig).limit(1))
        alert_config = alert_result.scalars().first()
        ai_filter_enabled = alert_config.ai_filter_enabled if alert_config else True

        # Run AI analysis
        ai_result = await ai_analyzer.analyze_change(
            court_name=court.name,
            url=court.url,
            old_content=old_content,
            new_content=new_content,
            diff_text=diff_text,
        )

        change.ai_is_relevant = ai_result["is_relevant"]
        change.ai_summary = ai_result["summary"]
        change.ai_category = ai_result["category"]
        change.ai_priority = ai_result["priority"]
        change.ai_action = ai_result["action_required"]

        # Filter based on AI relevance if enabled
        if ai_filter_enabled and not ai_result["is_relevant"]:
            logger.info(
                "AI determined change %d is not relevant to docketing rules; "
                "marking false_positive",
                change_id,
            )
            change.status = "false_positive"
            await session.commit()
            return

        # Check minimum priority filter
        if alert_config and not _meets_priority(
            ai_result["priority"], alert_config.min_priority
        ):
            logger.info(
                "Change %d priority %s below minimum %s; marking false_positive",
                change_id,
                ai_result["priority"],
                alert_config.min_priority,
            )
            change.status = "false_positive"
            await session.commit()
            return

        # Create SharePoint item
        try:
            sp_item_id = await add_change_to_sharepoint(change, court)
            change.sharepoint_item_id = sp_item_id
        except Exception as exc:
            logger.error("SharePoint item creation failed for change %d: %s", change_id, exc)

        # Send email notification
        recipients: list[str] = []
        if alert_config and alert_config.email_recipients:
            recipients = [
                r.strip()
                for r in alert_config.email_recipients.split(",")
                if r.strip()
            ]

        if recipients and (not alert_config or alert_config.notify_immediately):
            try:
                await send_change_notification(change, court, recipients)
                change.email_sent = True
            except Exception as exc:
                logger.error(
                    "Email notification failed for change %d: %s", change_id, exc
                )

        await session.commit()
        logger.info(
            "Finished processing change %d (court: %s, priority: %s, relevant: %s)",
            change_id,
            court.name,
            ai_result["priority"],
            ai_result["is_relevant"],
        )


def _meets_priority(change_priority: str, min_priority: str) -> bool:
    """Return True if change_priority is at or above min_priority."""
    order = {"high": 3, "medium": 2, "low": 1}
    return order.get(change_priority, 1) >= order.get(min_priority, 1)
