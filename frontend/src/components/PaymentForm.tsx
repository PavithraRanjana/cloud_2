import { useState } from "react";

export interface PaymentFormData {
  payment_method: string;
  card_holder_name?: string;
  card_number?: string;
  card_expiry?: string;
  card_cvv?: string;
  wallet_type?: string;
  wallet_email?: string;
  wallet_phone?: string;
  bank_account_holder?: string;
  bank_name?: string;
  bank_account_number?: string;
  bank_routing_number?: string;
}

interface Props {
  amount: number;
  currency?: string;
  onSubmit: (data: PaymentFormData) => void;
  onBack: () => void;
  isPending: boolean;
}

type CardBrand = "visa" | "mastercard" | "amex" | "discover" | "unknown";

function detectCardBrand(raw: string): CardBrand {
  const n = raw.replace(/\s/g, "");
  if (/^4/.test(n)) return "visa";
  if (/^(5[1-5]|2[2-7])/.test(n)) return "mastercard";
  if (/^3[47]/.test(n)) return "amex";
  if (/^(6011|622|64[4-9]|65)/.test(n)) return "discover";
  return "unknown";
}

const BRAND_LABEL: Record<CardBrand, string> = {
  visa: "VISA", mastercard: "MC", amex: "AMEX", discover: "DISC", unknown: "",
};

const WALLET_LABEL: Record<string, string> = {
  paypal: "PayPal",
  google_pay: "Google Pay",
  apple_pay: "Apple Pay",
  samsung_pay: "Samsung Pay",
};

function fmtCardNumber(v: string) {
  return v.replace(/\D/g, "").slice(0, 16).replace(/(.{4})/g, "$1 ").trim();
}

function fmtExpiry(v: string) {
  const d = v.replace(/\D/g, "").slice(0, 4);
  return d.length >= 3 ? d.slice(0, 2) + "/" + d.slice(2) : d;
}

function Field({
  label, error, children,
}: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500">
        {label}
      </label>
      {children}
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </div>
  );
}

