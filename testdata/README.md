# Small September test extracts

Four Excel workbooks sampled from `Sep_All_Call_Data.xlsx` for lightweight UI / pipeline checks (e.g. Google VM). Each file has a `Data` sheet with the full header plus **50 rows**.

| File | Rows (source order) |
|------|---------------------|
| `Sep_Test_Batch_01.xlsx` | 1–50 |
| `Sep_Test_Batch_02.xlsx` | 51–100 |
| `Sep_Test_Batch_03.xlsx` | 101–150 |
| `Sep_Test_Batch_04.xlsx` | 151–200 |

## Use with Docker

```bash
mkdir -p datasets
cp testdata/*.xlsx datasets/
docker compose up --build -d
```

The UI lists `*.xlsx` files directly under `datasets/`.
