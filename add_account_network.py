#!/usr/bin/env python3
"""Enrich an existing tagged workbook, independently of the UI/pipeline.
Requires: openpyxl. Headers are in row 1. Sources: monthly *_All_Call_Data.xlsx,
Data sheet when present, otherwise first sheet. Match using the identifiers present in each output row.
Every nonempty output row must match its own monthly source before saving.
Close the target workbook and avoid UI writes while running this script.
"""
import argparse
from copy import copy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import os
import re
import shutil
import tempfile
from openpyxl import load_workbook

KEYS = ('BAN', 'record_id', 'Conversation ID')
EXTRAS = ('Account Type', 'Network Type')


def canonical_header(value):
    value = str(value or '').strip().casefold()
    return 'record_id' if value in ('record id', 'record_id') else value


def headers(ws):
    result = {}
    for i, cell in enumerate(next(ws.iter_rows(min_row=1, max_row=1), ()), 1):
        name = canonical_header(cell.value)
        if not name:
            continue
        if name in result:
            raise ValueError(f'{ws.title}: duplicate header {cell.value!r}')
        result[name] = i
    return result


def identifier(value):
    if value is None:
        return ''
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value))
        return format(number, 'f').rstrip('0').rstrip('.') if '.' in format(number, 'f') else format(number, 'f')
    text = str(value).strip()
    # Handle IDs previously stringified by pandas as "123.0".
    if re.fullmatch(r'[0-9]+\.0+', text):
        text = text.split('.')[0]
    return text


def key_from(values, cols):
    return tuple(identifier(values[cols[canonical_header(k)] - 1])
                 if canonical_header(k) in cols else '' for k in KEYS)


def clean(value):
    return value.strip() if isinstance(value, str) else value


MONTH_FILES = {
    'Jan_2026': ('Jan_All_Call_Data.xlsx',),
    'Feb_2026': ('Feb_All_Call_Data.xlsx',),
    'Mar_2026': ('Mar_All_Call_Data.xlsx',),
    'Apr_2026': ('Apr_All_Call_Data.xlsx',),
    'May_2026': ('May_All_Call_Data.xlsx',),
    'Jun_2026': ('Jun_All_Call_Data.xlsx',),
    'Jul_2026': ('Jul_All_Call_data.xlsx',),
    'Aug_2026': ('Aug_All_Call_data.xlsx', 'August_All_Call_data.xlsx'),
    'Sep_2026': ('Sep_All_Call_Data.xlsx',),
}


def monthly_lookup(root, sheet_name):
    if sheet_name not in MONTH_FILES:
        raise ValueError(f'{sheet_name}: no configured monthly dataset. Workbook unchanged.')
    available = [p for p in (root / 'datasets').glob('*.xlsx')
                 if p.name.casefold() in {n.casefold() for n in MONTH_FILES[sheet_name]}]
    if len(available) != 1:
        raise ValueError(f'{sheet_name}: expected exactly one of {MONTH_FILES[sheet_name]}, found {len(available)}. Workbook unchanged.')
    path = available[0]
    lookup = {}
    source = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = source['Data'] if 'Data' in source.sheetnames else source.worksheets[0]
        cols = headers(ws)
        missing = [k for k in EXTRAS if canonical_header(k) not in cols]
        if not any(canonical_header(k) in cols for k in KEYS):
            missing.append('at least one of BAN, record_id, Conversation ID')
        if missing:
            raise ValueError(f'{path.name}: missing columns {missing}')
        for row_number, values in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            key = key_from(values, cols)
            if not any(key):
                continue
            detail = tuple(clean(values[cols[canonical_header(k)] - 1]) for k in EXTRAS)
            if key in lookup and lookup[key] != detail:
                raise ValueError(f'{path.name}, row {row_number}: conflicting source values for a combined ID key. Workbook unchanged.')
            lookup[key] = detail
    finally:
        source.close()
    print(f'Mapping {sheet_name} using {path.name}', flush=True)
    # Index every available combination once, avoiding a source scan per row.
    indices = {mask: {} for mask in range(1, 8)}
    for full_key, detail in lookup.items():
        for mask, index in indices.items():
            positions = tuple(i for i in range(3) if mask & (1 << i))
            if not all(full_key[i] for i in positions):
                continue
            partial_key = tuple(full_key[i] for i in positions)
            if partial_key in index:
                # Different source keys sharing the remaining IDs are ambiguous.
                index[partial_key] = None
            else:
                index[partial_key] = detail
    return indices


