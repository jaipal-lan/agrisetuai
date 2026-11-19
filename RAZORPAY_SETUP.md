# Razorpay setup (sandbox → live)

How to switch AgriSetuAI payments from the in-app "mock" capture to a real
payment gateway. **Test (sandbox) mode needs no KYC** — you can integrate today.
Live mode needs business KYC (PAN, GST, bank proof) submitted to Razorpay.

## 1. Test API keys (Key ID + Secret)

1. Sign up / log in at **dashboard.razorpay.com** (free).
2. Flip the **Test Mode** toggle at the top of the dashboard.
3. Go to **Account & Settings → API Keys** (some accounts: **Settings → API Keys**).
4. Click **Generate Test Key**.
5. Copy both now:
   - **Key Id** → starts with `rzp_test_…`
   - **Key Secret** → ⚠️ shown **once** — save it immediately (regenerate if lost).

No website or KYC needed for test keys. Only the account Owner/Admin can view keys.

## 2. Webhook + secret

The webhook secret is a string **you invent** (Razorpay does not issue it); you
type the same value here and into the backend env.

1. In **Test Mode**, go to **Account & Settings → Webhooks → Add New Webhook**.
2. **Webhook URL:** `https://<your-render-backend>.onrender.com/api/payments/webhook`
   (find the `onrender.com` URL in Render → your backend service).
3. **Secret:** a strong random string — save a copy. This is `PAYMENT_WEBHOOK_SECRET`.
4. **Active events:** tick **`payment.captured`** (optionally `payment.failed`, `order.paid`).
5. **Create Webhook.**

## 3. Backend environment (Render → backend service → Environment)

| Env var | Value |
|---|---|
| `PAYMENT_PROVIDER` | `razorpay` |
| `RAZORPAY_KEY_ID` | `rzp_test_…` |
| `RAZORPAY_KEY_SECRET` | *(the secret from step 1)* |
| `PAYMENT_WEBHOOK_SECRET` | *(the webhook secret from step 2)* |

Redeploy. Once `PAYMENT_PROVIDER != mock`, the free in-app `/orders/{id}/pay`
capture is disabled — payment must flow through Checkout + the webhook.

## 4. How it flows in the app

1. Buyer confirms the quote → order is `payment_pending`.
2. Client calls `GET /api/payments/intent/{order_id}` → returns `key_id` +
   `provider_order_id` (a real Razorpay Order) + amount for Razorpay Checkout.
3. Buyer pays in Checkout.
4. Razorpay calls `POST /api/payments/webhook` with `X-Razorpay-Signature`
   (`payment.captured`) → the backend verifies the signature and captures the
   order through the ledger (`order → paid`).

## 5. Test cards (sandbox — no real money)

- Card: **`4111 1111 1111 1111`**, any future expiry, any CVV.
- UPI success VPA: **`success@razorpay`** (failure: `failure@razorpay`).

## 6. Going live (later)

1. Complete **business KYC** in the Razorpay dashboard.
2. Switch to **Live Mode**, generate **Live** keys (`rzp_live_…`).
3. Add a **Live-mode webhook** (same URL, a new secret).
4. Update the four env vars with the live values and redeploy.

## What's implemented vs. pending

- ✅ Real Razorpay Order creation (`create_intent`), signed webhook (Razorpay
  signature scheme), ledger capture, and the in-app-pay bypass disabled in prod.
- ⏳ Needs a merchant account to end-to-end test; Cashfree not wired;
  provider-side refunds (dispute refunds are ledger-only today).
