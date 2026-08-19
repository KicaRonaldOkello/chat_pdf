# Understanding Notes — Homepage Redesign Recommendations

**Reference sites scanned:** [anara.com](https://anara.com/) — "AI tailored for scientific research" · [elicit.com](https://elicit.com/) — "AI for scientific research"
**Current file:** `frontend/src/app/landing/landing.component.{html,scss,ts}`
**Positioning (current):** "Deep understanding, powered by AI."
**Audience for this document:** designers and frontend implementers
**Date:** 2026-08-19

---

## 1. Executive summary

Anara's homepage converts because it answers three questions in the first screen and proves every claim on the way down the page:

1. **What is this?** — the hero says exactly what the product does, for whom, with a quantified proof point ("4× more accurate than general-purpose AI").
2. **Does it work?** — the hero and every feature section show the actual product interface (chat, citations, file list) instead of decorative photography.
3. **Why trust it?** — the page ends with an accuracy benchmark against named competitors, then enterprise security certifications and integrations.

Elicit represents the second successful model: an **editorial, manifesto-driven homepage** ("Stand on the shoulders of giants") that wins on tone and brand rather than benchmark charts. Understanding Notes already has Elicit's DNA — the Newsreader serif, the editorial voice — but it stops halfway: it has the aspirational headline without the clarifying product sentence, and no proof structure at all. The recommended direction is a **hybrid**: Elicit's emotional hero language and brand voice, with Anara's proof-driven layout underneath.

The positioning — **deep understanding, powered by AI** — is strong and should drive the hero headline. It also implies a differentiator the homepage never shows: Understanding Notes reads the *whole document* (text, scanned pages, tables, figures), not just the text layer. That is exactly what the comparison table (Section 7) should prove against ChatGPT and Claude.

---

## 2. The two reference models

### Anara — the proof-driven model

| Position | Section | What it contains |
| --- | --- | --- |
| 1 | Sticky header | Logo, nav, sign-in, primary CTA |
| 2 | Hero | "AI tailored for scientific research" + one-sentence capability summary + quantified claim + CTA |
| 3 | Product demo | A real chat UI mock: user question → answer with cited file chips |
| 4 | Feature highlights | 3 features, each with a mini product UI as proof (Perfect memory, Cited answers, Built for scale) |
| 5 | How it works | Numbered process steps |
| 6 | Benchmark | Bar chart vs. 5 named competitors with numeric results |
| 7 | Security & integrations | SOC 2 / ISO / GDPR / HIPAA badges + connector logos |
| 8 | Footer | Standard conversion footer |

The pattern behind every section: **claim + visual proof + one clear next action**.

---

### Elicit — the second reference model

Elicit's homepage, in contrast, is editorial and aspirational:

| Position | Section | What it contains |
| --- | --- | --- |
| 1 | Hero | Aspirational H1 "Stand on the shoulders of giants" + one concrete sentence explaining the product: "Use Elicit to understand more quickly what science already knows, so that you can discover the unknown." |
| 2 | Capability overview | "Research takes many forms" — Library, Alerts: product capabilities framed around the researcher's workflow |
| 3 | Manifesto | A long mission statement ("This is an important moment in time...") that works because it arrives *after* the product is clear |

**What to learn from Elicit:**
- An aspirational headline works when the very next sentence names the product behavior. Elicit pairs an emotional H1 with a subhead that tells you exactly what the tool does, for whom, and why. The current Understanding Notes H1 is aspirational, but the subhead repeats the H1's idea instead of explaining the product.
- A mission/manifesto section is not inherently wrong — it is wrong **in position and in repetition**. Elicit places its manifesto at the end, once; the current page puts a vision statement near the top that repeats the hero headline verbatim.
- Capabilities can be presented as workflow outcomes ("quick answer" vs. "multi-month comprehensive review") rather than feature names. That framing speaks to the user's job, not the product's modules.
- Elicit's homepage converts on brand alone because Elicit is already famous. For an early-stage product, brand-only persuasion is riskier — proof (Anara's approach) is the safer spine.

---

## 3. Diagnosis of the current homepage (what's holding it back)

### 3.1 Header

