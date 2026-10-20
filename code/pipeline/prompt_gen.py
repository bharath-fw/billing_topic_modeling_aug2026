"""Step 6b: Generate the guided "ChatGPT Excel Plugin" tagging prompt.

The prompt is generated from the governed 104-leaf vocabulary
(``artifacts/canonical_vocabulary.csv``) so it never drifts from the taxonomy.
It is written for the *monthly-worksheet* workflow produced by ``build_xlsx.py``:
the user uploads the workbook (one sheet per calendar month), and asks ChatGPT to
classify each month's rows in turn, writing the ai_tag_* columns back into each
month's worksheet (batched inference, one month at a time).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "code" / "artifacts"
OUT = ROOT / "code" / "output"

VOCAB_PATH = ARTIFACTS / "canonical_vocabulary.csv"

OUTPUT_COLS = [
    "ai_tag_1", "ai_category_1", "ai_subcategory_1",
    "ai_tag_2", "ai_category_2", "ai_subcategory_2",
    "ai_tag_3", "ai_category_3", "ai_subcategory_3",
]

INPUT_COLS = [
    "BAN", "record_id", "Call_Date", "Call_Month",
    "Customer Intent Tag", "Problem Identified Tag",
    "Reason", "Summary", "Queue Category", "Conversation ID", "QueueName",
]

NARRATIVE_FIELD = (
    "Build a single call narrative per row by concatenating these columns, "
    "in this order: `Customer Intent Tag`, `Problem Identified Tag`, `Reason`, "
    "`Summary`. Treat the concatenation as one structured customer-intent text. "
    "`Customer Intent Tag` and `Problem Identified Tag` are the shortest and most "
    "salient; `Reason` and `Summary` add context. Use all four together to decide "
    "the intent — never rely on `Queue Category` or `QueueName` alone."
)


def build_prompt(vocab: pd.DataFrame, fallback_tag: str = "OTHER_MISC_OTHER_BILLING") -> str:
    cats = vocab.groupby("category")
    vocab_section = []
    for cat, g in cats:
        g = g.sort_values("subcategory")
        vocab_section.append(f"### {cat} ({(g.shape[0])} tags)")
        vocab_section.append("")
        vocab_section.append("| canonical_tag | subcategory | definition |")
        vocab_section.append("|---|---|---|")
        for _, r in g.iterrows():
            vocab_section.append(f"| {r['canonical_tag']} | {r['subcategory']} | {r['definition']} |")
        vocab_section.append("")

    n_tags = len(vocab)

    return f"""# Brightspeed Billing & Payments Call Classifier — ChatGPT Excel Plugin Prompt

> **Guided, controlled-vocabulary prompt for tagging the monthly billing workbook.**
> Use this in ChatGPT (with the Excel/Analysis plugin, or by uploading the workbook).
> The vocabulary below is EXHAUSTIVE and FROZEN — do not invent, rename, merge, split,
> abbreviate, or rephrase any tag.

---

## Workflow (batch per worksheet)

1. Open/upload the workbook **`billing_tagging_input.xlsx`**. It has **one worksheet per
   calendar month** (e.g. `Jan_2026`, `Feb_2026`, …, `Aug_2026`) plus an `Overview` sheet.
2. You will classify **one worksheet (one month) at a time**. Do NOT try to classify all
   months in a single pass if a sheet is very large — process month by month so each batch
   is self-contained and auditable.
3. For each worksheet, read the existing columns and **append** the nine output columns
   (they are pre-created and empty):
   {', '.join('`' + c + '`' for c in OUTPUT_COLS)}
4. Write one row per input row, in the same order. **Do not drop, reorder, or edit any
   input columns.** Leave rank-2 / rank-3 cells blank unless the call genuinely has more
   than one independent billing ask.
5. When a sheet is done, move to the next month. At the end, save the workbook back as
   the **tagged** file (e.g. `billing_tagged_ytd.xlsx`).

---

## System role & rules (apply to every row)

You are a Brightspeed billing-and-payments call classifier. You classify each call's
customer intent into a CONTROLLED VOCABULARY of exactly **{n_tags}** canonical tags across
{len(cats.groups)} categories.

