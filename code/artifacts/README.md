# Brightspeed Billing Taxonomy Bundle V4

Production-oriented taxonomy with macro categories, comprehensive subcategories, canonical tags, evidence-density visuals, and a low-entropy Excel inference workflow.

Key inference rule: one primary tag is mandatory. Rank 2 and rank 3 are used only for truly separate additional billing asks.

Included artifacts

- billing_taxonomy_workbook.xlsx: taxonomy review workbook with the current prompt
- brightspeed_excel_inference_output.xlsx: worked inference output, canonical vocabulary, prompt, and non-technical usage notes
- billing_inference_prompt.txt: compact Excel inference prompt
- canonical_vocabulary.csv: allowed tag vocabulary and exact readable labels
- taxonomy.json, taxonomy_keywords.csv, curated_centroids_10_each.csv
- tree_hierarchy.md
- treemap_subcategory_evidence_density.png
- som_evidence_density.png and som_cells_evidence_density.csv
- source_reason_to_canonical_mapping.csv and canonical_leaf_evidence_counts.csv
- 02_brightspeed_billing_taxonomy_explained.ipynb

The uploaded billing_segment_full.parquet could not be decoded in this runtime because pyarrow and fastparquet are unavailable and package installation has no network access. The inference-output workbook therefore uses auditable aggregate source-reason mappings and clearly marked constructed multi-topic examples rather than claiming row-level predictions.