- The logo is **110px tall**, which dominates the header; at that height it reads as a billboard, not a brand mark. Reduce to ~56–72px.
- Nav links are **hidden entirely below 768px** (`.landing-nav { display: none }`) — mobile visitors get no navigation. A hamburger menu is required.
- "Offerings" is vague as a nav label. It should be "Features" or "Product".
- Anchor targets are broken: `id="about"` appears **twice** (vision section and feature 02), and the "Offerings" nav anchor points at feature 03's id instead of a real offerings section.

### 3.2 Hero (position 1)

- Eyebrow says "Our Mission" — a visitor is not looking for a mission; they are looking for what the site does.
- H1 "To make every document as easy to understand." is a vision statement. It does not tell the user the product exists, what it does, or how to use it.
- The lead "The default way people and teams read, understand, and trust their documents." repeats the H1 idea without adding information.
- The hero image is a decorative, grayscale antique-book photograph. It says "books", not "software". It demonstrates nothing and builds no trust.
- There is a single CTA ("Begin Research") with no secondary path for people who need more convincing before committing.

### 3.3 Social-proof strip (position 2)

- "Trusted by over 10,000 scholars and researchers" is an unverifiable claim with no logos, numbers, or testimonials beside it. Unsourced claims can hurt credibility more than they help.

### 3.4 Vision section (position 3)

- The H2 is nearly identical to the hero H1 — the same sentence appears twice on one page.
- The body is philosophy, not product information. No visitor learns what they can *do*.
- The "Get Early Access" CTA routes to `/sign-in`, which reads as a login wall, not an offer.

### 3.5 Features (position 5)

- Features are labeled by capability ("Chat", "Summaries", "Voice") rather than by user outcome.
- Each feature describes what it does but shows no proof: one feature has a faded icon, another a decorative sound-wave image. There are no product screenshots.
- The three features have no logical narrative order (chat → summaries → text-to-speech) and no "How it works" bridge.

### 3.6 CTA section (position 7)

- "Experience Clarity." + "No subscription required for initial inquiry." is a slogan, not an offer. There is no mention of price, free tier, or what the user gets.
- "Get Started" is a third distinct CTA label ("Begin Research" elsewhere); labels should be consistent.

### 3.7 Footer

- Placeholder content: fake address ("123 address st."), "Offering 1 / 2 / 3", and "Contact Us" linked to `/sign-in`.
- No product/company link structure, no legal links, no social links, no newsletter.

---

## 4. Recommended homepage structure (section-by-section spec)

This is the target page flow. Each section includes placement, content, copy suggestions, and designer notes.

### Section 1 — Sticky header

**Position:** fixed at top, full width, ~72px tall, white 95% + backdrop blur.

