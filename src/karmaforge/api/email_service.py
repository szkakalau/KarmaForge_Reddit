"""Email notifications — Resend (default) or SMTP fallback.

Env vars:
  RESEND_API_KEY  — Resend API key (https://resend.com)
  EMAIL_FROM      — sender address (default: noreply@reddpilot.com)

Flow:
  - After registration → welcome email
  - Quota at 80% → heads-up email
  - Quota exhausted → upgrade prompt email
  - Subscription canceled → confirmation email
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "Reddpilot <noreply@reddpilot.com>")


def _send_via_resend(to: str, subject: str, html: str) -> bool:
    """Send email via Resend API."""
    if not RESEND_API_KEY:
        logger.debug("RESEND_API_KEY not set — skipping email to %s", to)
        return False

    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": EMAIL_FROM,
                "to": to,
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("Email sent to %s: %s", to, subject)
            return True
        logger.warning("Resend API error %d: %s", resp.status_code, resp.text)
        return False
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


# ── Templates ──────────────────────────────────────────────────────

def send_welcome_email(to: str, display_name: str = "") -> bool:
    name = display_name or to.split("@")[0]
    subject = "Welcome to Reddpilot"
    html = f"""\
<!DOCTYPE html>
<html><body style="font-family:Inter,sans-serif;background:#0D0D0F;color:#EBEBEC;padding:32px">
  <div style="max-width:480px;margin:0 auto">
    <h1 style="color:#00C48C;font-size:20px;margin-bottom:16px">Welcome to Reddpilot</h1>
    <p style="color:#8E8E98;font-size:14px;line-height:1.6">
      Hi {name},<br><br>
      You're all set. Your free account includes <strong style="color:#EBEBEC">20 generations per month</strong>.
    </p>
    <p style="color:#8E8E98;font-size:14px;line-height:1.6">
      Head to the dashboard, describe your content, and let Reddpilot craft Reddit titles that actually get upvoted.
    </p>
    <a href="https://reddpilot.com/app" style="display:inline-block;background:#00C48C;color:#0D0D0F;font-weight:600;padding:10px 20px;border-radius:6px;text-decoration:none;font-size:14px;margin-top:16px">
      Go to Dashboard →
    </a>
    <p style="color:#5C5C66;font-size:11px;margin-top:32px">Reddpilot — Reddit Growth Co-pilot</p>
  </div>
</body></html>"""
    return _send_via_resend(to, subject, html)


def send_quota_warning(to: str, used: int, limit: int) -> bool:
    subject = f"You've used {used}/{limit} generations this month"
    html = f"""\
<!DOCTYPE html>
<html><body style="font-family:Inter,sans-serif;background:#0D0D0F;color:#EBEBEC;padding:32px">
  <div style="max-width:480px;margin:0 auto">
    <h1 style="color:#F5A623;font-size:20px;margin-bottom:16px">Quota running low</h1>
    <p style="color:#8E8E98;font-size:14px;line-height:1.6">
      You've used <strong style="color:#EBEBEC">{used} of {limit}</strong> free generations this month.
    </p>
    <p style="color:#8E8E98;font-size:14px;line-height:1.6">
      Upgrade to Pro for 300 generations/month, unlimited AI revisions, and more.
    </p>
    <a href="https://reddpilot.com/app/pricing" style="display:inline-block;background:#00C48C;color:#0D0D0F;font-weight:600;padding:10px 20px;border-radius:6px;text-decoration:none;font-size:14px;margin-top:16px">
      Upgrade to Pro — $5/month →
    </a>
  </div>
</body></html>"""
    return _send_via_resend(to, subject, html)


def send_subscription_canceled(to: str, end_date: str) -> bool:
    subject = "Your Reddpilot Pro subscription has been canceled"
    html = f"""\
<!DOCTYPE html>
<html><body style="font-family:Inter,sans-serif;background:#0D0D0F;color:#EBEBEC;padding:32px">
  <div style="max-width:480px;margin:0 auto">
    <h1 style="color:#EBEBEC;font-size:20px;margin-bottom:16px">Subscription canceled</h1>
    <p style="color:#8E8E98;font-size:14px;line-height:1.6">
      Your Pro access continues until <strong style="color:#EBEBEC">{end_date}</strong>.
      After that, you'll be moved to the Free plan (20 generations/month).
    </p>
    <p style="color:#8E8E98;font-size:14px;line-height:1.6">
      You can re-subscribe anytime from your dashboard.
    </p>
  </div>
</body></html>"""
    return _send_via_resend(to, subject, html)
