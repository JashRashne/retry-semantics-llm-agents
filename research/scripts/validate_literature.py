#!/usr/bin/env python3
"""Offline CSV structure and metadata checks; never infer scientific findings."""
import argparse
import csv
import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_COLUMNS = '''citation_key title authors year venue publication_status doi
arxiv_id url literature_bucket systems_concept failure_model state_mutating
retry_discussed retry_trigger replay_or_regenerate external_state_verified
idempotency_mechanism compensation_mechanism transactional_mechanism
real_or_simulated_system external_system main_result_relevant_to_project
limitation_relevant_to_project reading_status notes_file metadata_sources
metadata_checked_on metadata_notes missing_metadata'''.split()
ENUMS = {
    'reading_status': {'TODO', 'SKIMMED', 'FULL_READ', 'VERIFIED'},
    'publication_status': {'STANDARD', 'CONFERENCE_PAPER', 'JOURNAL_ARTICLE',
                           'PREPRINT', 'TECHNICAL_REPORT', 'DOCUMENTATION', 'OTHER', 'UNCLEAR'},
    'literature_bucket': {'SYSTEMS_FOUNDATIONS', 'AGENT_METHODS', 'BENCHMARKS',
                          'AGENT_RELIABILITY', 'API_DOCUMENTATION',
                          'MODEL_DOCUMENTATION', 'OTHER', 'UNCLEAR'},
    'replay_or_regenerate': {'REPLAY', 'REGENERATE', 'BOTH', 'OTHER', 'UNCLEAR', 'NOT_APPLICABLE'},
    'real_or_simulated_system': {'REAL', 'SIMULATED', 'BOTH', 'CONCEPTUAL', 'UNCLEAR'},
}
for field in ('state_mutating', 'retry_discussed', 'external_state_verified'):
    ENUMS[field] = {'YES', 'NO', 'PARTIAL', 'UNCLEAR', 'NOT_APPLICABLE'}
OPTIONAL_ENUMS = set(ENUMS) - {'reading_status', 'publication_status'}
BIB_REQUIRED = {'citation_key', 'title', 'authors', 'year', 'venue', 'publication_status', 'url'}
# Only these bibliographic gaps may be explicitly acknowledged, with a reason.
WAIVABLE = {'authors', 'year', 'venue'}


def normalize_doi(value):
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value.strip(), flags=re.I).lower()


def normalize_arxiv(value):
    value = re.sub(r'^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/|^arxiv:\s*', '', value.strip(), flags=re.I)
    value = re.sub(r'\.pdf$', '', value, flags=re.I)
    return re.sub(r'v\d+$', '', value, flags=re.I).lower()


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, strict=True)
        return reader.fieldnames or [], list(reader)


def validate(path):
    errors, warnings = [], []
    try:
        headers, rows = read_csv(path)
    except (OSError, UnicodeError, csv.Error) as exc:
        return [str(exc)], [], 0
    missing = sorted(set(REQUIRED_COLUMNS) - set(headers))
    if missing:
        errors.append('Missing required columns: ' + ', '.join(missing))
    if len(headers) != len(set(headers)):
        errors.append('Duplicate column names')
    if not rows:
        errors.append('No literature records')
    seen = {field: {} for field in ('citation_key', 'doi', 'arxiv_id')}
    for line, original in enumerate(rows, 2):
        if None in original or any(value is None for value in original.values()):
            errors.append(f'Row {line}: column count does not match header')
            continue
        row = {key: value.strip() for key, value in original.items()}
        label = f"Row {line} ({row.get('citation_key') or 'no key'})"
        try:
            gaps = json.loads(row.get('missing_metadata') or '{}')
            if not isinstance(gaps, dict):
                raise ValueError('must be a JSON object')
        except (ValueError, TypeError) as exc:
            errors.append(f'{label}: invalid missing_metadata: {exc}')
            gaps = {}
        for field, reason in gaps.items():
            if field not in WAIVABLE or not isinstance(reason, str) or not reason.strip() or reason.strip() == 'TODO':
                errors.append(f'{label}: invalid metadata gap for {field}')
            elif row.get(field) not in ('', 'TODO', None):
                errors.append(f'{label}: stale metadata gap for populated field {field}')
            else:
                warnings.append(f'{label}: documented missing {field}: {reason}')
        for field in BIB_REQUIRED | {'metadata_sources', 'metadata_checked_on'}:
            if row.get(field) in ('', 'TODO', None) and not (field in WAIVABLE and field in gaps):
                errors.append(f'{label}: required metadata {field} is missing')
        for field, allowed in ENUMS.items():
            value = row.get(field, '')
            if field in OPTIONAL_ENUMS and value in ('', 'TODO'):
                continue
            if value not in allowed:
                errors.append(f'{label}: invalid {field}={value!r}')
        for field, normalize in (('citation_key', str.strip), ('doi', normalize_doi), ('arxiv_id', normalize_arxiv)):
            value = row.get(field, '')
            if value in ('', 'TODO'):
                continue
            canonical = normalize(value)
            if canonical in seen[field]:
                errors.append(f'{label}: duplicate {field} {canonical!r} (also row {seen[field][canonical]})')
            seen[field][canonical] = line
        if row.get('year') not in ('', 'TODO', None) and not re.fullmatch(r'\d{4}', row['year']):
            errors.append(f'{label}: year must be four digits')
        if row.get('citation_key') and not re.fullmatch(r'[A-Za-z0-9_:.+-]+', row['citation_key']):
            errors.append(f'{label}: invalid citation key syntax')
        if row.get('doi') and not re.fullmatch(r'10\.\d{4,9}/\S+', normalize_doi(row['doi'])):
            errors.append(f'{label}: invalid DOI syntax')
        if row.get('arxiv_id') and not re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z.-]+/\d{7})', normalize_arxiv(row['arxiv_id'])):
            errors.append(f'{label}: invalid arXiv ID syntax')
        if row.get('venue') == 'arXiv' and not row.get('arxiv_id'):
            errors.append(f'{label}: arXiv venue requires arxiv_id')
        for field in ('url', 'metadata_sources'):
            for url in row.get(field, '').split(' | '):
                if url and not re.fullmatch(r'https?://[^\s/]+(?:/\S*)?', url):
                    errors.append(f'{label}: invalid URL in {field}')
        try:
            datetime.date.fromisoformat(row.get('metadata_checked_on', ''))
        except ValueError:
            errors.append(f'{label}: metadata_checked_on must be YYYY-MM-DD')
        if row.get('notes_file'):
            target = (path.parent / row['notes_file']).resolve()
            if not target.is_relative_to(path.parent.resolve()):
                errors.append(f'{label}: notes_file must stay within the research directory')
            elif not target.is_file():
                errors.append(f"{label}: notes_file does not exist: {row['notes_file']}")
    return errors, warnings, len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', nargs='?', type=Path, default=ROOT / 'literature.csv')
    args = parser.parse_args()
    errors, warnings, count = validate(args.csv.resolve())
    for message in warnings:
        print('WARNING: ' + message)
    for message in errors:
        print('ERROR: ' + message)
    print(f"{'FAIL' if errors else 'PASS'}: literature.csv: {count} records, {len(errors)} errors, {len(warnings)} warnings.")
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