**Layout (desktop):**
- Left: logo at **56–72px height** (reduced from 110px).
- Center: nav links — Home, **What it does** (→ #what-it-does), **How it works** (→ #how-it-works), **Features** (→ #features), **Compare** (→ #compare), **Security** (→ #security).
- Right: "Sign in" text link + primary button "Get started" (→ `/sign-up`).

**Layout (mobile):** same logo + right-aligned hamburger; slide-down menu with the same links and CTA. The mobile menu is currently missing entirely — this is a must-fix.

**Designer notes:** keep the current green `#00B074` for the primary CTA. Add a subtle bottom border on scroll. Ensure the header is sticky, not fixed, so content never overlaps it.

---

### Section 2 — Hero (above the fold)

**Position:** directly below header. **Desktop:** two columns — copy left (55%), product mockup right (45%). **Mobile:** stacked, mockup below copy.

**Content:**

| Element | Current | Recommended |
| --- | --- | --- |
| Eyebrow | "Our Mission" | "For researchers, analysts, and teams" (audience, not mission) |
| H1 | "To make every document as easy to understand." | **Primary (from your positioning):** "Deep understanding, powered by AI." · **Alternative (editorial):** "Every document, deeply understood." |
| Subhead | "The default way people and teams read, understand, and trust their documents." | "Upload your documents — PDFs, scans, tables, and figures — and ask anything. Understanding Notes reads them deeply and answers with every claim cited to the exact page, table, or chart." |
| CTA pair | Single "Begin Research" | Primary "Begin research" (→ `/sign-up`) + secondary text link "See it in action" (→ scroll to Section 3) |
| Proof line | — | "Free during preview · No credit card required" |

**Right column — product mockup (critical change):**
- Replace the antique-book photograph with a **real product screenshot or high-fidelity mockup of the chat interface**: a question in the composer, an AI answer, and a highlighted citation chip pointing to a page in the document panel.
- Add a small caption under the mockup: *"Every answer cites the exact page, table, or chart."*
- The mockup must look like the actual app — this is the single most important trust element on the page.

**Designer notes:** keep the Newsreader serif headline (it is the brand differentiator). Option A is the safer conversion play; Option B matches Elicit's emotional register — but with either option, the subhead must do the product-explaining (the Elicit pattern), because the current subhead only repeats the H1. Left-align on desktop; center on mobile. Add a 1px divider below the section, or a soft gradient into the next section.

---

### Section 3 — Product demo ("See it in action")

**Position:** second scroll, full width. This is Anara's strongest section and is missing entirely.

**Content:**
- Eyebrow: "See it in action"
- H2: "One question. Every answer sourced."
- An **interactive or animated product mockup**: left side shows a document library/file list; right side shows a chat exchange:
  - *User:* "What were the main causes of battery degradation in this study?"
  - *AI answer:* 2–3 sentence summary with a highlighted citation chip: "Source: battery-study.pdf, page 12".
- Under the mockup, three capability chips with short labels:
  - "Answers cite the exact passage"
  - "Works across thousands of files"
  - "Summaries, transcripts, and exports"

**Designer notes:** this mockup should be the visual anchor of the page — larger than the hero mockup, on a contrasting background (light gray `#f8f8f8` panel or dark `#18181B` panel) so it reads as a product, not a screenshot of the page. If animating, use a simple typing effect triggered on scroll into view.

---

### Section 4 — "What it does" (replaces the Vision section)

**Position:** third scroll. Replace the current philosophy/vision block.

**Content:**
- Eyebrow: "What it does"
- H2: "A research workspace that reads everything for you."
- Three-column capability grid, each with icon, title, and 2–3 sentence description:

1. **Read** — "Upload PDFs, scanned pages, tables, and figures. Understanding Notes indexes the whole document — not just the text layer."
2. **Understand** — "Get concise summaries, structured answers, and comparisons — built from your documents alone, with every claim cited."
3. **Trust** — "Every answer points back to the exact passage it came from. Your documents are never used to train models."

- One CTA below the grid: "Begin research" (→ `/sign-up`).

**Designer notes:** remove the duplicated headline (the current vision H2 repeats the hero H1). Keep the editorial split layout if preferred, but the copy must describe product behavior, not brand philosophy. Cards: white background, 1px `#E4E4E7` border, 16–20px radius, hover lift.

**Elicit framing idea:** Elicit presents capabilities as researcher workflows ("quick answer" vs. "multi-month comprehensive review") rather than module names. If the Read/Understand/Trust cards feel too feature-like, reframe them as journeys: "Quick answers from one document," "Deep reviews across your library," "Verified writing you can export."

---

### Section 5 — How it works

**Position:** fourth scroll, directly after "What it does" (matches Anara's pattern and the nav).

**Content:** three numbered steps in a horizontal row (stacked on mobile):

1. **Upload** — "Add your PDFs, reports, and notes. Understanding Notes reads and indexes everything."
2. **Ask** — "Chat with one document or your entire library. Ask for summaries, comparisons, or specific passages."
3. **Verify & use** — "Check every answer against its cited source, then export the summary or citation."

**Designer notes:** use large ghost numerals (01 / 02 / 03) in the serif typeface as the visual motif, matching the existing "01 / Chat" eyebrow style. Keep each step to one line of heading + one line of body on desktop. Add thin connector lines between steps on desktop.

---

### Section 6 — Features with proof

**Position:** fifth scroll. Keep the alternating editorial layout but rewrite each feature and pair it with proof.

| Feature | Current copy problem | Recommended heading | Proof element |
| --- | --- | --- | --- |
| 01 Chat | "Chat with documents" — generic | "Chat with your documents" | Mini Q&A mockup: question, answer, highlighted citation |
| 02 Summaries | "Smart summarization" — generic | "Summaries you can verify" | Before/after mockup: dense paragraph → 3 bullet points with source line |
| 03 Voice | "AI Text to Speech" — fine, but unproven | "Listen to your research" | Audio-player mockup with waveform + "sample" play button |

Each feature row keeps: eyebrow (01 / 02 / 03), serif title, 1–2 sentence body, and a "Try it" text link (→ `/sign-up`).

**Designer notes:** alternate text-left/text-right on desktop exactly as today, but replace the icon block and decorative sound-wave image with **product UI mockups** (chat bubble, summary card, audio player). Proof mockups should share one consistent visual language (same window chrome, same green accent).

---

### Section 7 — Comparison table (Understanding Notes vs. ChatGPT & Claude)

**Position:** sixth scroll, directly after the features (`id="compare"`). This is the homepage's evidence centerpiece — the equivalent of Anara's benchmark chart, but built around the positioning ("deep understanding") rather than a generic accuracy score.

**Content:**
- Eyebrow: "Why it's different"
- H2: "Built for documents. Not general chat."
- Intro line: "ChatGPT and Claude are brilliant generalists. Understanding Notes is built for one thing: reading your documents — text, scans, tables, and figures — and answering from what's actually there."
- The comparison table (drafted below), with a footnote: *"Feature availability in ChatGPT/Claude varies by plan and model version. Verified against public documentation as of August 2026."*

**Drafted table content (copy as-is or adjust tone):**

| Capability | Understanding Notes | ChatGPT | Claude |
| --- | --- | --- | --- |
| **Documents** | | | |
| Reads PDFs end-to-end (text, layout, structure) | ✓ Purpose-built document pipeline | ◐ Works as a chat attachment — no document-level indexing | ◐ Works as a chat attachment — no document-level indexing |
| Scanned / handwritten pages (OCR) | ✓ Automatic OCR routing for scanned and image-based PDFs | ✕ No dedicated OCR pipeline | ✕ No dedicated OCR pipeline |
| Answers across your whole library (thousands of files) | ✓ Indexed library — ask across every upload | ✕ Limited to what fits in one conversation | ✕ Limited to what fits in one conversation |
| **Tables** | | | |
| Extracts tables as structured data (rows & columns) | ✓ Tables parsed and stored with row/column structure | ◐ Reads simple tables; struggles with complex or multi-page layouts | ◐ Reads simple tables; struggles with complex or multi-page layouts |
| Answers from table content and cites the table | ✓ Answer points to the exact table and page | ✕ No guaranteed source citation | ✕ No guaranteed source citation |
| **Images & figures** | | | |
| Reads figures *inside* your documents automatically | ✓ Every figure is captioned, described, and indexed | ✕ Only images you manually upload | ✕ Only images you manually upload |
| Reads charts, diagrams, axes & legends | ✓ Query-time vision analysis of the actual page | ◐ Can describe pasted images, inconsistently | ◐ Can describe pasted images, inconsistently |
| Detects signatures, stamps, handwriting | ✓ Vision analysis flags them on the page | ✕ Not a document-analysis capability | ✕ Not a document-analysis capability |
| **Trust** | | | |
| Every answer cited to the exact source | ✓ Passage, table, or figure — clickable | ✕ No guaranteed citation; may invent sources | ✕ No guaranteed citation; may invent sources |
| Your documents never train models | ✓ | ✕ Unless disabled in enterprise settings | ✕ Unless disabled in enterprise settings |

**Designer notes:**
- Layout: full-width table on desktop with a sticky first column; collapse to a per-category card layout on mobile (group rows under "Documents," "Tables," "Images").
- Markers: use a consistent icon system — ✓ (green, full capability), ◐ (amber, partial), ✕ (gray, not built for this). Add tooltips with the evidence for each ✓ (e.g., "Scanned PDFs are auto-detected and routed through OCR").
- The ✓ column is the hero: make it visually strongest with the green `#00B074` accent; the comparison columns stay neutral.
- Keep the claims defensible: every ✓ must reflect a shipped capability (the current pipeline does OCR, structured table extraction, and vision analysis of figures — verified in the backend), and every ✕ must be true of the competitor's public product as of the date shown in the footnote.
- Optional additions below the table: a stats band (real numbers only) or 2–3 named testimonials if available.

**Optional stats band (only with real numbers):** big-number grid — "10,000+ files in one workspace," "100% of answers sourced," "OCR for scanned documents" — placed under the table.

---

### Section 8 — Security & privacy

**Position:** seventh scroll.

**Content:** two-column split:
- Left: H2 "Built for private, sovereign work" + body: "Your documents stay yours. Sessions are encrypted, and Understanding Notes never trains models on your documentation."
- Right: a trust-badge grid — Encryption, No training on your data, SSO/role management, [any real certifications such as SOC 2, ISO 27001 — only if certified].

**Designer notes:** use a clean badge grid (2×2 or 3×2 chips with icons). This content already exists in essence on the sign-in page margin note — surface it on the homepage where it builds trust before sign-up.

---

### Optional — Manifesto block (Elicit pattern)

**Position (if used):** between the evidence section and the final CTA — late in the page, once, never above the fold.

**Content:** the current "Our Vision" copy, rewritten once and placed here: "We believe understanding is a right, not a privilege…" This is exactly where Elicit puts its manifesto ("This is an important moment in time…") — after the product is clear, so the emotion lands instead of obscuring the product.

**Designer notes:** use the editorial serif at large size with generous spacing; a quiet, left-aligned block on white. Keep it to one paragraph plus, at most, a single supporting line. Do not pair it with a CTA — the next section owns conversion.

---

### Section 9 — Final CTA

**Position:** eighth scroll (ninth if the optional manifesto is used), last content section.

**Content:**
- H2: "Begin research today."
- Sub: "Free during preview · No subscription required."
- Primary CTA: "Begin research" (→ `/sign-up`).

**Designer notes:** keep it short — all persuasion has already happened above. Use the current gray band or invert to a dark panel (`#18181B`) with white type and the green button for a strong closing contrast.

---

### Section 10 — Footer

**Position:** bottom.

**Content and fixes:**
- Replace the placeholder address with real contact information (or remove it).
- Column 1 "Product": Features, How it works, Security, Pricing.
- Column 2 "Company": About, Contact, Privacy Policy, Terms of Service.
- Fix "Contact Us" — it must not link to `/sign-in`.
- Replace "Offering 1 / 2 / 3" placeholder links with the real anchors.
- Optional: email capture ("Get research updates") as the footer's conversion element.

---

## 5. Cross-cutting design recommendations

1. **Product mockups over photography.** Every Anara section that makes a claim shows the product proving it. Replace the hero book photo, the feature icon block, and the sound-wave image with consistent UI mockups.
2. **One headline, one meaning.** Remove the duplicate hero/vision headline; each section should have a distinct message.
3. **Consistent CTA language.** Use "Begin research" as the primary conversion label everywhere (header, hero, sections, final CTA). Reserve "Sign in" for returning users.
4. **Fix navigation fundamentals.** Unique `id` per anchor, real hrefs, and a mobile menu at <768px.
5. **Type scale.** The 10px uppercase labels (social strip, footer meta) are too small; raise to 12px minimum with `letter-spacing` preserved.
6. **Performance.** The page loads two very large remote images from `lh3.googleusercontent.com`. Replace with locally optimized assets (WebP, ~1600px max, compressed).
7. **Accessibility.** Ensure the green `#00B074` button passes contrast for white text (it is borderline at small sizes); add `focus-visible` states on all links and buttons.

---

## 6. Implementation phases

**Phase 1 — Quick wins (same day):**
- Rewrite hero copy (audience eyebrow, product H1, capability subhead).
- Reduce logo height in the header.
- Fix duplicate `id="about"`, broken anchors, footer placeholders, "Contact Us" link.
- Rename nav "Offerings" → "Features"; add mobile hamburger menu.

**Phase 2 — Trust through visuals (1–2 sprints):**
- Build the hero product mockup and the Section 3 demo mockup from real UI screenshots.
- Add "What it does" + "How it works" sections.
- Rewrite feature rows with proof mockups.
- Replace remote images with optimized local assets.

**Phase 3 — Social proof (as data becomes real):**
- Add the Section 7 comparison table (requires a final sign-off on each ✓/◐/✕ claim).
- Add stats band or testimonials with real numbers.
- Add security/integrations section with genuine certifications.
- Add pricing teaser and footer newsletter.
