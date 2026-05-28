# Mastering Foundry IQ — sample data

This directory holds the local assets the notebook reads at runtime.

## Zava Corporate Presentation

The File Knowledge Source section uploads
`Zava-Corporate-Presentation.pdf` (any PDF / DOCX / HTML / TXT works). Drop
the file here, or point `ZAVA_FILE_UPLOAD_PATH` at any other location:

```bash
export ZAVA_FILE_UPLOAD_PATH=/path/to/your/document.pdf
```

If the file is missing the File KS section is skipped cleanly and the rest
of the notebook still runs.