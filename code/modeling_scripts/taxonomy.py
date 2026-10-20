"""Parse the billing taxonomy files into a structured hierarchy.

Inputs (in the repo root):
    billing_categories.txt           : one top-level Category per line
    billing_subcategories_deeper.txt : Category headers + deeper sub-reasons

Output: a dict
    TAXONOMY = {
        "Bill Dispute": ["Late fee dispute", "Incorrect billing after disconnect", ...],
        ...
    }
    plus derived lists (CATEGORIES, SUB_CATEGORIES) and a curated vocabulary of
    canonical subcategory keys.

Subcategory names are canonicalised so they can be used as stable LVQ prototype
labels and class names in the scoring file.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAT_FILE = ROOT / "billing_categories.txt"
SUB_FILE = ROOT / "billing_subcategories_deeper.txt"

# A few duplicated / inconsistent names seen in the source file get folded onto a
# canonical key so the taxonomy has exactly one key per subcategory.
ALIASES = {
    "Late fee": "Late Fee",
    "Late fee ": "Late Fee",
    "Taxes & Regulatory Fees": "Tax & Other Charges",
    "tax recovery surcharge": "Bill higher than expected due to tax recovery surcharge",
    "General reward inquiry": "General reward inquiry",
    "Payment method update": "Payment method update",
}

# Subcategory rows that are clearly label-noise (survey junk, near-empty) are dropped.
SKIP_SUB = {"", "Customer reason", "Trend insight"}
_SUB_COLS = re.compile(r"^(.*?)\t\d")

_CAT_HEADER = re.compile(r"^(.*?)\s*\(\s*[\d,]+\)\s*$")


def _clean(name: str) -> str:
    name = name.strip().rstrip(" \t.,-")
    return name


def parse_categories() -> list[str]:
    cats = []
    for line in CAT_FILE.read_text().splitlines():
        c = _clean(line)
        if c:
            cats.append(c)
    return cats


def parse_taxonomy() -> dict[str, list[str]]:
    """Parse billing_subcategories_deeper.txt into {category: [subcategories]}."""
    taxonomy: dict[str, list[str]] = {}
    current: str | None = None
    for raw in SUB_FILE.read_text().splitlines():
        line = raw.rstrip("\n")
        m = _CAT_HEADER.match(line)
        if m and not line.startswith("Customer reason") and "Count" not in line:
            current = _clean(m.group(1))
            taxonomy.setdefault(current, [])
            continue
        if line.startswith("Trend insight"):
            continue
        if not line.strip() or line.startswith("Customer reason"):
            continue
        if current is None:
            continue
        # sub-reason row: name is the leading field before the first tab + count
        mm = _SUB_COLS.match(line)
        name = _clean(mm.group(1)) if mm else _clean(line.split("\t")[0])
        if name and name.lower() not in {s.lower() for s in SKIP_SUB}:
            key = ALIASES.get(name, name)
            if key not in taxonomy[current]:
                taxonomy[current].append(key)
    return taxonomy


def build_subcategory_vocab(taxonomy: dict[str, list[str]]) -> dict[str, str]:
    """Create a flat {canonical_subcategory_key: description} vocab.

    Each entry becomes a prototype seed for the LVQ.  Keys are unique across the
    whole taxonomy so the model has one prototype per subcategory.
    """
    vocab: dict[str, str] = {}
    for cat, subs in taxonomy.items():
        for sub in subs:
            key = _canonical_key(cat, sub)
            vocab[key] = f"{cat} - {sub}"
    return vocab


def _canonical_key(cat: str, sub: str) -> str:
    return f"{cat} :: {sub}"


def main() -> None:
    cats = parse_categories()
    taxonomy = parse_taxonomy()
    vocab = build_subcategory_vocab(taxonomy)
    print(f"categories from {CAT_FILE.name}: {len(cats)}")
    print(f"categories with subcategories: {len(taxonomy)}")
    print(f"total subcategories: {len(vocab)}")
    print()
    for cat, subs in taxonomy.items():
        print(f"  {cat} ({len(subs)}): {subs[:5]}{'...' if len(subs) > 5 else ''}")
    # write a machine-readable copy
    import json
    (ROOT / "data").mkdir(exist_ok=True)
    with open(ROOT / "data" / "taxonomy.json", "w") as fh:
        json.dump({"categories": cats, "taxonomy": taxonomy,
                   "subcategory_vocab": vocab}, fh, indent=2)
    print("\nwrote data/taxonomy.json")


if __name__ == "__main__":
    main()