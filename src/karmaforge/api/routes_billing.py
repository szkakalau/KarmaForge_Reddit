"""Billing endpoints — Stripe Checkout, Portal, Webhooks."""

import logging
import os
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .deps import get_current_user, get_db, get_quota_info, require_quota
from .models import Subscription, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["billing"])

BASE_URL = os.getenv("BASE_URL", "http://localhost:5173")


def _get_stripe_secret() -> str:
    return os.getenv("STRIPE_SECRET_KEY", "")


def _get_webhook_secret() -> str:
    return os.getenv("STRIPE_WEBHOOK_SECRET", "")


def _get_price_id() -> str:
    return os.getenv("STRIPE_PRICE_ID", "price_1TfsNd7479xkrVpGRml9OLsF")

# ── Helpers ─────────────────────────────────────────────────────────


def _get_or_create_subscription(user_id: str, session: Session) -> Subscription:
    sub = session.query(Subscription).filter(Subscription.user_id == user_id).first()
    if sub is None:
        sub = Subscription(user_id=user_id, plan="free", status="active")
        session.add(sub)
        session.commit()
    return sub


def _stripe_available() -> bool:
    return bool(_get_stripe_secret())


# ── Checkout ────────────────────────────────────────────────────────


class CreateCheckoutRequest(BaseModel):
    success_url: str | None = None
    cancel_url: str | None = None


