# Verification

Passed in the execution environment:
- Python compilation and available-port discovery.
- Port scanning skips an occupied localhost port.
- Streamlit starts on 8502; HTTP health endpoint returns `ok`.
- Streamlit AppTest renders the UI without exceptions.
- Monthly/custom/full controls render and switch without exceptions.
- Results chart, preview, filters, and download controls render with a representative tagged fixture.
- Real attached ingestion and billing functions process a synthetic workbook correctly.
- Zero billing calls produce a successful empty result instead of triggering model embedding.
- An unreadable workbook produces a visible Failed status and error log.
- SHA-256 checks confirm all four supplied pipeline files remain unchanged.

Not verified:
- Real model inference and semantic tag accuracy: the model/taxonomy assets were not attached.
- Full processing of the provided August workbook: OpenPyXL rejects its ZIP archive.
- Large monthly/full-year performance and actual CUDA execution on the user's machine.
- Interactive browser upload on the user's machine. Workbook validation and exclusive filename handling are implemented.

First deployment check: upload a valid workbook, run a limit of 100 billing calls, inspect the tags and logs, then set limit to 0 for full tagging. The limit applies after ingestion and Billing/Payments filtering.
