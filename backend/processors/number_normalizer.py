"""Spoken and written number normalization and financial figure extraction.

Normalizes spoken numbers ('fifteen thousand', '4.2 million', '15k', '$15,000') into
canonical numeric values for deterministic verification.
"""

import re
from typing import List, Optional, Tuple

NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

SCALES = {
    "hundred": 100,
    "thousand": 1_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
}


def words_to_number(text: str) -> Optional[float]:
    """Convert spoken number words (e.g. 'fifteen thousand', 'four point two million') to float."""
    tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", text.lower())
    if not tokens:
        return None

    current_val = 0.0
    total_val = 0.0
    matched_any = False

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        # Check decimal point spoken: e.g. "four point two million"
        if tok in NUMBER_WORDS or re.match(r"^\d+$", tok):
            val = float(NUMBER_WORDS[tok]) if tok in NUMBER_WORDS else float(tok)
            # Check if next token is 'point'
            if i + 2 < len(tokens) and tokens[i + 1] == "point" and (tokens[i + 2] in NUMBER_WORDS or re.match(r"^\d+$", tokens[i + 2])):
                dec_val = float(NUMBER_WORDS[tokens[i + 2]]) if tokens[i + 2] in NUMBER_WORDS else float(tokens[i + 2])
                val += dec_val / 10.0
                i += 2
            current_val += val
            matched_any = True
        elif tok in SCALES:
            scale = SCALES[tok]
            if current_val == 0.0:
                current_val = 1.0
            if scale == 100:
                current_val *= 100
            else:
                total_val += current_val * scale
                current_val = 0.0
            matched_any = True
        elif tok == "point":
            pass
        elif tok == "and":
            pass
        else:
            # Non-number token encountered
            break
        i += 1

    total_val += current_val
    return total_val if matched_any else None


def normalize_numeric_string(s: str) -> Optional[float]:
    """Parse a single numeric or currency token into a float value."""
    clean = re.sub(r"[$,€£%]", "", s).strip().lower()

    # Case: "15k" or "4.2m" or "2b"
    short_match = re.match(r"^(\d+(?:\.\d+)?)\s*([kmb])$", clean)
    if short_match:
        val = float(short_match.group(1))
        suffix = short_match.group(2)
        mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[suffix]
        return val * mult

    # Case: "4.2 million" or "15 thousand"
    scaled_match = re.match(r"^(\d+(?:\.\d+)?)\s*(million|billion|thousand|hundred)$", clean)
    if scaled_match:
        val = float(scaled_match.group(1))
        mult = SCALES[scaled_match.group(2)]
        return val * mult

    # Case: "$15,000" or "4200000"
    num_clean = clean.replace(",", "")
    try:
        return float(num_clean)
    except ValueError:
        pass

    # Try spoken number words: e.g. "fifteen thousand"
    return words_to_number(s)


def extract_numbers_from_text(text: str) -> List[Tuple[str, float]]:
    """Extract all numbers (digit strings, currency, spoken numbers) from text with their parsed float values."""
    candidates: List[Tuple[int, int, str, float]] = []  # (start, end, raw, val)

    # 1. Regex for formatted numbers & currencies: e.g. $15,000, 4.2 million, 15k, 50,000
    patterns = [
        r"(?:[\$€£])?\s*\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:million|billion|thousand|m|b|k)?\b",
        r"\b\d+(?:,\d{3})*(?:\.\d+)?\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            raw = m.group().strip()
            val = normalize_numeric_string(raw)
            if val is not None:
                candidates.append((m.start(), m.end(), raw, val))

    # 2. Spoken numbers: e.g. "fifteen thousand", "four point two million", "fifty thousand"
    spoken_pat = r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:\s+(?:point\s+\w+|hundred|thousand|million|billion|and|one|two|three|four|five|six|seven|eight|nine))+\b"
    for m in re.finditer(spoken_pat, text, re.IGNORECASE):
        raw = m.group().strip()
        val = words_to_number(raw)
        if val is not None:
            candidates.append((m.start(), m.end(), raw, val))

    # Resolve overlapping spans: longest span wins
    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))

    resolved: List[Tuple[int, int, str, float]] = []
    for cand in candidates:
        overlaps = False
        for acc in resolved:
            if max(cand[0], acc[0]) < min(cand[1], acc[1]):
                overlaps = True
                break
        if not overlaps:
            resolved.append(cand)

    # Return list of (raw, val)
    return [(c[2], c[3]) for c in resolved]


def numbers_compare_equal(val1: float, val2: float, tolerance: float = 0.001) -> bool:
    """Compare two numbers for equality with floating tolerance."""
    if val1 == val2:
        return True
    diff = abs(val1 - val2)
    denom = max(abs(val1), abs(val2), 1.0)
    return (diff / denom) <= tolerance
