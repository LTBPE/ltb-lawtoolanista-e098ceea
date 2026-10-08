"""
Microsoft Graph API client for SharePoint list management and email notifications.
"""

import logging
from datetime import timezone

import httpx
import msal
from shared.config import config
from shared.models import Change, Court

logger = logging.getLogger(__name__)

_token_cache: dict = {}


def _get_access_token() -> str:
    """
    Obtain an access token using MSAL client credentials flow.
    MSAL handles token caching internally.
    """
    app = msal.ConfidentialClientApplication(
        client_id=config.GRAPH_CLIENT_ID,
        client_credential=config.GRAPH_CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{config.GRAPH_TENANT_ID}",
    )
    result = app.acquire_token_for_client(scopes=[config.GRAPH_SCOPE])
    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "unknown"))
        raise RuntimeError(f"Failed to acquire Graph token: {error}")
    return result["access_token"]


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_access_token()}",
        "Content-Type": "application/json",
    }


async def discover_site_id() -> str:
    """
    Discover and return the SharePoint site ID for the configured site.
    Logs the value so it can be stored as SHAREPOINT_SITE_ID env var.
    """
    url = (
        f"{config.GRAPH_BASE_URL}/sites/"
        f"{config.SHAREPOINT_HOST}:{config.SHAREPOINT_SITE_PATH}"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=_auth_headers())
        response.raise_for_status()
        data = response.json()
        site_id = data["id"]
        logger.info("SharePoint site ID: %s", site_id)
        return site_id


async def add_change_to_sharepoint(change: Change, court: Court) -> str:
    """
    Create a list item in SharePoint for a detected change.

    Args:
        change: The Change ORM instance.
        court: The associated Court ORM instance.

    Returns:
        The SharePoint list item ID string.
    """
    if not config.sharepoint_configured:
        logger.warning("SharePoint not configured; skipping list item creation")
        return ""

    detected_iso = (
        change.detected_at.replace(tzinfo=timezone.utc).isoformat()
        if change.detected_at.tzinfo is None
        else change.detected_at.isoformat()
    )

    diff_preview = (change.diff_text or "")[:5000]

    fields: dict = {
        "Title": court.name,
        "CourtURL": court.url,
        "DetectedDate": detected_iso,
        "Category": change.ai_category or "other",
        "Priority": change.ai_priority or "medium",
        "Summary": change.ai_summary or "",
        "ActionRequired": change.ai_action or "",
        "DiffText": diff_preview,
        "Status": "New",
        "ChangeId": str(change.id),
    }

    url = (
        f"{config.GRAPH_BASE_URL}/sites/{config.SHAREPOINT_SITE_ID}"
        f"/lists/{config.SHAREPOINT_LIST_ID}/items"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url,
            json={"fields": fields},
            headers=_auth_headers(),
        )
        response.raise_for_status()
        data = response.json()
        item_id = data.get("id", "")
        logger.info(
            "Created SharePoint item %s for change %d", item_id, change.id
        )
        return item_id


def _build_notification_html(
    change: Change,
    court: Court,
    sharepoint_item_url: str | None = None,
) -> str:
    """Build the HTML body for a change notification email."""
    priority = (change.ai_priority or "medium").upper()
    category = change.ai_category or "other"
    summary = change.ai_summary or "No summary available."
    action = change.ai_action or ""

    priority_color = {
        "HIGH": "#dc2626",
        "MEDIUM": "#d97706",
        "LOW": "#6b7280",
    }.get(priority, "#6b7280")

    diff_lines = (change.diff_text or "").splitlines()[:50]
    diff_preview = "\n".join(diff_lines)

    sp_link = ""
    if sharepoint_item_url:
        sp_link = (
            f'<p><a href="{sharepoint_item_url}">View in SharePoint</a></p>'
        )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;">
  <h2 style="color:#1e3a5f;">Court Monitor Alert</h2>
  <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
    <tr>
      <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Court</td>
      <td style="padding:8px;border:1px solid #ddd;">
        <a href="{court.url}">{court.name}</a>
      </td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Detected</td>
      <td style="padding:8px;border:1px solid #ddd;">
        {change.detected_at.strftime("%Y-%m-%d %H:%M UTC")}
      </td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Priority</td>
      <td style="padding:8px;border:1px solid #ddd;">
        <span style="background:{priority_color};color:white;
          padding:2px 8px;border-radius:4px;font-weight:bold;">
          {priority}
        </span>
      </td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Category</td>
      <td style="padding:8px;border:1px solid #ddd;">{category}</td>
    </tr>
  </table>

  <h3>Summary</h3>
  <p>{summary}</p>

  {"<h3>Action Required</h3><p>" + action + "</p>" if action else ""}

  <h3>Diff Preview (first 50 lines)</h3>
  <pre style="background:#f4f4f4;padding:12px;border:1px solid #ccc;
    overflow-x:auto;font-size:12px;white-space:pre-wrap;">{diff_preview}</pre>

  {sp_link}

  <hr style="margin-top:30px;">
  <p style="color:#888;font-size:12px;">
    Manage alerts at
    <a href="{config.MANAGEMENT_PORTAL_URL}">{config.MANAGEMENT_PORTAL_URL}</a>
  </p>
</body>
</html>"""


async def send_change_notification(
    change: Change,
    court: Court,
    recipients: list[str],
) -> None:
    """
    Send an HTML email notification via Microsoft Graph sendMail.

    Args:
        change: The Change ORM instance.
        court: The associated Court ORM instance.
        recipients: List of email address strings.
    """
    if not config.graph_configured:
        logger.warning("Graph API not configured; skipping email notification")
        return
    if not recipients:
        logger.warning("No recipients configured; skipping email for change %d", change.id)
        return

    priority_label = (change.ai_priority or "medium").upper()
    category_label = change.ai_category or "other"
    subject = f"[Court Monitor] {priority_label}: {court.name} - {category_label}"

    html_body = _build_notification_html(change, court)

    to_recipients = [
        {"emailAddress": {"address": addr.strip()}}
        for addr in recipients
        if addr.strip()
    ]

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": to_recipients,
        },
        "saveToSentItems": False,
    }

    url = (
        f"{config.GRAPH_BASE_URL}/users/{config.GRAPH_SENDER_EMAIL}/sendMail"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers=_auth_headers())
        response.raise_for_status()

    logger.info(
        "Sent notification email for change %d to %d recipient(s)",
        change.id,
        len(to_recipients),
    )
