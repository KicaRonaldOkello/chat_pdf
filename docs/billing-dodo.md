# Billing & Payments with Dodo Payments — Engineering Plan

**Date:** 2026-08-19
**Source:** Dodo Payments subscription integration guide + API docs (docs.dodopayments.com)
**Stack:** FastAPI backend · Angular frontend · official Dodo Python SDK
**Status:** Phase 0 + Phase 1 + Phase 2 + Phase 3 complete (2026-08-20).
- Phase 0: SDK added, Dodo settings in `settings.py`, `plans` / `subscriptions` / `usage_meter` models + migration `0009` (seeded), repositories wired into `db.dependencies`. Migration applied to Postgres.
- Phase 1: migration `0009` applied; Dodo products created in test mode (`sync_subscription_products`, keyed by `metadata.plan_slug`); `POST /api/billing/checkout` + `GET /api/billing/status` live in `app/api/routes/billing.py`; pricing page CTAs create a hosted checkout for signed-in users (sign-up first otherwise); `/app/billing` landing page handles success/cancelled redirects, plan + usage meters. Live test: test checkout session returned a hosted URL (`https://test.checkout.dodopayments.com/session/...`).
- Phase 3: entitlement + usage enforcement in `app/billing/enforcement.py`; migration `0010` adds `plans.max_upload_bytes_per_import` (Free 5 MB / Plus 100 MB / Pro 300 MB). Chat endpoint checks files-in-scope + word quota, counts AI words from the answer, caps the meter at the daily allowance, emits `limit_reached`, and records usage in `finally`; upload endpoint checks uploads/day + bytes/day + per-import cap and increments the meter. Plan-limit blocks render as HTTP 402 `{code: "usage_limit", limit_type, used, limit, upgrade}` via a global handler. Frontend: real "Words remaining" meter in the sidebar (was hardcoded 84%), plan-aware client-side upload size checks, and upgrade snackbars on 402 / `limit_reached`.
- Phase 2: `POST /webhooks/dodo` (no auth; signature-verified via `standardwebhooks` through the Dodo SDK), idempotency ledger table `dodo_webhook_events` (migration `0011`, claim via `ON CONFLICT DO NOTHING` + `RETURNING`), and `app/billing/webhooks.py` maps `subscription.*` events to the `subscriptions` table (plan via `metadata.plan_slug` → fallback `product_id`, user via `metadata.user_id` → fallback customer email). `subscription.active/renewed/updated/on_hold/cancelled/failed/expired` all upsert status + period + payment method; payment events are logged only. Verified end-to-end: signed delivery created an active Plus subscription, and a replay was deduped.
- Next: Phase 4 (billing UI: cancel, upgrade/downgrade with proration, update payment method), then Phase 5 (go-live drill).

---

## What Dodo handles for us (merchant of record)

- Hosted checkout (redirect flow) — no card forms on our site
- Subscription billing, renewals, proration, plan changes
- Failed-payment handling (`on_hold` + dunning) and payment-method updates
- Taxes in every jurisdiction, invoices/receipts, 220+ countries, 80+ currencies, 40+ payment methods
- Test and live environments with separate credentials

We handle: mapping Dodo subscriptions to plans/entitlements, usage metering and limit enforcement, the billing UI, and webhook state sync.

---

## Architecture

```
Angular pricing page
        │  POST /billing/checkout {tier, period}
        ▼
FastAPI  ──► Dodo API (create checkout session) ──► hosted checkout URL
        ◄──────────────── redirect ──────────────── user pays
                │
Dodo webhooks ──► POST /webhooks/dodo (signature-verified)
                │   subscription.active / renewed / updated / on_hold / failed
                │   payment.succeeded / failed
                ▼
        subscriptions table ──► entitlements (tier, period end)
                ▼
        usage meters ──► enforcement on chat/upload APIs
                ▼
        GET /billing/usage ──► Angular billing UI (real meter, not the hardcoded 84%)
```

**Rule:** Dodo API key lives only in the backend. The frontend never sees it.

---

## Engineering phases

### Phase 0 — Setup & data model

- Add `dodopayments` Python SDK (`uv add dodopayments`).
- Settings: `DODO_API_KEY`, `DODO_WEBHOOK_SECRET`, `DODO_MODE` (`test_mode`/`live_mode`), `DODO_WEBHOOK_URL`, `DODO_BILLING_CURRENCY` (e.g. `USD`), `DODO_TRIAL_DAYS` (0 for now).
- Pricing config: 4 Dodo products — Plus monthly ($12), Plus yearly ($115.20 billed annually), Pro monthly ($24), Pro yearly ($230.40 billed annually). Create them in the Dodo dashboard **or** via the products API during setup.
- New tables:
  - `plans` — tier, billing_period, dodo_product_id, price, limits (words/day, uploads/day, mb/day, files_in_scope)
  - `subscriptions` — user_id, dodo_subscription_id, plan, status (active/renewed/on_hold/expired/cancelled/failed), current_period_end, payment_method_id, last_webhook
  - `usage_meter` — user_id, date, ai_words, uploads, upload_bytes (daily rollup)
- Migration: existing users get the Free plan.

### Phase 1 — Checkout flow (backend + pricing page)

