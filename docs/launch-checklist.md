# Understanding Notes — SaaS Launch Checklist

**Date:** 2026-08-19
**Reference products:** Anara (anara.com) · Elicit (elicit.com)
**How to use this:** work through one item at a time, top to bottom. Tick the box, note the status, and move on.

---

## What is already solid

- [x] Authentication — Google OAuth sign-in/sign-up, JWT session tokens
- [x] Document pipeline — OCR, tables, figures/vision, citations, embeddings, vector search
- [x] Rate limiting — slowapi on auth routes + global middleware
- [x] Backend observability — Prometheus metrics, Loki logs, OpenTelemetry tracing
- [x] Deployment — Terraform (VPC/RDS/ECS/CloudFront/S3/ECR), Docker, CI
- [x] Landing page — positioning, product mockups, comparison table, pricing + legal pages

---

## 🚨 Launch blockers

### 1. Billing & payments
- [ ] Status: not started
- **Why:** the pricing page is informational; there is no way to pay. Anara's funnel is pricing → checkout → plan enforcement.
- **Done looks like:** Stripe (or equivalent) checkout on the pricing page, subscription management (cancel/renew), webhooks, receipts, and a payments test in staging.
- **Depends on:** plan enforcement (#2), pricing sign-off.

### 2. Plan enforcement & usage metering
- [ ] Status: not started
- **Why:** the token meter is hardcoded — `tokensRemainingPercent = 84` in `app-shell.component.ts`. Tier limits (AI words/day, uploads/day, MB/day, files in scope) are marketing copy, not enforced limits.
- **Done looks like:** server-side usage counters per user/plan, entitlement checks on chat/upload APIs, limit responses surfaced in the UI, free-tier abuse protection (one account per user).
- **Depends on:** nothing — can be built before payments and tested with the free tier.

### 3. Account deletion & data export
- [ ] Status: not started
- **Why:** the privacy policy promises deletion rights (GDPR/CCPA), but there is no "delete account" or "export my data" feature, and no backend cleanup of documents/embeddings/storage when an account goes.
- **Done looks like:** "Export my data" and "Delete account" in account settings; backend endpoint that removes user, documents, embeddings, and storage objects; confirmation + retention handled per policy.

### 4. Support channel
- [ ] Status: not started
- **Why:** the only contact is a misspelled Gmail address (`uderstandnotes@gmail.com`). No support inbox, help center, or contact form. Anara has support.anara.com; Elicit has docs + support.
- **Done looks like:** real support email at a custom domain (SPF/DKIM), a contact form or help center, and a documented response SLA.

### 5. Legal housekeeping
- [ ] Status: draft
- **Why:** privacy/terms are written but un-reviewed; company entity unnamed; "governing law = jurisdiction of residence" is weak; no refund policy, cookie-consent banner, DPA, or "Do Not Sell" disclosure; email typo unresolved.
- **Done looks like:** lawyer review; entity named; email typo fixed; cookie banner once analytics ship; refund policy; GDPR/CCPA contact process documented.

### 6. Onboarding / activation
- [ ] Status: not started
- **Why:** sign-up drops users straight into the workspace. Anara and Elicit both guide first-run: sample document, empty-state walkthrough, "upload → ask → verify" moment.
- **Done looks like:** first-run coach marks or checklist, sample document option, empty states that explain value, and a measurable activation event (first question answered with a citation).

### 7. Plan ↔ product reality check
- [ ] Status: needs audit
- **Why:** pricing promises files-in-scope, deep research across the library, text-to-speech, advanced models. Each must exist and be gated; do not imply collaboration if it isn't shipped.
- **Done looks like:** every priced feature maps to a shipped capability and an enforcement rule; pricing copy adjusted where the product can't deliver yet.

---

## ⚠️ Important (before or just after launch)

### 8. SEO & metadata
- [ ] Status: broken
- **Why:** `index.html` title still says "Your documents now with a voice and a mind."; no meta description, OG/Twitter tags, canonical, sitemap.xml, robots.txt, or JSON-LD.
- **Done looks like:** title updated to match positioning, description + OG image (1200×630), canonical, sitemap + robots, and product/SoftwareApplication schema.

### 9. Product analytics & error tracking
- [ ] Status: not started
- **Why:** backend has OTel/Prometheus but there is no frontend analytics or JS error tracking.
- **Done looks like:** privacy-respecting analytics (e.g., PostHog/Plausible) with consent banner, and Sentry (or equivalent) for frontend + backend errors; key funnels tracked (sign-up → first question → retention).

### 10. Security hardening
- [ ] Status: partial
- **Why:** session tokens live in localStorage (XSS exposure); Google OAuth consent screen needs prod-domain verification; no security.txt; no dependency audit in CI.
- **Done looks like:** token storage reviewed (httpOnly cookie option), OAuth verified, `security.txt`, CI dependency audits (`npm audit`, pip-audit), upload limits enforced server-side per plan.

### 11. Domain & transactional email
- [ ] Status: not started
- **Why:** no SMTP/SendGrid/Resend anywhere; no receipts, plan-change emails, or security alerts.
- **Done looks like:** transactional email provider wired, custom-domain sender with SPF/DKIM, templates for welcome/receipt/cancel/security notices.

### 12. Docs & help center
- [ ] Status: not started
- **Why:** no FAQ, user guides, or changelog. Users will ask how citations, tables, and OCR work.
- **Done looks like:** help center or docs pages: getting started, upload limits, citations/trust scores, OCR, pricing FAQ, troubleshooting.

### 13. Real social proof
- [ ] Status: unverified
- **Why:** homepage claims "10,000+ scholars and researchers" with no logos or testimonials; comparison table ✓/◐/✕ ratings never signed off.
- **Done looks like:** named logos or verifiable stats, 2–3 real testimonials with names/roles, and sign-off on every comparison-table claim with a verification date.

### 14. Landing claims verification
- [ ] Status: needs pass
- **Why:** "works across thousands of files", "Free during preview · No credit card required", and the demo mockup content need to match reality before launch.
- **Done looks like:** a final copy pass against shipped behavior; demo mockup content confirmed for public use.

### 15. Backups & data lifecycle
- [ ] Status: infra exists, process untested
- **Why:** need tested restore, retention jobs, and deletion propagation (account → documents → embeddings → storage).
- **Done looks like:** documented backup/restore drill, retention schedule, and deletion path wired to account deletion (#3).

### 16. Status page & alerting
- [ ] Status: not started
- **Why:** OTel stack exists but there is no public status page or alert routing.
- **Done looks like:** status page (e.g., statuspage-style), uptime checks, and alerts to Slack/PagerDuty on API/worker degradation.

---

## ✨ Polish

### 17. Pricing page extras
- [ ] Status: not started
- **Done looks like:** pricing FAQ (what happens at limits, cancellation, refunds), refund policy page, and a "what's included" expander per tier.

### 18. Cookie consent & privacy UX
- [ ] Status: not started
- **Done looks like:** consent banner when analytics ship, "Do Not Sell/Share" link where required, DSAR contact flow.

### 19. Accessibility & performance
- [ ] Status: partial
- **Done looks like:** focus states on landing/pricing/legal links, mobile menu close-on-escape, lazy-load Google GSI script off the landing page, font loading with preconnect.

### 20. Launch content
- [ ] Status: not started
- **Done looks like:** changelog/blog post, product screenshots (from the real app, not mockups), social share image, and a launch announcement plan.

---

## Suggested order

1. **#8 SEO/metadata** — quick, fixes an active contradiction on the homepage
2. **#4 Support channel** — cheap and unblocks everything else
3. **#2 Plan enforcement** — buildable now, testable with the free tier
4. **#3 Account deletion/export** — legal requirement, moderate effort
5. **#1 Payments** — depends on #2, the real revenue unlock
6. Then the rest in any order that fits the launch date
