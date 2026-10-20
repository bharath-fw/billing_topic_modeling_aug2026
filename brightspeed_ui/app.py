"""Brightspeed UI adapter. Existing pipeline source files are never modified."""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import uuid
import re
import torch
from datetime import datetime
from io import BytesIO
import hashlib

HERE = Path(__file__).resolve().parent





FILTER_COLUMNS = [
    'BAN', 'Account Status', 'Account Type', 'State Name', 'Start Time Date',
    'Network Type', 'Record ID', 'Primary Call Reason', 'Sub Call Reason',
    'Customer Intent Tag', 'Problem Identified Tag', 'Root Cause', 'Reason',
    'Actions', 'Agent Email', 'Queue Category', 'Migration Flag',
    'Migration Type', 'Summary', 'Conversation ID', 'DNIs', 'QueueName',
]


def resolve_column(frame, column):
    aliases = {'Record ID': ('Record ID', 'record_id')}
    for name in aliases.get(column, (column,)):
        if name in frame.columns:
            return name
    raise ValueError(f'Dataset does not contain column {column!r}')


def filter_rows(frame, filters):
    """OR between values for one column; AND between enabled columns."""
    for column, values in filters.items():
        if not values:
            raise ValueError(f'Enter at least one value for {column}')
        name = resolve_column(frame, column)
        wanted = {str(value).strip().casefold() for value in values}
        frame = frame[
            frame[name].astype(str).str.strip().str.casefold().isin(wanted)
        ].copy()
    return frame


def filter_call_types(frame, billing=True, payment=True):
    # Retain the pipeline's existing scope when both defaults are enabled.
    if billing and payment:
        return frame
    if not billing and not payment:
        raise ValueError('Select Billing calls or Payment calls')
    name = resolve_column(frame, 'Primary Call Reason')
    reason = frame[name].astype(str)
    pattern = r'\bbilling\b' if billing else r'\bpayments?\b'
    return frame[reason.str.contains(pattern, case=False, regex=True, na=False)].copy()


def reported_progress(log_text, state):
    """Only display counts/percentages actually reported by the pipeline."""
    if state.get('state') == 'Complete':
        return 1.0, 'Processing complete: 100%'
    # tqdm writes carriage-return-delimited lines such as 25%|...| 25/100.
    matches = list(re.finditer(
        r'(\d{1,3})%[^\r\n]*?\b(\d[\d,]*)\s*/\s*(\d[\d,]*)',
        log_text,
    ))
    if matches:
        match = matches[-1]
        percent, processed, total = match.groups()
        return min(int(percent), 100) / 100, (
            f'Latest pipeline progress: {percent}% ({processed}/{total}); '
            'this may describe an embedding batch, not the entire run.'
        )
    return None, 'Processed-call percentage is unavailable until the pipeline reports progress.'


def script_path(folder, name):
    for filename in (f'{name}.py', f'{name}(1).py'):
        p = folder / filename
        if p.is_file():
            return p
    raise FileNotFoundError(f'Missing {name}.py in {folder}')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def status(run, state, **extra):
    temp = run / 'status.tmp'
    temp.write_text(json.dumps({'state': state, **extra}))
    temp.replace(run / 'status.json')


