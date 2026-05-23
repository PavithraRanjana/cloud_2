import { useEffect, useMemo, useState } from "react";
import { loadStripe, type Stripe } from "@stripe/stripe-js";
import {
  Elements,
  PaymentElement,
  useElements,
  useStripe,
} from "@stripe/react-stripe-js";

export interface PaymentFormProps {
  clientSecret: string;
  publishableKey: string;
  amount: number;
  currency?: string;
  isPending?: boolean;
  onBack: () => void;
  onSuccess: (intentId: string) => void;
  onError?: (message: string) => void;
}

// ── Inner form: uses Stripe hooks (must be inside <Elements>) ─────────────
function CheckoutForm({
  amount, currency = "USD", isPending: parentPending, onBack, onSuccess, onError,
}: Omit<PaymentFormProps, "clientSecret" | "publishableKey">) {
  const stripe   = useStripe();
  const elements = useElements();
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg,   setErrorMsg]   = useState<string | null>(null);
  const [ready,      setReady]      = useState(false);

  const busy = submitting || !!parentPending;

  async function handlePay() {
    if (!stripe || !elements) return;
    setErrorMsg(null);
    setSubmitting(true);

    const { error, paymentIntent } = await stripe.confirmPayment({
      elements,
      // Stay on this page where possible; Stripe will only redirect when the
      // chosen payment method requires it (e.g. 3DS challenge windows).
      confirmParams: { return_url: window.location.href },
      redirect: "if_required",
    });

    if (error) {
      const msg = error.message ?? "Payment failed. Please try again.";
      setErrorMsg(msg);
      setSubmitting(false);
      onError?.(msg);
      return;
    }

    if (paymentIntent && paymentIntent.status === "succeeded") {
      onSuccess(paymentIntent.id);
      return;
    }

    // Anything else (requires_action, processing, …) — surface a status to the user.
    const status = paymentIntent?.status ?? "unknown";
    const msg = `Payment is ${status}. Please refresh in a moment.`;
    setErrorMsg(msg);
    setSubmitting(false);
    onError?.(msg);
  }

  return (
    <div className="space-y-4">
      <PaymentElement onReady={() => setReady(true)} />

      {errorMsg && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {errorMsg}
        </div>
      )}

      <div className="flex justify-between rounded-xl bg-gray-50 px-4 py-3 text-sm">
        <span className="text-gray-500">Amount due</span>
        <span className="text-lg font-bold text-blue-700">
          ${amount.toFixed(2)} {currency}
        </span>
      </div>

      <div className="flex gap-3 pt-1">
        <button
          type="button"
          onClick={onBack}
          disabled={busy}
          className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          Back
        </button>
        <button
          type="button"
          onClick={handlePay}
          disabled={busy || !stripe || !elements || !ready}
          className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition-colors"
        >
          {busy ? "Processing…" : `Pay $${amount.toFixed(2)}`}
        </button>
      </div>
    </div>
  );
}

// ── Cache the Stripe.js promise so it's only fetched once per pubkey ──────
const stripeCache = new Map<string, Promise<Stripe | null>>();
function getStripe(publishableKey: string): Promise<Stripe | null> {
  let p = stripeCache.get(publishableKey);
  if (!p) {
    p = loadStripe(publishableKey);
    stripeCache.set(publishableKey, p);
  }
  return p;
}

// ── Outer wrapper: provides Elements context ──────────────────────────────
export function PaymentForm(props: PaymentFormProps) {
  const { clientSecret, publishableKey } = props;
  const [stripeReady, setStripeReady] = useState<Stripe | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!publishableKey) return;
    getStripe(publishableKey).then((s) => {
      if (!cancelled) setStripeReady(s);
    });
    return () => { cancelled = true; };
  }, [publishableKey]);

  const options = useMemo(() => ({
    clientSecret,
    appearance: { theme: "stripe" as const },
  }), [clientSecret]);

  if (!publishableKey) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
        Payment is not configured. Set <code>STRIPE_PUBLISHABLE_KEY</code> on the server.
      </div>
    );
  }

  if (!stripeReady || !clientSecret) {
    return <p className="text-sm text-gray-400 animate-pulse">Loading payment form…</p>;
  }

  return (
    <Elements stripe={stripeReady} options={options}>
      <CheckoutForm {...props} />
    </Elements>
  );
}
