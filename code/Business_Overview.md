# Brightspeed Billing Taxonomy — Business Overview

> A data-driven classification system that organizes every customer billing contact into a governed, auditable, and AI-scoreable taxonomy — built from real call data, validated by experiment, and ready for self-serve use.

---

## The business problem

Brightspeed handles millions of customer contacts per year. A significant portion are billing-related — customers calling about their bill, a charge, a payment, a refund, or a service change with billing impact.

**Without a taxonomy,** these contacts are a undifferentiated mass. You cannot answer basic questions:

- What are customers actually calling about?
- Which billing issues are growing?
- Where are agents spending the most time?
- What is the root cause of billing-related churn risk?

**With a taxonomy,** every contact gets a precise, consistent label. The same question asked a thousand different ways — "my bill is wrong," "I was charged twice," "why is this on my statement" — maps to the correct category. Reporting becomes reliable. Trends become visible. Action becomes possible.

---

## What was built

A two-level billing taxonomy was constructed from 7 months of Brightspeed call data (January–July 2026):

| | Count |
|---|---|
| Raw customer contacts analyzed | **5,000,000+** |
| Billing contacts identified | **832,885** |
| Macro categories | **10 + 1 fallback** |
| Specific subcategories (canonical tags) | **104** |
| Source reason observations mapped | **111,836** |
| Representative texts curated per subcategory | **10 each (1,040 total)** |

The taxonomy covers the full spectrum of Brightspeed billing contacts — from "what is my balance" to "I need to understand a prorated charge after moving" to "my promotional gift card never arrived."

---

## How it was built — experimental rigor

This was not a subjective labeling exercise. The taxonomy was discovered from the data through a structured, repeatable process:

### Stage 1 — Discovery

Every billing contact was converted into a semantic fingerprint (a mathematical representation of its meaning). A machine learning kernel then automatically separated billing contacts from non-billing contacts — ensuring the taxonomy explains only billing, not service or sales.

### Stage 2 — Pattern identification

Multiple pattern-finding algorithms were tested against each other. Each was scored on four criteria: how well-separated the groups were, how consistently they appeared across all 7 months, how much of the data they covered, and how well they mapped to known Brightspeed billing concepts.

**The winning approach was validated by comparison, not chosen by default.**

### Stage 3 — Refinement

The raw patterns were reviewed for:

- Overlapping groups that should be merged
- Valid but rare billing reasons that would otherwise be lost
- Billing topics that the current data doesn't show yet but that Brightspeed customers will inevitably have
- Clear boundaries between categories (e.g., "late fee dispute" vs. "late fee waiver" are different customer intents)

### Stage 4 — Governance

The final vocabulary was approved through a governance step that balances data evidence with business judgment. Some categories exist because the data strongly supports them. Others exist because they are operationally necessary even if current volume is low. A fallback category catches anything that doesn't fit a specific label.

---

## The final taxonomy — 10 macro categories plus 1 fallback category

| # | Category | What it covers |
|--:|---|---|
| 1 | Bill Understanding and Balance | Questions about amounts owed, due dates, line items, first bills, prorated charges |
| 2 | Rates Discounts and Recurring Charges | Price increases, promotional rate expirations, discount requests, recurring charge inquiries |
| 3 | Billing Errors Fees and Taxes | Incorrect charges, duplicate charges, late fees, tax inquiries, billing after cancellation |
| 4 | Payments and Payment Posting | Making payments, payment not posted, wrong account, confirmations, payment history |
| 5 | AutoPay and Payment Methods | AutoPay enrollment, failures, amount errors, payment method updates, compromised cards |
| 6 | Payment Assistance Past Due and Collections | Payment arrangements, past-due balances, service suspension, collections, credit concerns |
| 7 | Credits Refunds and Adjustments | Credit requests, refund status, outage credits, overpayment refunds, deposit returns |
| 8 | Billing Delivery Account and Preferences | Bill copies, paperless billing, account access, address/contact updates |
| 9 | Promotions Rewards and Gift Cards | Gift card status, reward inquiries, promotion eligibility and fulfillment timing |
| 10 | Service Changes Equipment and Final Billing | Cancellation billing, equipment charges, vacation holds, move/transfer billing, upgrades |
| 11 | Other Category | Billing-related contacts that don't fit a specific subcategory |

---

## What the data shows

### Tagging results across 832,885 billing contacts

| Outcome | Count | Share |
|---|---:|---:|
| Classified with a specific billing topic | **760,963** | **91.4%** |
| Needed a second topic (genuinely multi-issue) | **45,288** | **5.4%** |
| Needed a third topic | **2,820** | **0.3%** |
| No specific topic fit (fallback) | **71,922** | **8.6%** |