@router.post("/billing/create-checkout")
def create_checkout(
    body: CreateCheckoutRequest,
    request: Request,
    user: User = Depends(require_quota),  # auth required
    session: Session = Depends(get_db),
):
    """Create a Stripe Checkout Session to upgrade to Pro."""
    if not _stripe_available():
        raise HTTPException(status_code=503, detail="Billing not configured")

    stripe.api_key = _get_stripe_secret()

    sub = _get_or_create_subscription(user.id, session)

    # Create or reuse Stripe customer
    if not sub.stripe_customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            metadata={"user_id": user.id},
        )
        sub.stripe_customer_id = customer.id
        session.commit()

    success_url = body.success_url or f"{BASE_URL}/?upgraded=true"
    cancel_url = body.cancel_url or f"{BASE_URL}/pricing?canceled=true"

    try:
        checkout = stripe.checkout.Session.create(
            customer=sub.stripe_customer_id,
            mode="subscription",
            line_items=[{"price": _get_price_id(), "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": user.id},
        )
        return {"url": checkout.url, "session_id": checkout.id}
    except stripe.StripeError as e:
        logger.exception("Stripe checkout creation failed for user %s", user.id)
        raise HTTPException(status_code=500, detail=f"Stripe error: {e.user_message or str(e)}")


# ── Customer Portal ─────────────────────────────────────────────────


@router.post("/billing/portal")
def create_portal(
    request: Request,
    user: User = Depends(require_quota),
    session: Session = Depends(get_db),
):
    """Create a Stripe Customer Portal session for subscription management."""
    if not _stripe_available():
        raise HTTPException(status_code=503, detail="Billing not configured")

    stripe.api_key = _get_stripe_secret()

    sub = _get_or_create_subscription(user.id, session)
    if not sub.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer found. Upgrade first.")

    try:
        portal = stripe.billing_portal.Session.create(
            customer=sub.stripe_customer_id,
            return_url=f"{BASE_URL}/settings",
        )
        return {"url": portal.url}
    except stripe.StripeError as e:
        logger.exception("Stripe portal creation failed for user %s", user.id)
        raise HTTPException(status_code=500, detail=f"Stripe error: {e.user_message or str(e)}")


# ── Webhook ─────────────────────────────────────────────────────────


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    session: Session = Depends(get_db),
):
    """Stripe webhook receiver — signature verified, idempotent."""
    if not _get_webhook_secret():
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # ── Signature verification (T3) ──
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=_get_webhook_secret(),
        )
    except stripe.SignatureVerificationError:
        logger.warning("Stripe webhook: invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except ValueError:
        logger.warning("Stripe webhook: invalid payload")
        raise HTTPException(status_code=400, detail="Invalid payload")

    event_id = event.id
    event_type = event.type

    logger.info("Stripe webhook received: %s (id=%s)", event_type, event_id)

    # ── Handle subscription events ──
    if event_type in (
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        _handle_subscription_event(event, event_id, session)

    # ── Handle payment failure ──
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(event, session)

    return {"status": "received"}


def _handle_subscription_event(event, event_id: str, session: Session) -> None:
    """Process subscription lifecycle events — idempotent (T5)."""
    obj = event.data.object

    # Extract user_id from metadata
    user_id = None
    if hasattr(obj, "metadata") and obj.metadata:
        user_id = obj.metadata.get("user_id")
    if not user_id and hasattr(obj, "customer"):
        # Look up by Stripe customer ID
        sub = session.query(Subscription).filter(
            Subscription.stripe_customer_id == obj.customer
        ).first()
        if sub:
            user_id = sub.user_id

    if not user_id:
        logger.warning("Stripe webhook: could not determine user_id for event %s", event_id)
        return

    sub = session.query(Subscription).filter(Subscription.user_id == user_id).first()
    if not sub:
        logger.warning("Stripe webhook: no subscription found for user %s", user_id)
        return

    # ── Idempotency check (T5) ──
    event_ids = sub.stripe_event_ids or []
    if event_id in event_ids:
        logger.info("Stripe webhook: duplicate event %s — skipped", event_id)
        return
    event_ids.append(event_id)
    # Keep only last 100 event IDs to bound storage
    if len(event_ids) > 100:
        event_ids = event_ids[-100:]

    event_type = event.type

    if event_type in ("checkout.session.completed", "customer.subscription.created"):
        sub.plan = "pro"
        sub.status = "active"
        sub.cancel_at_period_end = False
        # Update user tier
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            user.tier = "pro"
    elif event_type == "customer.subscription.updated":
        # Handle cancel_at_period_end or plan changes
        if hasattr(obj, "cancel_at_period_end") and obj.cancel_at_period_end:
            sub.cancel_at_period_end = True
    elif event_type == "customer.subscription.deleted":
        sub.plan = "free"
        sub.status = "canceled"
        sub.cancel_at_period_end = False
        # Downgrade user
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            user.tier = "free"

    # Sync Stripe IDs
    if hasattr(obj, "id") and not sub.stripe_subscription_id:
        sub.stripe_subscription_id = obj.id
    if hasattr(obj, "current_period_start"):
        sub.current_period_start = datetime.fromtimestamp(
            obj.current_period_start, tz=timezone.utc
        )
    if hasattr(obj, "current_period_end"):
        sub.current_period_end = datetime.fromtimestamp(
            obj.current_period_end, tz=timezone.utc
        )

    sub.stripe_event_ids = event_ids
    sub.updated_at = datetime.now(timezone.utc)
    session.commit()
    logger.info("Stripe webhook: subscription updated for user %s → plan=%s status=%s",
                user_id, sub.plan, sub.status)


def _handle_payment_failed(event, session: Session) -> None:
    """Mark subscription as past_due on payment failure."""
    obj = event.data.object
    customer_id = obj.get("customer") if isinstance(obj, dict) else getattr(obj, "customer", None)
    if not customer_id:
        return

    sub = session.query(Subscription).filter(
        Subscription.stripe_customer_id == customer_id
    ).first()
    if sub:
        sub.status = "past_due"
        session.commit()
        logger.warning("Stripe webhook: payment failed for user %s", sub.user_id)


# ── Status & Usage ──────────────────────────────────────────────────


@router.get("/billing/status")
def billing_status(
    request: Request,
    user: User = Depends(require_quota),
    session: Session = Depends(get_db),
):
    """Return current subscription status."""
    sub = _get_or_create_subscription(user.id, session)
    return {
        "plan": sub.plan,
        "status": sub.status,
        "cancel_at_period_end": sub.cancel_at_period_end,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "stripe_customer_id": sub.stripe_customer_id,
    }


@router.get("/usage")
def usage(
    request: Request,
    user: User = Depends(require_quota),
    session: Session = Depends(get_db),
):
    """Return current generation usage and quota info."""
    return get_quota_info(request, session)
