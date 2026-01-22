import json
import re
import os

current_dir = os.path.dirname(__file__)
json_path = os.path.join(current_dir, '..', 'data', 'company_tickers.json')
output_path = os.path.join(current_dir, '..', 'data', 'cleaned_tickers.json')
alias_output_path = os.path.join(current_dir, '..', 'data', 'alias_to_canonical.json')

with open(json_path, "r") as f:
    sec_data = json.load(f)

STOP_SUFFIXES = [
    "inc", "corp", "corporation", "ltd", "llc", "co", "&co", ",inc", ",inc.", "/new", "/de/", "/mn"
]

ABBREV_MAP = {
    r'\bco\b': 'company',
    r'\bcorp\b': 'corporation',
    r'\binc\b': 'incorporated',
    r'\bltd\b': 'limited',
    r'\bintl\b': 'international',
    r"\bint'l\b": 'international',
    r'\bint\b': 'international',
    r'\bgrp\b': 'group',
    r'\btech\b': 'technologies',
    r'\bmfg\b': 'manufacturing',
    r'\bsys\b': 'systems',
    r'\bassoc\b': 'associates',
    r'\bbros\b': 'brothers',
    r'\bmgmt\b': 'management'
}

# Normalize company name by lowercasing, removing punctuation and stripping common suffixes
def normalize_company(name):
    text = re.sub(r"[^a-z0-9]", "", name.lower())
    for s in STOP_SUFFIXES:
        if text.endswith(s):
            text = text[: -len(s)]
    return text

# expand abbreviations to build alias mapping
# e.g. Apple bgrp becomes Apple group
def expand_abbreviations(name):
    expanded = name
    for abbrev, full in ABBREV_MAP.items():
        expanded = re.sub(abbrev, full, expanded, flags=re.IGNORECASE)
    return expanded

# normalize tickers by uppercasing and replacing dash with dot for BRK-B style tickers 
def normalize_ticker(ticker):
    return ticker.replace("-", ".").upper()

# Step 1: Build canonical mapping
cleaned_mapping = {}
for entry in sec_data.values():
    ticker_raw = entry.get("ticker")
    title_raw = entry.get("title")
    if not ticker_raw or not title_raw:
        continue  

    ticker = normalize_ticker(ticker_raw)
    name_norm = normalize_company(title_raw)

    if name_norm not in cleaned_mapping:
        cleaned_mapping[name_norm] = {"ticker": ticker, "title": title_raw}

# Step 2: Build alias-to-canonical mapping
alias_to_canonical = {}
for entry in sec_data.values():
    title_raw = entry.get("title")
    if not title_raw:
        continue

    name_norm = normalize_company(title_raw)
    expanded_title = expand_abbreviations(title_raw)
    expanded_norm = normalize_company(expanded_title)

    # Map both the original and expanded forms to the canonical name_norm
    for alias in {normalize_company(title_raw), expanded_norm}:
        if alias != name_norm:
            alias_to_canonical[alias] = name_norm

# Save cleaned mapping
with open(output_path, "w") as f:
    json.dump(cleaned_mapping, f, indent=2)

# Save alias mapping
with open(alias_output_path, "w") as f:
    json.dump(alias_to_canonical, f, indent=2)

print(f"Cleaned {len(cleaned_mapping)} companies saved to cleaned_tickers.json")
print(f"Alias mapping saved to alias_to_canonical.json")