**Key insight:** 94.2% of all billing contacts were resolved with a single, specific label. Only 5.8% required more than one topic — and those were genuinely multi-issue calls, not uncertainty padding.

The 8.6% fallback rate is deliberate. The system would rather say "this is billing, but I'm not sure which specific topic" than force a wrong label. This keeps reporting honest.

---

## Why this matters for the business

### Before the taxonomy

- Billing contacts were lumped into broad buckets (or no bucket at all)
- Trend analysis was unreliable — the same issue might be labeled differently by different agents or systems
- Root cause analysis required manual review of individual calls
- New billing issues were invisible until they became crises

### After the taxonomy

- Every contact gets a consistent, machine-readable label
- Category-level trends are visible in weekly/monthly reports
- Root cause analysis can be done at scale — "what is driving the 4,245 'bill higher than expected' calls this month?"
- Rare but legitimate issues (like vacation hold billing) are tracked even at low volume
- The vocabulary is stable — it does not drift with agent phrasing or seasonal language changes

---

## Self-serve AI scoring — how business users can classify calls

The taxonomy is not locked in a data science pipeline. It is available as a **self-serve tool** that any business user can operate through Excel and ChatGPT.

### What you need

1. A spreadsheet with a `call_intent` column (the customer's billing reason, as recorded)
2. The ChatGPT Excel plugin (or ChatGPT with file upload)
3. The classification prompt (provided in `ChatGPT_Prompt.md`)

### What you get

Nine new columns added to your spreadsheet:

| Column | Content |
|---|---|
| `ai_tag_1` | Primary classification tag (required) |
| `ai_category_1` | Category name |
| `ai_subcategory_1` | Subcategory name |
| `ai_tag_2` | Secondary tag (only if a second distinct billing issue exists) |
| `ai_category_2` | Category name |
| `ai_subcategory_2` | Subcategory name |
| `ai_tag_3` | Tertiary tag (only if a third distinct billing issue exists) |
| `ai_category_3` | Category name |
| `ai_subcategory_3` | Subcategory name |

### What makes this reliable

The prompt enforces a **controlled vocabulary** — the AI can only output the 104 approved tags. It cannot invent new ones. It cannot abbreviate. It cannot rephrase. It cannot merge or split existing categories.

This means:

- **Today's classifications are comparable to next month's.** The vocabulary does not drift.
- **Different users get the same result.** The prompt is deterministic.
- **The fallback is honest.** When the AI is unsure, it says so — it does not guess.

### Step-by-step for business users

1. Open your billing call spreadsheet in Excel
2. Open ChatGPT and upload the spreadsheet plus the prompt from `ChatGPT_Prompt.md`
3. ChatGPT reads the `call_intent` column and outputs the 9 classification columns
4. Review rows tagged `OTHER_MISC_OTHER_BILLING` — these may need manual review
5. Save the tagged file

---

## What this is not

| Claim | Reality |
|---|---|
| "AI classified all calls perfectly" | AI classified calls using a controlled vocabulary. 8.6% were flagged as uncertain. Human review is recommended for those. |
| "The 104 categories are final forever" | The taxonomy is governed. New categories can be added through a formal review process. The vocabulary is stable but not immutable. |
| "This replaces agent judgment" | This supplements agent judgment. The taxonomy provides consistent labels for reporting and trend analysis. Complex or ambiguous calls still need human review. |
| "Every tag has equal confidence" | Tags backed by thousands of observations are more reliable than tags backed by a few. The evidence count per tag is auditable. |

---

## Key files

| File | Purpose |
|---|---|
| `Taxonomy_Process_Tech.md` | Technical process report (methodology, algorithms, validation) |
| `ChatGPT_Prompt.md` | Self-serve classification prompt with controlled vocabulary |
| `input_output/billing_all_ytd.xlsx` | Raw input data |
| `input_output/billing_all_ytd_tagged.xlsx` | Fully tagged output |
| `artifacts/billing_taxonomy_workbook.xlsx` | Review workbook with vocabulary and usage notes |
| `artifacts/canonical_vocabulary.csv` | Machine-readable tag vocabulary |
| `artifacts/tree_hierarchy.md` | Complete taxonomy tree with definitions |

---

## Bottom line

This taxonomy was built from real data, validated by experiment, governed by business judgment, and made available for self-serve use. It turns 832,885 billing contacts from an undifferentiated mass into a structured, reportable, and actionable dataset — without requiring a data scientist to operate it.
