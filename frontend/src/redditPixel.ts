// Reddit Pixel — event tracking module
// Pixel ID: a2_ir4ey0jenya0
//
// Base pixel (loader + init + PageVisit) is in index.html <head>.
// This module exposes typed wrappers for conversion events.

type RdtFn = (action: string, event?: string, params?: Record<string, unknown>) => void;

function rdt(): RdtFn {
  if (typeof window !== 'undefined' && typeof (window as any).rdt === 'function') {
    return (window as any).rdt;
  }
  return () => {};
}

/** Fire after successful registration */
export function trackSignUp(): void {
  rdt()('track', 'SignUp');
}

/** Fire after user's first title generation (Lead = high-intent action) */
export function trackLead(): void {
  rdt()('track', 'Lead');
}

/** Fire after successful Stripe checkout → Pro upgrade */
export function trackPurchase(orderId: string, value = 5, currency = 'USD'): void {
  rdt()('track', 'Purchase', {
    value,
    currency,
    transactionId: orderId,
  });
}

/** Storage keys for dedup tracking */
export const RD_EVENTS = {
  LEAD_FIRED: 'rd_lead_fired',
  PURCHASE_FIRED: 'rd_purchase_fired',
} as const;