def worker(config_path):
    import pandas as pd
    import numpy as np
    cfg = json.loads(Path(config_path).read_text())
    run = Path(config_path).parent
    try:
        scripts = Path(cfg['scripts'])
        root = Path(cfg['root'])
        data, out = run / 'data', run / 'output'
        data.mkdir(exist_ok=True)
        out.mkdir(exist_ok=True)
        status(run, 'Reading selected datasets')
        ingest = load_module(script_path(scripts, 'ingest'), 'bs_ingest')
        frames = []
        for filename in cfg['files']:
            path = root / 'datasets' / filename
            if path.parent.resolve() != (root / 'datasets').resolve():
                raise ValueError('Invalid dataset path')
            df = ingest.read_month(path)
            needed = dict(cfg.get('filters', {}))
            if cfg.get('dnis') and 'DNIs' not in needed:
                needed['DNIs'] = cfg['dnis']
            if not (cfg.get('include_billing', True) and cfg.get('include_payment', True)):
                needed.setdefault('Primary Call Reason', [])
            missing_filters = []
            for column in needed:
                try:
                    resolve_column(df, column)
                except ValueError:
                    missing_filters.append(column)
            if missing_filters:
                # Restore only columns needed for active filters. Match by call ID,
                # never by row position, because ingestion may drop/reorder rows.
                with pd.ExcelFile(path) as workbook:
                    sheet = 'Data' if 'Data' in workbook.sheet_names else workbook.sheet_names[0]
                    original = pd.read_excel(workbook, sheet_name=sheet, dtype=str)
                source_id = resolve_column(original, 'Record ID')
                target_id = resolve_column(df, 'Record ID')
                names = [resolve_column(original, c) for c in missing_filters]
                details = original[[source_id, *names]].copy()
                details = details.rename(columns={source_id: target_id})
                details[target_id] = details[target_id].astype(str)
                df[target_id] = df[target_id].astype(str)
                details = details.drop_duplicates()
                df = df.merge(details, on=target_id, how='left', validate='many_to_one')
            df.insert(0, 'Source', path.stem)
            frames.append(df)
            print(f'{filename}: {len(df):,} calls', flush=True)
        raw = pd.concat(
            frames, ignore_index=True, sort=False
        ).astype(str)

        filters = cfg.get('filters', {})
        # Older saved worker configurations remain supported.
        if cfg.get('dnis') and 'DNIs' not in filters:
            filters = {**filters, 'DNIs': cfg['dnis']}
        raw = filter_rows(raw, filters)
        raw = filter_call_types(
            raw, cfg.get('include_billing', True),
            cfg.get('include_payment', True),
        )
        print(f'Input filters: {len(raw):,} matching calls', flush=True)
        if raw.empty:
            raise ValueError('No calls match the selected filters')

        total = len(raw)
        raw.to_parquet(data / 'raw_all_string.parquet', index=False)
        del raw, frames
        status(run, 'Filtering Billing/Payments', total_calls=total)
        billing = load_module(script_path(scripts, 'billing_narrow'), 'bs_billing')
        billing.build_billing(data / 'raw_all_string.parquet', data / 'billing_all.parquet', data / 'billing_narrow.parquet')
        count = len(pd.read_parquet(data / 'billing_narrow.parquet', columns=['record_id']))
        if not count:
            status(run, 'Complete', total_calls=total, billing_calls=0, tagged_calls=0)
            return
        # Explicit alias prevents collision with the unrelated coverage testing package.
        coverage = load_module(script_path(scripts, 'coverage'), 'coverage')
        coverage.DATA, coverage.OUT = data, out
        coverage.ARTIFACTS = root / 'code' / 'artifacts'
        tags = load_module(script_path(scripts, 'autotag'), 'bs_autotag')
        tags.DATA, tags.OUT = data, out
        assets = root / 'code' / 'output'
        names = ('coverage_leaf_order.csv', 'coverage_leaf_protos.npy')
        if all((assets / name).is_file() for name in names):
            for name in names:
                shutil.copy2(assets / name, out / name)
        else:
            status(run, 'Building taxonomy prototypes', total_calls=total, billing_calls=count)
            leaf = coverage.build_leaf_prototypes(coverage.build_leaf_prototype_texts(), device=cfg['device'])
            np.save(out / names[1], np.stack(leaf['prototype'].to_numpy()))
            leaf.drop(columns='prototype').to_csv(out / names[0], index=False)
        leaf = pd.read_csv(out / names[0])
        protos = np.load(out / names[1], allow_pickle=False)
        if protos.ndim != 2 or len(leaf) != len(protos) or len(leaf) < 3:
            raise ValueError('Invalid or mismatched taxonomy prototypes')
        status(run, 'Embedding and tagging calls', total_calls=total, billing_calls=count)
        result = tags.run(limit=cfg['limit'] or None, device=cfg['device'])
        tagged = pd.read_parquet(result)

        # Read original call details retained during ingestion.
        source = pd.read_parquet(data / 'raw_all_string.parquet')

        if 'record_id' not in source.columns and 'Record ID' in source.columns:
            source = source.rename(columns={'Record ID': 'record_id'})

        extra_columns = [
            'Account Type',
            'Network Type',
            'Queue Category',
            'DNIs',
        ]
        missing = [
            column
            for column in ['record_id', *extra_columns]
            if column not in source.columns
        ]
        if missing:
            raise ValueError(
                f'Columns missing from ingested data: {missing}'
            )

        # Add only columns absent from the tagging output.
        columns_to_add = [
            column for column in extra_columns
            if column not in tagged.columns
        ]

        if columns_to_add:
            details = source[
                ['record_id', *columns_to_add]
            ].drop_duplicates()

            tagged = tagged.merge(
                details,
                on='record_id',
                how='left',
                validate='many_to_one',
            )

        # Update the run's Parquet so the UI downloads include these columns.
        tagged.to_parquet(result, index=False)
        tagged.to_csv(out / 'billing_tagged_full.csv', index=False)
        # Save only months that do not already have a worksheet.
        excel_folder = root / 'code' / 'output'
        excel_folder.mkdir(parents=True, exist_ok=True)
        excel_path = excel_folder / 'billing_tagged_full.xlsx'

        required = ['Call_Month', 'ai_category_1']
        missing = [column for column in required if column not in tagged.columns]
        if missing:
            raise ValueError(f'Missing Excel output columns: {missing}')

        # Expected Call_Month format: YYYY-MM, as in your screenshot.
        month_dates = pd.to_datetime(
            tagged['Call_Month'].astype(str).str.strip(),
            format='%Y-%m',
            errors='coerce',
        )
        if month_dates.isna().any():
            raise ValueError('Call_Month must contain valid YYYY-MM values')

        monthly_data = tagged.copy()
        monthly_data['Call_Month'] = month_dates.dt.strftime('%Y-%m')

        overview_columns = [
            'Call_Month', 'ai_category_1', 'calls', 'total_calls'
        ]
        overview = pd.DataFrame(columns=overview_columns)
        existing_sheets = set()

        if excel_path.exists():
            with pd.ExcelFile(excel_path, engine='openpyxl') as workbook:
                existing_sheets = set(workbook.sheet_names)
                if 'Overview' in existing_sheets:
                    overview = pd.read_excel(
                        workbook,
                        sheet_name='Overview',
                        dtype={'Call_Month': str},
                    )
                    if not set(overview_columns).issubset(overview.columns):
                        raise ValueError(
                            'Overview does not have the expected columns'
                        )
                    overview = overview[overview_columns]

        month_names = [
            'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
        ]

        new_sheets = {}
        new_summaries = []
        new_months = []

        for month, rows in monthly_data.groupby('Call_Month', sort=True):
            year, month_number = month.split('-')
            sheet_name = f'{month_names[int(month_number) - 1]}_{year}'

            if sheet_name in existing_sheets:
                print(
                    f'Skipped {month}: {sheet_name} already exists',
                    flush=True,
                )
                continue

            # Keep every column returned by the tagging pipeline.
            new_sheets[sheet_name] = rows

            summary = (
                rows.groupby('ai_category_1', dropna=False)
                .size()
                .reset_index(name='calls')
            )
            summary.insert(0, 'Call_Month', month)
            summary['total_calls'] = len(rows)

            new_summaries.append(summary[overview_columns])
            new_months.append(month)

        if new_sheets:
            # Preserve other months; refresh Overview rows for added months.
            overview = overview[
                ~overview['Call_Month'].isin(new_months)
            ]
            overview = pd.concat(
                [overview, *new_summaries],
                ignore_index=True,
            )
            overview = overview.sort_values(
                ['Call_Month', 'calls'],
                ascending=[True, False],
                kind='stable',
            )

            writer_options = {
                'engine': 'openpyxl',
                'mode': 'a' if excel_path.exists() else 'w',
            }
            if writer_options['mode'] == 'a':
                writer_options['if_sheet_exists'] = 'replace'

            with pd.ExcelWriter(excel_path, **writer_options) as writer:
                for sheet_name, rows in new_sheets.items():
                    rows.to_excel(
                        writer, sheet_name=sheet_name, index=False
                    )
                overview.to_excel(
                    writer, sheet_name='Overview', index=False
                )

            print(
                f'Added sheets: {", ".join(new_sheets)}; '
                f'updated Overview in {excel_path}',
                flush=True,
            )
        else:
            print('No new month sheets to add', flush=True)        
        status(run, 'Complete', total_calls=total, billing_calls=count, tagged_calls=len(tagged))
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        status(run, 'Failed', error=str(exc))
        return 1
    return 0
