import json
import re
from app.scripts.aws_bucket_access import AWSBucket

bucket = AWSBucket()

# object keys to be stored in s3
RAW_KEY = "data/raw/company_tickers.json"
CLEANED_KEY = "data/processed/cleaned_tickers.json"
ALIAS_KEY = "data/processed/alias_to_canonical.json"

sec_data = json.loads(bucket.read_text(RAW_KEY))

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

def normalize_company(name):
    text = re.sub(r"[^a-z0-9]", "", name.lower())
    for s in STOP_SUFFIXES:
        if text.endswith(s):
            text = text[: -len(s)]
    return text

def expand_abbreviations(name):
    expanded = name
    for abbrev, full in ABBREV_MAP.items():
        expanded = re.sub(abbrev, full, expanded, flags=re.IGNORECASE)
    return expanded

def normalize_ticker(ticker):
    return ticker.replace("-", ".").upper()

# Build canonical mapping
cleaned_mapping = {}
for entry in sec_data.values():
    ticker_raw = entry.get("ticker")
    title_raw = entry.get("title")
    if not ticker_raw or not title_raw:
        continue

    ticker = normalize_ticker(ticker_raw)
    name_norm = normalize_company(title_raw)

    if name_norm not in cleaned_mapping:
        cleaned_mapping[name_norm] = {
            "ticker": ticker,
            "title": title_raw,
        }

# Build alias mapping
alias_to_canonical = {}
for entry in sec_data.values():
    title_raw = entry.get("title")
    if not title_raw:
        continue

    name_norm = normalize_company(title_raw)
    expanded_norm = normalize_company(expand_abbreviations(title_raw))

    for alias in {name_norm, expanded_norm}:
        if alias != name_norm:
            alias_to_canonical[alias] = name_norm

# Upload results to S3 bucket
bucket.write_text(json.dumps(cleaned_mapping, indent=2), CLEANED_KEY)
bucket.write_text(json.dumps(alias_to_canonical, indent=2), ALIAS_KEY)

print(f"Uploaded {len(cleaned_mapping)} companies")
print(f"Uploaded {len(alias_to_canonical)} alias mappings")
