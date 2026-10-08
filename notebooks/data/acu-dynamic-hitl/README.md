# Data and helpers for `acu-dynamic-hitl`

| File | What it is |
| --- | --- |
| `cord_demo.parquet` | Measured Azure Content Understanding output for 1,000 CORD v2 receipts: 13,853 extracted field values, each with its confidence score and an `is_correct` verdict against ground truth. |
| `metadata.json` | Provenance for the parquet: source dataset, pinned revision, analyzer, model, API version. |
| `cord_receipt_v1.json` | The Content Understanding analyzer that produced the parquet, with confidence scores turned on. Use it as a template. |
| `calibration.py` | The calibration API the notebook calls. |
| `acu_calibrator.py` | The engine behind it: grouped cross-validation, AUC intervals, Wilson bounds, cutoff sweeps. |
| `matching.py` | Builds `is_correct` by comparing extractions to ground truth after per-field normalization, and pairs list items, such as receipt line items, with ground truth by content. |
| `hitl_dial.py` | Renders the mistake catch-rate dial and the accessible charts shown in the notebook. |
| `calibration_table_80pct.csv` | The calibration table written by step 4 of the notebook. Each run regenerates it. |
| `requirements.txt` | Python dependencies for the recipe. |

`calibration.py`, `acu_calibrator.py`, and `matching.py` are copied unchanged from the `dynamic_hitl/calibration_lab` folder of the [Content Understanding toolkit](https://github.com/Azure/content-understanding-toolkit). You need them to calibrate. To deploy, you only need the calibration table CSV plus `load_table` and `route_value` from step 5 of the notebook, which use the Python standard library alone.

## Interactive explainer

`../../media/acu-dynamic-hitl/dynamic-hitl-explainer.html` is a single-file, offline build of the explainer site in the same toolkit folder (`dynamic_hitl/web_app`), built with `npm run build:single`. It makes no network requests. Its figures are precomputed from the same calibration code and data in this folder.

## Attribution

The receipts, ground truth, and images behind `cord_demo.parquet` come from [CORD v2](https://huggingface.co/datasets/naver-clova-ix/cord-v2) by NAVER Clova (revision `7f0115a4b758a71d6473b8d085751692da2fef98`), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Extracted values and confidence scores were added by running `cord_receipt_v1.json` through Content Understanding.