def show_pivot_verification(st, pd, run, cfg, output):
    st.subheader('Pivot table verification')

    input_path = run / 'data' / 'raw_all_string.parquet'

    if not input_path.exists():
        st.warning('Input data for this analysis is unavailable.')
        return

    input_data = pd.read_parquet(input_path)
    output_data = output.copy()

    filter_columns = [
        'DNIs',
        'Account Type',
        'Queue Category',
        'Network Type',
    ]
    required = [*filter_columns, 'Primary Call Reason']

    # Recover pivot columns missing from output using the original call ID.
    missing_output = [
        column for column in required
        if column not in output_data.columns
    ]

    if missing_output:
        source = input_data.copy()

        if 'record_id' not in source.columns and 'Record ID' in source.columns:
            source = source.rename(columns={'Record ID': 'record_id'})

        if (
            'record_id' not in output_data.columns
            and 'Record ID' in output_data.columns
        ):
            output_data = output_data.rename(
                columns={'Record ID': 'record_id'}
            )

        can_restore = (
            'record_id' in source.columns
            and 'record_id' in output_data.columns
            and all(column in source.columns for column in missing_output)
        )

        if can_restore:
            details = source[
                ['record_id', *missing_output]
            ].drop_duplicates()

            try:
                output_data = output_data.merge(
                    details,
                    on='record_id',
                    how='left',
                    validate='many_to_one',
                )
            except pd.errors.MergeError:
                st.error(
                    'Cannot verify pivots: some record IDs have '
                    'conflicting source details.'
                )
                return

    for label, frame in [
        ('Input', input_data),
        ('Output', output_data),
    ]:
        missing = [
            column for column in required
            if column not in frame.columns
        ]
        if missing:
            st.warning(
                f'{label} data is missing pivot columns: '
                + ', '.join(missing)
            )
            return

    # Normalize filter values without changing saved files.
    for frame in [input_data, output_data]:
        for column in filter_columns:
            frame[column] = frame[column].astype('string').str.strip()

    analysis_dnis = cfg.get('filters', {}).get(
        'DNIs', cfg.get('dnis', [])
    )

    defaults = {
        'DNIs': analysis_dnis,
        'Account Type': ['Residential'],
        'Queue Category': ['Care', 'Saves'],
        'Network Type': ['Fiber'],
    }

    selections = {}
    controls = st.columns(4)

    for control, column in zip(controls, filter_columns):
        available = pd.concat(
            [input_data[column], output_data[column]],
            ignore_index=True,
        ).dropna()

        available = available[available.ne('')]

        # Include requested defaults even when they have no matching rows.
        options = sorted(
            set(available.tolist())
            | {str(value).strip() for value in defaults[column]},
            key=str.casefold,
        )

        # Match default spelling to the dataset, ignoring case.
        lookup = {value.casefold(): value for value in options}
        selected_defaults = list(dict.fromkeys(
            lookup[str(value).strip().casefold()]
            for value in defaults[column]
        ))

        selections[column] = control.multiselect(
            column,
            options=options,
            default=selected_defaults,
            placeholder='All',
            key=f'pivot_{run.name}_{column}',
        )

    st.caption(
        'An empty filter means All. These filters affect only '
        'the verification tables, not analysis or downloads.'
    )

    def build_pivot(frame):
        filtered = frame

        for column, values in selections.items():
            if values:
                filtered = filtered[
                    filtered[column].str.casefold().isin(
                        [value.casefold() for value in values]
                    )
                ]

        # Same layout as Excel:
        # Rows = Primary Call Reason
        # Values = Count of Primary Call Reason
        pivot = (
            filtered.groupby('Primary Call Reason')[
                'Primary Call Reason'
            ]
            .count()
            .rename('Count of Primary Call Reason')
            .reset_index()
        )

        total = int(pivot['Count of Primary Call Reason'].sum())

        pivot.loc[len(pivot)] = ['Grand Total', total]

        return pivot, total

    input_pivot, input_total = build_pivot(input_data)
    output_pivot, output_total = build_pivot(output_data)

    left, right = st.columns(2)

    with left:
        st.write('**Input — data used for analysis**')
        st.dataframe(
            input_pivot,
            hide_index=True,
            use_container_width=True,
        )

    with right:
        st.write('**Output — tagged results**')
        st.dataframe(
            output_pivot,
            hide_index=True,
            use_container_width=True,
        )

    st.write(
        
        
    )

