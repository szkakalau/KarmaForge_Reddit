"""E4: Email notifications — post milestone alerts via SMTP."""

import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

MILESTONES = [25, 50, 100, 250, 500, 1000]

TEMPLATES: dict[int, dict[str, str]] = {
    25: {
        "subject": "Your r/{subreddit} post hit 25 upvotes!",
        "emoji": "🌱",
        "label": "Gaining traction",
    },
    50: {
        "subject": "50 upvotes! Your r/{subreddit} post is climbing",
        "emoji": "📈",
        "label": "Rising",
    },
    100: {
        "subject": "100 upvotes! r/{subreddit} is listening",
        "emoji": "🔥",
        "label": "Hot post",
    },
    250: {
        "subject": "250 upvotes on r/{subreddit} — this is going viral",
        "emoji": "🚀",
        "label": "Going viral",
    },
    500: {
        "subject": "500 upvotes! Your r/{subreddit} post is a top performer",
        "emoji": "🏆",
        "label": "Top performer",
    },
    1000: {
        "subject": "1,000 upvotes on r/{subreddit} — legendary",
        "emoji": "👑",
        "label": "Legendary",
    },
}


def get_milestones_achieved(old_upvotes: int, new_upvotes: int) -> list[int]:
    """Return list of milestone thresholds crossed between old and new upvote counts."""
    return [m for m in MILESTONES if old_upvotes < m <= new_upvotes]


def send_milestone_email(
    to_email: str,
    subreddit: str,
    title: str,
    upvotes: int,
    num_comments: int,
    url: str = "",
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_password: str = "",
) -> bool:
    """Send a milestone notification email."""

    milestones = get_milestones_achieved(0, upvotes)
    if not milestones:
        return False

    highest = max(milestones)
    tmpl = TEMPLATES.get(highest, TEMPLATES[25])

    body = f"""Hi,

{tmpl['emoji']} Your Reddit post just reached {upvotes} upvotes on r/{subreddit}!

  "{title}"

  Upvotes: {upvotes}
  Comments: {num_comments}
  Milestone: {tmpl['label']}

{("  View: " + url) if url else ""}

Keep growing!

— KarmaForge
"""

    msg = MIMEText(body)
    msg["Subject"] = tmpl["subject"].format(subreddit=subreddit)
    msg["From"] = smtp_user or "noreply@karmaforge.dev"
    msg["To"] = to_email

    host = smtp_host or os.getenv("SMTP_HOST", "")
    if not host:
        logger.info("No SMTP configured — notification would send: %s", msg["Subject"])
        return False

    try:
        with smtplib.SMTP(host, smtp_port) as server:
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_password or os.getenv("SMTP_PASSWORD", ""))
            server.send_message(msg)
        logger.info("Sent milestone email to %s: %d upvotes on r/%s", to_email, upvotes, subreddit)
        return True
    except Exception as e:
        logger.warning("Failed to send email: %s", e)
        return False
