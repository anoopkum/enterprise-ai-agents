# OCR extractions — travel brochures

Azure AI Document Intelligence (`prebuilt-layout`) output for the public
travel-brochure PDFs in `../` (Margie's Travel sample set). Generated with the
app's own OCR path (`src/ingestion/ocr.py`) against the `di-kyc-aml-dev` resource.

Per PDF:
- `<name>.txt`  — full extracted text (`AnalyzeResult.content`)
- `<name>.json` — structured summary: model, page dimensions, line/word counts,
  per-page mean word confidence, tables

`_summary.json` rolls all six up.

This is public, PII-free reference content — safe to commit (hence the
`!data/extracted/` allowlist in `.gitignore`). It is **not** ingested into the
KYC search index; it exists only to demonstrate the Document Intelligence OCR leg.