def enrich(root):
    target = root / 'code' / 'output' / 'billing_tagged_full.xlsx'
    if not target.is_file():
        raise ValueError(f'Workbook not found: {target}')
    stamp = target.stat()
    book = load_workbook(target)
    matched_total = unmatched_total = 0
    try:
        month_order = {name: i for i, name in enumerate(MONTH_FILES)}
        for ws in sorted(book.worksheets, key=lambda ws: month_order.get(ws.title, 99)):
            if ws.title.strip().casefold() == 'overview':
                continue
            lookup = monthly_lookup(root, ws.title)
            cols = headers(ws)
            if not any(canonical_header(k) in cols for k in KEYS):
                raise ValueError(f'{ws.title}: none of the three identifier columns exists. Workbook unchanged.')
            matched = unmatched = 0
            unmatched_examples = []
            original_width = ws.max_column
            additions = {}
            for name in EXTRAS:
                pos = cols.get(canonical_header(name))
                if pos is None:
                    pos = ws.max_column + 1
                    cell = ws.cell(1, pos, name)
                    cell._style = copy(ws.cell(1, original_width)._style)
                    ws.column_dimensions[cell.column_letter].width = 22
                additions[name] = pos
            for row_number in range(2, ws.max_row + 1):
                values = tuple(ws.cell(row_number, col).value for col in range(1, original_width + 1))
                if all(v is None for v in values):
                    continue
                key = key_from(values, cols)
                mask = sum(1 << i for i, value in enumerate(key) if value)
                partial_key = tuple(value for value in key if value)
                index = lookup.get(mask, {})
                if partial_key in index and index[partial_key] is None:
                    used = ', '.join(KEYS[i] for i in range(3) if mask & (1 << i))
                    raise ValueError(f'{ws.title}, row {row_number}: ambiguous match using {used}. Workbook unchanged.')
                if not mask or partial_key not in index:
                    unmatched += 1
                    if len(unmatched_examples) < 10:
                        unmatched_examples.append(row_number)
                    continue
                for name, value in zip(EXTRAS, index[partial_key]):
                    cell = ws.cell(row_number, additions[name])
                    # Literal strings must not become Excel formulas.
                    cell.value = value
                    if isinstance(value, str):
                        cell.data_type = 's'
                matched += 1
            matched_total += matched
            unmatched_total += unmatched
            print(f'{ws.title}: matched={matched:,}, unmatched={unmatched:,}', flush=True)
            if unmatched_examples:
                print(f'  First unmatched Excel row numbers: {unmatched_examples}', flush=True)
        if unmatched_total:
            print(
                f'Skipping {unmatched_total:,} unmatched rows. '
                'Updating all matched rows.',
                flush=True,
            )
        if not matched_total:
            raise ValueError('No matching rows. Workbook unchanged.')
        fd, temp_name = tempfile.mkstemp(prefix='.enriched_', suffix='.xlsx', dir=target.parent)
        os.close(fd)
        temporary = Path(temp_name)
        try:
            book.save(temporary)
            current = target.stat()
            if (current.st_mtime_ns, current.st_size) != (stamp.st_mtime_ns, stamp.st_size):
                raise ValueError('Target changed during processing. Workbook not replaced. Run again after stopping other writes.')
            backup = target.with_name(f'{target.stem}.backup_{datetime.now():%Y%m%d_%H%M%S_%f}.xlsx')
            shutil.copy2(target, backup)
            os.replace(temporary, target)
            print(f'Backup: {backup}')
            print(f'Updated: {target}; matched={matched_total:,}, unmatched={unmatched_total:,}')
        finally:
            temporary.unlink(missing_ok=True)
    finally:
        book.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        enrich(args.project_root.expanduser().resolve())
    except Exception as exc:
        parser.exit(1, f'ERROR: {exc}\n')


if __name__ == '__main__':
    main()