**Input fields used:** {NARRATIVE_FIELD}

**Rules — read before classifying any row:**

1. **VOCABULARY LOCK:** Only output tags from the CANONICAL VOCABULARY table below. Never
   invent, abbreviate, rephrase, merge, or split a tag. If no specific tag fits, use
   `{fallback_tag}`.

2. **ONE PRIMARY TAG (required):** Every row MUST receive exactly one `ai_tag_1`.

3. **OPTIONAL SECONDARY/TERTIARY:** Use `ai_tag_2` (and `ai_tag_3`) ONLY when the call
   clearly contains a SEPARATE and INDEPENDENT billing ask — a genuinely different topic
   also raised. Do NOT create extra tags for:
   - restatements / rephrasing of the same issue;
   - causes or consequences of the same problem (e.g. a "late fee" caused by a
     "payment not posted" is ONE ask);
   - background account facts or context;
   - alternate plausible readings of the same issue.
   Leave unused rank cells BLANK.

4. **SPECIFICITY:** Always choose the MOST SPECIFIC tag that fits the customer's stated
   ask. "Payment issue" is too general when `PAY_PAYMENT_NOT_POSTED` or another
   specific tag fits.

5. **STYLE LOCK:** Do not adapt tag names to match customer wording. Customer language
   varies; the vocabulary is fixed.

6. **CATEGORY/SUBCATEGORY:** For each selected tag copy `category` and `subcategory`
   EXACTLY as written in the vocabulary table. Output the exact `canonical_tag` string,
   character-for-character.

7. **CONFIDENCE / HONESTY:** When genuinely uncertain, use `{fallback_tag}`. Do not guess
   and do not invent a near-match tag. No commentary columns; output only the nine columns.

---

## CANONICAL VOCABULARY ({n_tags} tags)

{chr(10).join(vocab_section)}

---

## Anti-drift examples

| Customer says | Correct | WRONG (do not output) |
|---|---|---|
| "my bill is crazy high" | RATE_BILL_HIGHER_THAN_EXPECTED | BILL_TOO_HIGH |
| "they charged me twice" | ERR_DUPLICATE_CHARGE | DOUBLE_BILLED |
| "I can't get into my account" | ACCT_ONLINE_ACCOUNT_ACCESS_VERIFICATION | LOGIN_ISSUE |
| "where's my refund?" | CRD_REFUND_NOT_RECEIVED_REFUND_STATUS | MISSING_REFUND |
| "AutoPay charged me the wrong amount" | AUTO_AUTOPAY_CHARGED_WRONG_AMOUNT | AUTO_AUTOPAY_PAYMENT_FAILURE |

---

## Output contract

Per worksheet, fill exactly these columns for every row (rank-2/3 optional, else blank):

| column | meaning |
|---|---|
| ai_tag_1 | primary canonical tag (required) |
| ai_category_1 | category of ai_tag_1 |
| ai_subcategory_1 | subcategory of ai_tag_1 |
| ai_tag_2 | secondary canonical tag (only if a truly separate ask exists) |
| ai_category_2 | category of ai_tag_2 |
| ai_subcategory_2 | subcategory of ai_tag_2 |
| ai_tag_3 | tertiary canonical tag (only if a third distinct ask exists) |
| ai_category_3 | category of ai_tag_3 |
| ai_subcategory_3 | subcategory of ai_tag_3 |

Process EVERY month worksheet, one at a time, then save the workbook.
Review rows tagged `{fallback_tag}` — they may need manual review (a modest fallback
rate is expected and acceptable; do NOT force them into a specific label).
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vocab", type=Path, default=VOCAB_PATH)
    ap.add_argument("--out", type=Path, default=OUT / "ChatGPT_Plugin_Guided_Prompt.md")
    args = ap.parse_args()
    vocab = pd.read_csv(args.vocab)
    prompt = build_prompt(vocab)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(prompt)
    print(f"guided prompt written ({len(vocab)} tags, "
          f"{vocab['category'].nunique()} categories) -> {args.out}")


if __name__ == "__main__":
    main()
