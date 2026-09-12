#!/usr/bin/env python3
"""Offline citation-key cross-check, not a full BibTeX semantic validator."""
import argparse
import csv
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def bib_keys(text):
    """Scan top-level entries, respecting nested braces, quotes and comments."""
    keys, i = [], 0
    while i < len(text):
        if text[i] == '%':
            end = text.find('\n', i)
            i = len(text) if end == -1 else end + 1
            continue
        if text[i] != '@':
            i += 1
            continue
        match = re.match(r'@([A-Za-z]+)\s*([{(])', text[i:])
        if not match:
            raise ValueError(f'Malformed BibTeX entry near character {i}')
        kind, opening = match.groups()
        i += match.end()
        start = i
        closing = '}' if opening == '{' else ')'
        depth, quoted = 0, False
        while i < len(text):
            char = text[i]
            if char == '\\':
                i += 2
                continue
            if char == '%' and not quoted and depth == 0:
                end = text.find('\n', i)
                i = len(text) if end == -1 else end + 1
                continue
            if char == '"' and depth == 0:
                quoted = not quoted
            elif char == closing and depth == 0 and not quoted:
                break
            elif char == '{':
                depth += 1
            elif char == '}' and depth > 0:
                depth -= 1
            i += 1
        if i == len(text):
            raise ValueError('Unterminated BibTeX entry')
        body = text[start:i]
        if kind.lower() not in {'comment', 'string', 'preamble'}:
            key = re.match(r'\s*([A-Za-z0-9_:.+\-]+)\s*,', body)
            if not key:
                raise ValueError(f'Missing or invalid citation key in @{kind}')
            keys.append(key.group(1))
        i += 1
    return keys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, default=ROOT / 'literature.csv')
    parser.add_argument('--bib', type=Path, default=ROOT / 'references.bib')
    args = parser.parse_args()
    errors = []
    try:
        with args.csv.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle, strict=True)
            if 'citation_key' not in (reader.fieldnames or []):
                raise ValueError('CSV missing citation_key column')
            csv_keys = []
            for line, row in enumerate(reader, 2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f'CSV row {line}: column count mismatch')
                key = row['citation_key'].strip()
                if not key:
                    raise ValueError(f'CSV row {line}: empty citation key')
                csv_keys.append(key)
        keys = bib_keys(args.bib.read_text(encoding='utf-8-sig'))
        for name, values in [('CSV', csv_keys), ('BibTeX', keys)]:
            for key, count in sorted(Counter(values).items()):
                if count > 1:
                    errors.append(f'Duplicate {name} citation key: {key}')
        missing = sorted(set(csv_keys) - set(keys))
        orphans = sorted(set(keys) - set(csv_keys))
        errors.extend('Missing BibTeX entry: ' + key for key in missing)
        print('Orphaned BibTeX entries: ' + (', '.join(orphans) or 'none'))
        for error in errors:
            print('ERROR: ' + error)
        print(f"{'FAIL' if errors else 'PASS'}: bibliography: {len(csv_keys)} CSV keys, {len(keys)} BibTeX entries, {len(errors)} errors, {len(orphans)} orphans.")
        return bool(errors)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        print(f'ERROR: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
