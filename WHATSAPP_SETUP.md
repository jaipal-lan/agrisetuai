# WhatsApp alerts (Gupshup) — setup

KissanSetu can push transactional updates — **order placed/paid/out-for-delivery/
settled, payout sent, dispute resolved, account/KYC decisions** — to users over
WhatsApp, so farmers hear about a sale even when they're not in the app.

It is **gated**: nothing is sent until you switch it on AND provide Gupshup
credentials. With it off (the default) the app behaves exactly as before
(in-app notifications only), so dev and tests never message anyone.

Only a small, high-value set of events go to WhatsApp (`order`, `payout`,
`payout_account`, `dispute`, `user`). Noisy/proactive alerts (new offers, RFQ
matches, price alerts) and bulk broadcasts are deliberately **excluded**.

---

## 1. Create a Gupshup account + WhatsApp app

1. Sign up at **https://www.gupshup.io/** → **WhatsApp API**.
2. Create a WhatsApp app. For production messaging you onboard a **WhatsApp
   Business number** (a number not already on consumer WhatsApp) and complete
   Facebook/Meta Business verification. For first tests, Gupshup provides a
   **sandbox** number you can message immediately.
3. From the app dashboard, copy:
   - **API key** → `GUPSHUP_API_KEY`
   - **App name** → `GUPSHUP_SRC_NAME`
   - **Source number** (your WhatsApp Business number, digits only, e.g.
     `9180XXXXXXXX`) → `GUPSHUP_SOURCE`

## 2. Set the environment variables (Render / your host)

```
WHATSAPP_ENABLED=true
GUPSHUP_API_KEY=your-gupshup-api-key
GUPSHUP_SOURCE=9180XXXXXXXX
GUPSHUP_SRC_NAME=your-app-name
```

Leave `WHATSAPP_ENABLED` unset (or `false`) to keep WhatsApp off.

## 3. Message templates (important for production)

WhatsApp only allows **free-form text within 24h of the user's last message**
to your number. For business-initiated messages **outside** that window (most of
our alerts), Meta requires **pre-approved message templates**.

- For sandbox / early testing, the plain-text send wired here works.
- For production, create and get **utility templates approved** in Gupshup for
  each alert (e.g. "Your order {{1}} was delivered"), then we switch the sender
  from plain text to the approved template call. Tell me when your templates are
  approved and I'll wire the template path (it's a small change isolated to
  `app/services/whatsapp.py`).

## 4. Test

1. Set the env vars, redeploy.
2. Place a test order (or trigger any order event) for a user whose phone is a
   real WhatsApp number.
3. They should receive the update on WhatsApp. If not, check the backend logs
   for `agrisetu.whatsapp` warnings (bad key, unapproved template, or number not
   opted in).

## Notes

- Delivery is **best-effort**: a WhatsApp failure never blocks an order,
  payment or payout — it only logs a warning.
- Costs: WhatsApp business-initiated (utility) messages are billed per
  conversation by Meta/Gupshup. Keep the alert set small (as configured).
- An SMS fallback (2Factor/MSG91) already exists for OTP and can be extended to
  these alerts later if you want SMS when WhatsApp is undelivered.