def render():
    import pandas as pd
    import streamlit as st
    st.set_page_config(page_title='Brightspeed Call Analytics', page_icon='📞', layout='wide', menu_items={'Get Help': None, 'Report a bug': None, 'About': None})
    # Hide the Streamlit menu containing Print. Browser Ctrl+P is unaffected.
    st.markdown('<style>#MainMenu {visibility: hidden;}</style>', unsafe_allow_html=True)
    st.title('Brightspeed Call Analytics')
    root = HERE
    scripts = root / 'code' / 'pipeline'
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    datasets = root / 'datasets'
    
    tabs = st.tabs(['Analyze calls', 'Filters', 'Results'])

    with tabs[1]:
        
        include_billing = st.checkbox('Billing calls', value=True)
        include_payment = st.checkbox('Payment calls', value=True)
        st.caption('Column values match exactly, ignoring case and surrounding spaces. Enter one value per line or separate values with commas.')
        filters = {}
        empty_filters = []
        for column in FILTER_COLUMNS:
            if st.checkbox(column, key=f'enable_filter_{column}'):
                text = st.text_area(
                    f'Values for {column}',
                    key=f'filter_values_{column}',
                )
                values = list(dict.fromkeys(
                    v.strip()
                    for v in re.split(r'[,\n]', text)
                    if v.strip()
                ))
                filters[column] = values
                if not values:
                    empty_filters.append(column)
    
    with tabs[0]:
        uploaded = st.file_uploader(
            'Drag and drop new monthly Excel files here',
            type=['xlsx'],
            accept_multiple_files=True,
            key='monthly_uploads',
        )
        

        saved_uploads = st.session_state.setdefault('saved_uploads', set())

        if uploaded:
            from openpyxl import load_workbook

            for item in uploaded:
                name = Path(item.name).name
                dest = datasets / name
                upload_id = (
                    str(dest),
                    hashlib.sha256(item.getbuffer()).hexdigest(),
                )

                # Avoid saving the same upload again on UI reruns.
                if upload_id in saved_uploads:
                    st.success(f'Saved: {dest}')
                    continue

                tmp = datasets / f'.{uuid.uuid4().hex}.xlsx'

                try:
                    datasets.mkdir(parents=True, exist_ok=True)

                    if dest.exists():
                        raise ValueError(
                            'This filename already exists. Rename your new file.'
                        )

                    tmp.write_bytes(item.getbuffer())

                    wb = load_workbook(
                        tmp, read_only=True, data_only=True
                    )
                    try:
                        ws = (
                            wb['Data']
                            if 'Data' in wb.sheetnames
                            else wb[wb.sheetnames[0]]
                        )
                        header = next(ws.iter_rows(values_only=True), ())
                    finally:
                        wb.close()

                    required = [
                        'Primary Call Reason', 'BAN',
                        'Customer Intent Tag', 'Problem Identified Tag',
                        'Reason', 'Summary', 'Queue Category',
                        'Conversation ID', 'QueueName',
                    ]
                    missing = [c for c in required if c not in header]

                    if not any(
                        c in header for c in ['Record ID', 'record_id']
                    ):
                        missing.append('Record ID')

                    if missing:
                        raise ValueError(
                            f'Missing required columns: {missing}'
                        )

                    # Save without replacing any existing dataset.
                    with dest.open('xb') as target, tmp.open('rb') as source:
                        shutil.copyfileobj(source, target)

                    saved_uploads.add(upload_id)
                    st.success(f'Saved: {dest}')

                except Exception as exc:
                    st.error(f'{name}: {exc}')
                finally:
                    tmp.unlink(missing_ok=True)
    files = sorted(p.name for p in datasets.glob('*.xlsx') if not p.name.startswith(('~$', '.')))
    runs = root / 'ui_runs'
    with tabs[0]:
        st.info('Choose call types and column filters in the Filters tab before starting analysis.')
        mode = st.radio('Dataset scope', ['Monthly', 'Custom selection', 'Full dataset'], horizontal=True)
        if mode == 'Monthly':
            chosen = st.selectbox('Monthly file', files) if files else None
            selected = [chosen] if chosen else []
        elif mode == 'Custom selection':
            selected = st.multiselect('Dataset files', files)
        else:
            selected = files
        st.write(f'{len(selected)} of {len(files)} files selected')
        

                      
        limit = 0
        
        
        issues = []
        if not include_billing and not include_payment:
            issues.append('Select Billing calls or Payment calls in Filters.')
        if empty_filters:
            issues.append('Enter filter values or uncheck: ' + ', '.join(empty_filters))
        for name in ['ingest', 'billing_narrow', 'coverage', 'autotag']:
            try:
                script_path(scripts, name)
            except FileNotFoundError as exc:
                issues.append(str(exc))
        assets = root / 'code' / 'output'
        if not all((assets / n).exists() for n in ['coverage_leaf_order.csv', 'coverage_leaf_protos.npy']):
            for n in ['taxonomy.json', 'curated_centroids_10_each.csv']:
                if not (root / 'code' / 'artifacts' / n).exists():
                    issues.append(f'Missing taxonomy asset: {n}')
        for issue in issues:
            st.error(issue)
        if not files:
            st.warning(f'No Excel datasets found in {datasets}. Use Upload datasets.')
        if st.button('Analyze and add tags', type='primary', disabled=bool(issues) or not selected):
            run = runs / (datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
            run.mkdir(parents=True)
            cfg = {
                'root': str(root),
                'scripts': str(scripts),
                'files': selected,
                'limit': int(limit),
                'device': device,
                'filters': filters,
                'include_billing': include_billing,
                'include_payment': include_payment,
            }
            config = run / 'config.json'
            config.write_text(json.dumps(cfg, indent=2))
            status(run, 'Queued')
            try:
                with (run / 'pipeline.log').open('w') as log:
                    proc = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '--worker', str(config)], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                (run / 'pid').write_text(str(proc.pid))
                st.success(f'Started run {run.name}. Open Results to monitor it.')
            except Exception as exc:
                status(run, 'Failed', error=str(exc))
                st.error(str(exc))
    with tabs[2]:
        st.button('Refresh results')
        history = sorted((p for p in runs.glob('*') if (p / 'config.json').is_file()), reverse=True)
        if history:
            run = st.selectbox('Analysis run', history, format_func=lambda p: p.name)
            cfg = json.loads((run / 'config.json').read_text())
            state = json.loads((run / 'status.json').read_text())
            st.write('Datasets:', ', '.join(cfg['files']))
            st.write('Status:', state['state'])
            if state['state'] not in ('Complete', 'Failed') and (run / 'pid').exists():
                try:
                    os.kill(int((run / 'pid').read_text()), 0)
                except ProcessLookupError:
                    st.error('Worker stopped before completion. Inspect the log and start a new run.')
            if 'error' in state:
                st.error(state['error'])
            cols = st.columns(3)
            for col, key, label in zip(cols, ['total_calls', 'billing_calls', 'tagged_calls'], ['Selected calls', 'Billing/Payments calls', 'Tagged calls']):
                col.metric(label, state.get(key, '—'))
            if (run / 'pipeline.log').exists():
                with st.expander('Processing log'):
                    with (run / 'pipeline.log').open('rb') as log:
                        log.seek(max(0, (run / 'pipeline.log').stat().st_size - 20000))
                        log_text = log.read().decode(errors='replace')
                    progress, progress_text = reported_progress(log_text, state)
                    if progress is None:
                        st.info(progress_text)
                    else:
                        st.progress(progress, text=progress_text)
                    st.code(log_text)
            result = run / 'output' / 'billing_tagged_full.parquet'
            if state['state'] == 'Complete' and result.exists():
                @st.cache_data(show_spinner=False)
                def read_result(path, stamp):
                    return pd.read_parquet(path)
                df = read_result(str(result), result.stat().st_mtime_ns)
                
                view = df
                
                
                
                
                def excel_bytes(frame):
                    buffer = BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        frame.to_excel(
                            writer, sheet_name='Tagged calls', index=False
                        )
                    return buffer.getvalue()

                excel_mime = (
                    'application/vnd.openxmlformats-officedocument.'
                    'spreadsheetml.sheet'
                )

                try:
                    st.download_button(
                        label='Download full results (.xlsx)',
                        data=excel_bytes(df),
                        file_name='billing_tagged_full.xlsx',
                        mime=excel_mime,
                    )
                except Exception as exc:
                    st.error(f'Could not create Excel download: {exc}') 
                show_pivot_verification(st, pd, run, cfg, df)                                                   
        else:
            st.info('Run an analysis to see results here.')


if __name__ == '__main__':
    if '--worker' in sys.argv:
        sys.exit(worker(sys.argv[sys.argv.index('--worker') + 1]))
    else:
        render()