export function PaymentForm({ amount, currency = "USD", onSubmit, onBack, isPending }: Props) {
  const [method,      setMethod]      = useState("credit-card");

  // Card
  const [holderName,  setHolderName]  = useState("");
  const [cardNum,     setCardNum]     = useState("");
  const [expiry,      setExpiry]      = useState("");
  const [cvv,         setCvv]         = useState("");

  // Wallet
  const [walletType,  setWalletType]  = useState("paypal");
  const [wEmail,      setWEmail]      = useState("");
  const [wPhone,      setWPhone]      = useState("");

  // Bank
  const [bHolder,     setBHolder]     = useState("");
  const [bName,       setBName]       = useState("");
  const [bAccount,    setBAccount]    = useState("");
  const [bRouting,    setBRouting]    = useState("");

  const [errors, setErrors] = useState<Record<string, string>>({});

  const isCard  = method === "credit-card" || method === "debit-card";
  const brand   = detectCardBrand(cardNum);
  const isAmex  = brand === "amex";
  const cvvLen  = isAmex ? 4 : 3;

  function inputCls(field: string) {
    return `w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-1 ${
      errors[field]
        ? "border-red-400 focus:border-red-400 focus:ring-red-200"
        : "border-gray-300 focus:border-blue-500 focus:ring-blue-500"
    }`;
  }

  function validate(): boolean {
    const e: Record<string, string> = {};

    if (isCard) {
      if (!holderName.trim()) e.holderName = "Cardholder name is required";
      const raw = cardNum.replace(/\s/g, "");
      if (raw.length < 13) e.cardNum = "Enter a valid card number";
      if (!expiry || !/^\d{2}\/\d{2}$/.test(expiry)) {
        e.expiry = "Enter expiry in MM/YY format";
      } else {
        const [mm, yy] = expiry.split("/").map(Number);
        const now = new Date();
        const expYear = 2000 + yy;
        if (mm < 1 || mm > 12) e.expiry = "Invalid expiry month";
        else if (expYear < now.getFullYear() || (expYear === now.getFullYear() && mm < now.getMonth() + 1))
          e.expiry = "This card has expired";
      }
      if (!cvv || cvv.length !== cvvLen) e.cvv = `CVV must be ${cvvLen} digits`;
    } else if (method === "wallet") {
      if (["paypal", "google_pay"].includes(walletType)) {
        if (!wEmail) e.wEmail = "Email address is required";
        else if (!/^[^@]+@[^@]+\.[^@]+$/.test(wEmail)) e.wEmail = "Enter a valid email address";
      } else if (["apple_pay", "samsung_pay"].includes(walletType)) {
        if (!wEmail && !wPhone) e.wPhone = "Email or phone number is required";
        else if (wEmail && !/^[^@]+@[^@]+\.[^@]+$/.test(wEmail)) e.wEmail = "Enter a valid email address";
      }
    } else if (method === "bank-transfer") {
      if (!bHolder.trim()) e.bHolder = "Account holder name is required";
      if (!bName.trim())   e.bName   = "Bank name is required";
      const acct = bAccount.replace(/\s/g, "");
      if (!/^\d{6,17}$/.test(acct)) e.bAccount = "Account number must be 6–17 digits";
      if (!bRouting.trim()) e.bRouting = "Routing / sort code is required";
    }

    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function handleSubmit() {
    if (!validate()) return;
    onSubmit({
      payment_method: method,
      ...(isCard ? {
        card_holder_name: holderName,
        card_number:      cardNum.replace(/\s/g, ""),
        card_expiry:      expiry,
        card_cvv:         cvv,
      } : {}),
      ...(method === "wallet" ? {
        wallet_type:  walletType,
        wallet_email: wEmail  || undefined,
        wallet_phone: wPhone  || undefined,
      } : {}),
      ...(method === "bank-transfer" ? {
        bank_account_holder: bHolder,
        bank_name:           bName,
        bank_account_number: bAccount.replace(/\s/g, ""),
        bank_routing_number: bRouting,
      } : {}),
    });
  }

  function switchMethod(m: string) {
    setMethod(m);
    setErrors({});
  }

  return (
    <div className="space-y-4">

      {/* Payment method */}
      <Field label="Payment Method">
        <select
          value={method}
          onChange={(e) => switchMethod(e.target.value)}
          className="w-full h-9 rounded-lg border border-gray-300 px-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="credit-card">Credit Card</option>
          <option value="debit-card">Debit Card</option>
          <option value="wallet">Digital Wallet</option>
          <option value="bank-transfer">Bank Transfer</option>
        </select>
      </Field>

      {/* ── Card fields ── */}
      {isCard && (
        <>
          <Field label="Cardholder Name" error={errors.holderName}>
            <input
              type="text"
              placeholder="Name exactly as shown on card"
              value={holderName}
              onChange={(e) => setHolderName(e.target.value)}
              autoComplete="cc-name"
              className={inputCls("holderName")}
            />
          </Field>

          <Field label="Card Number" error={errors.cardNum}>
            <div className="relative">
              <input
                type="text"
                inputMode="numeric"
                placeholder="1234 5678 9012 3456"
                maxLength={19}
                value={cardNum}
                onChange={(e) => setCardNum(fmtCardNumber(e.target.value))}
                autoComplete="cc-number"
                className={`${inputCls("cardNum")} pr-16 font-mono tracking-widest`}
              />
              {brand !== "unknown" && (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-600">
                  {BRAND_LABEL[brand]}
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-gray-400">Card number is tokenised and never stored raw.</p>
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Expiry (MM/YY)" error={errors.expiry}>
              <input
                type="text"
                inputMode="numeric"
                placeholder="MM/YY"
                maxLength={5}
                value={expiry}
                onChange={(e) => setExpiry(fmtExpiry(e.target.value))}
                autoComplete="cc-exp"
                className={`${inputCls("expiry")} font-mono`}
              />
            </Field>

            <Field label={`CVV${isAmex ? " (4 digits)" : " (3 digits)"}`} error={errors.cvv}>
              <input
                type="password"
                inputMode="numeric"
                placeholder={isAmex ? "●●●●" : "●●●"}
                maxLength={cvvLen}
                value={cvv}
                onChange={(e) => setCvv(e.target.value.replace(/\D/g, "").slice(0, cvvLen))}
                autoComplete="cc-csc"
                className={`${inputCls("cvv")} font-mono`}
              />
              <p className="mt-1 text-xs text-gray-400">CVV is never stored.</p>
            </Field>
          </div>
        </>
      )}

      {/* ── Digital Wallet ── */}
      {method === "wallet" && (
        <>
          <Field label="Wallet Type">
            <div className="grid grid-cols-2 gap-2">
              {(["paypal", "google_pay", "apple_pay", "samsung_pay"] as const).map((wt) => (
                <button
                  key={wt}
                  type="button"
                  onClick={() => { setWalletType(wt); setErrors({}); }}
                  className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                    walletType === wt
                      ? "border-blue-500 bg-blue-50 text-blue-700"
                      : "border-gray-300 text-gray-600 hover:border-gray-400"
                  }`}
                >
                  {WALLET_LABEL[wt]}
                </button>
              ))}
            </div>
          </Field>

          {["paypal", "google_pay"].includes(walletType) && (
            <Field label={`${WALLET_LABEL[walletType]} Email`} error={errors.wEmail}>
              <input
                type="email"
                placeholder="account@example.com"
                value={wEmail}
                onChange={(e) => setWEmail(e.target.value)}
                className={inputCls("wEmail")}
              />
            </Field>
          )}

          {["apple_pay", "samsung_pay"].includes(walletType) && (
            <>
              <Field label="Email Address" error={errors.wEmail}>
                <input
                  type="email"
                  placeholder="account@example.com"
                  value={wEmail}
                  onChange={(e) => setWEmail(e.target.value)}
                  className={inputCls("wEmail")}
                />
              </Field>
              <Field label="Phone Number" error={errors.wPhone}>
                <input
                  type="tel"
                  placeholder="+1 555 000 0000"
                  value={wPhone}
                  onChange={(e) => setWPhone(e.target.value)}
                  className={inputCls("wPhone")}
                />
                <p className="mt-1 text-xs text-gray-400">Either email or phone number is required.</p>
              </Field>
            </>
          )}
        </>
      )}

      {/* ── Bank Transfer ── */}
      {method === "bank-transfer" && (
        <>
          <Field label="Account Holder Name" error={errors.bHolder}>
            <input
              type="text"
              placeholder="Full legal name"
              value={bHolder}
              onChange={(e) => setBHolder(e.target.value)}
              className={inputCls("bHolder")}
            />
          </Field>

          <Field label="Bank Name" error={errors.bName}>
            <input
              type="text"
              placeholder="e.g. Chase Bank"
              value={bName}
              onChange={(e) => setBName(e.target.value)}
              className={inputCls("bName")}
            />
          </Field>

          <Field label="Account Number" error={errors.bAccount}>
            <input
              type="text"
              inputMode="numeric"
              placeholder="6–17 digits"
              maxLength={17}
              value={bAccount}
              onChange={(e) => setBAccount(e.target.value.replace(/\D/g, "").slice(0, 17))}
              className={`${inputCls("bAccount")} font-mono`}
            />
          </Field>

          <Field label="Routing / Sort Code" error={errors.bRouting}>
            <input
              type="text"
              placeholder="e.g. 021000021 or 20-00-00"
              value={bRouting}
              onChange={(e) => setBRouting(e.target.value)}
              className={inputCls("bRouting")}
            />
          </Field>
        </>
      )}

      {/* Amount summary */}
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
          disabled={isPending}
          className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          Back
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isPending}
          className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition-colors"
        >
          {isPending ? "Processing…" : `Pay $${amount.toFixed(2)}`}
        </button>
      </div>
    </div>
  );
}