- `POST /billing/checkout` (auth required): body `{tier, period}` → create Dodo checkout session with `product_cart`, `customer {email, name}`, `return_url` (success page), and pass `billing_currency` + `billing_address.country` explicitly (Dodo locks currency at first charge — don't let IP detection decide it). Return `{checkout_url}`.
- Pricing page buttons become: signed-out → sign-up first; signed-in → call checkout API, then `window.location = checkout_url`.
- `GET /billing/status` → current plan + usage, used by the sidebar and billing page.
- Success/cancel landing pages after Dodo redirect (`/app/billing?checkout=success|cancelled`).

### Phase 2 — Webhooks (the source of truth)

- `POST /webhooks/dodo`: verify signature with webhook secret → respond `200 {received: true}` quickly → process async.
- Idempotency: dedupe on Dodo event id; handle retries/replays.
- Event map:

| Dodo event | Action |
| --- | --- |
| `subscription.active` | Grant entitlement for the new plan; on first activation also welcome state |
| `subscription.renewed` | Extend `current_period_end` to next billing date (use this, not `payment.succeeded` alone, for renewals) |
| `subscription.updated` | Sync any plan/status field changes (upgrades/downgrades) |
| `subscription.on_hold` | Renewal failed — keep access per product decision (recommend: keep current tier until period end, prompt to update payment method) |
| `subscription.failed` | Terminal — never grant/keep entitlements; user must resubscribe |
| `payment.succeeded` / `payment.failed` | Record payment events (used with renewals; invoices handled by Dodo) |

- Plan changes (upgrade/downgrade from billing page): backend proxy to Dodo change-plan API with proration option — recommend `prorated_immediately` for upgrades (charge difference) and `do_not_bill` or `prorated_immediately` for downgrades (apply at next renewal; decide with product).
- `on_hold` recovery: expose "update payment method" → Dodo API, which auto-charges remaining dues and reactivates.

### Phase 3 — Entitlements & usage enforcement

- Backend dependency on chat + upload endpoints: resolve plan → check daily meters → enforce limits (words/day, uploads/day, MB/day, files in scope) → increment meters → `402`/`429` with upgrade payload when exceeded.
- Free tier: one account per person (link by Google sub), abuse heuristics.
- `GET /billing/usage` returns real daily usage; replace the hardcoded `tokensRemainingPercent = 84` in the app shell.
- Upgrade prompts: when a limit hits, UI toast/modal → checkout for Plus/Pro.

### Phase 4 — Billing UI

- Billing/account page (`/app/billing`): current plan + price, real usage meter, upgrade/downgrade buttons (change-plan API), cancel subscription (Dodo API + our state), update payment method (for on_hold), invoices note (Dodo emails receipts/invoices as MoR).
- Sidebar plan badge + upgrade link.
- Consistent "Begin Research" CTA behavior for signed-in free users (→ billing if at limit, else app).

### Phase 5 — Go-live checks

- Full test-mode walkthrough with Dodo test cards: checkout, first charge, renewal, failed payment → on_hold → payment-method update, plan upgrade/downgrade with proration, cancel.
- Live mode: swap keys, verify webhook URL is public HTTPS, run one real $12 purchase.
- Monitoring: webhook failure counter + alert (Prometheus), billing metrics (active subs, MRR), Sentry on webhook handler.
- Final pass on pricing page copy ("Free during preview" → real terms), refund policy consistency with Terms of Service.

---

## On your side — required keys & decisions

### Credentials (from the Dodo dashboard)

- [ ] **Merchant account** — register at dodopayments.com and complete business KYC/onboarding (needed before live mode)
- [ ] **Test API key** (`DODO_API_KEY`) — bearer token for `test_mode`
- [ ] **Live API key** (`DODO_API_KEY`) — bearer token for `live_mode`
- [ ] **Test webhook secret** (`DODO_WEBHOOK_SECRET`)
- [ ] **Live webhook secret** (`DODO_WEBHOOK_SECRET`)
- [ ] **Payout/bank details** — where funds settle

### Products & pricing decisions

- [ ] Confirm prices: Plus $12/mo, Pro $24/mo (and yearly equivalents: $115.20 / $230.40 billed annually — or choose different yearly pricing)
- [ ] Confirm billing currency (recommend `USD`)
- [ ] Confirm default billing country (used for tax/checkout — Dodo handles taxes as MoR)
- [ ] Decide trial length (recommend 0 days at launch; Dodo trials use a $0 authorization)
- [ ] Create the 4 products in the dashboard (or give me the API key and I'll create them via API during setup)
- [ ] Decide plan-change policy: upgrade = prorate immediately; downgrade = apply at next renewal (recommended)
- [ ] Decide `on_hold` behavior: keep access until period end (recommended) vs. immediate downgrade to Free

### URLs & branding

- [ ] Public HTTPS webhook URL (e.g., `https://api.yourdomain.com/webhooks/dodo`) — point Dodo at it and register the endpoint
- [ ] Success/cancel return URLs (e.g., `https://app.yourdomain.com/app/billing?checkout=success`)
- [ ] Checkout branding: brand name, logo, colors in the Dodo dashboard
- [ ] **Fix the support email** (`uderstandnotes@gmail.com` → correct address) — Dodo surfaces this on invoices/disputes

### Legal consistency

- [ ] Align pricing page, Terms of Service, and Privacy Policy with the live plans (amounts, refund policy, auto-renewal wording)
- [ ] Confirm refund policy matches Dodo's handling (Dodo is merchant of record — verify their refund window vs. your ToS)

---

## Suggested build order

1. Phase 0 (schema + settings) — small, unblocks everything
2. Phase 2 (webhooks) — the source of truth, build first so state is real
3. Phase 3 (enforcement) — makes the Free tier honest
4. Phase 1 (checkout) — wiring pricing page to Dodo
5. Phase 4 (billing UI) — polish + plan management
6. Phase 5 (go-live drill)
