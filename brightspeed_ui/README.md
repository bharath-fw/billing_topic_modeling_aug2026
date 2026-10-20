# Brightspeed Call Analytics UI

This is a local Streamlit UI for the supplied pipeline. It never edits pipeline source files. It invokes their existing functions in a separate Python process and redirects module path constants in memory to isolated run folders.

## Assumptions confirmed

- Tag Billing and Payments only, exactly as the existing pipeline does.
- The working project already has model/taxonomy assets.
- Monthly means one Excel file, custom means selected files, full means all `.xlsx` files directly in `datasets/`.
- Run on the pipeline machine using its existing Python environment. New uploads cannot overwrite existing files.

## 1. Put the UI next to your project

Unzip this package. Keep existing scripts in their current locations. A typical project layout is:

```
project/
  datasets/                         monthly .xlsx files
  code/
    pipeline/                       existing four Python scripts
    artifacts/
      taxonomy.json
      curated_centroids_10_each.csv
    output/
      coverage_leaf_order.csv
      coverage_leaf_protos.npy
  brightspeed_ui/
    app.py
    requirements-ui.txt
    .streamlit/config.toml
```

The UI accepts either normal filenames (`ingest.py`, `coverage.py`, `billing_narrow.py`, `autotag.py`) or the attached `(1).py` filenames. Normal filenames take precedence. Set the actual pipeline folder in the sidebar if yours differs.

If both prototype files exist, they are reused. Otherwise prototypes are built using the existing coverage functions and the two taxonomy artifacts. Use prototypes generated with the same embedding model as the pipeline.

## 2. Install UI dependencies in the working pipeline environment

```
conda activate YOUR_WORKING_PIPELINE_ENV
cd /absolute/path/to/project/brightspeed_ui
python -m pip install -r requirements-ui.txt
```

The existing environment must already provide NumPy, sentence-transformers, PyTorch, and the BAAI/bge-large-en-v1.5 model or access to download it. These model packages are intentionally not upgraded by the UI requirements.

## 3. Find a new available port and launch

```
python app.py --find-port
```

This scans localhost ports beginning at 8502. To select and launch with one command:

```
UI_PORT=$(python app.py --find-port)
python -m streamlit run app.py --server.port "$UI_PORT"
```

Open the localhost URL printed by Streamlit. The port is checked, not reserved; if another process takes it before startup, run the command again. Streamlit refuses an occupied port without interfering with the existing service.

For a remote server, use SSH forwarding from your own computer (replace 8502 with the chosen port):

```
ssh -L 8502:127.0.0.1:8502 YOUR_SERVER
```

Then open http://localhost:8502 on your computer. The default UI listens on localhost. Keep the terminal/server running while the UI is needed.

## 4. Use the UI

1. Set Project root and Pipeline scripts folder in the sidebar.
2. Choose CPU or CUDA as appropriate for the existing environment.
3. Use Upload datasets to save new Excel workbooks. Uploaded sheets must use the headers expected by your unchanged pipeline. The `Data` sheet is used when present, otherwise the first sheet. Duplicate filenames and unreadable workbooks are rejected.
4. In Analyze calls, choose Monthly, Custom selection, or Full dataset.
5. Optionally set a call limit for a quick test. Zero tags all billing calls. A limit still ingests all selected datasets, and tags only the first N billing rows in file order.
6. Click Analyze and add tags. Open Results and click Refresh results periodically.
7. Inspect call counts, category chart, first 500 matching calls, and logs. Filter by category or call month, then download filtered CSV or the full Parquet/CSV and monthly category summary.

Run outputs are retained in `project/ui_runs/<run-id>/`. Closing a browser tab does not cancel a worker. Run one analysis at a time to avoid GPU/RAM contention. Reopening the UI shows previous runs. A stopped worker is flagged in Results; rerun the analysis if needed.

The unchanged ingestion code materializes all selected rows in memory, and tagging embeds all selected billing calls together. Full-year runs need enough RAM/GPU capacity. Upload and CSV download preparation also use memory. The UI cannot remove these pipeline limits without changing the pipeline.

## Verification and limitations

- Python syntax, port discovery, module loading, empty-billing handling, and integration checks are recorded in VERIFICATION.md.
- The attached August workbook could not be read by OpenPyXL: `BadZipFile: File is not a zip file`. It has an Excel ZIP header but lacks a valid readable archive. Re-export or re-upload the workbook before testing it.
- Actual semantic tagging requires your existing model/prototypes and is not certified using substitute data.
- The wrapper intentionally preserves the supplied tag assignment algorithm, including its current rank-2/rank-3 behavior and fallback values. A UI cannot correct those algorithm choices while preserving the pipeline.
- Uploads support .xlsx only; dataset scope is based on selected files. Result month filters use Call_Month parsed by the pipeline. There is no pre-tagging arbitrary date-range filter.
