# StockDesk 1.26 — legacy XLS catalog import

Catalog uploads now accept Excel 97–2003 BIFF8 `.xls`, alongside CSV and XLSX. Conversion feeds the same permission-checked preview and atomic create/update workflow, including stale preview protection and idempotent commits. Existing-SKU updates preserve stock.

Use the existing template headers, one visible worksheet, at most 200 product rows and a 1 MB upload. SKU, category, unit and barcode cells must be text; leading zeros and Unicode are preserved. Formulas (including cached-result formulas), macros, external links, embedded objects, encryption, date/boolean/error cells and unsupported workbook structures are rejected. Older pre-BIFF8 files must be saved as XLSX first. This is a values-only catalog importer, not a general spreadsheet editor.

The backend adds pinned `xlrd==2.0.1`; rebuild Docker images to install it. No database migration or external PostgreSQL configuration change is required. Existing migrations are unchanged.

The remaining checklist remains authoritative. This release completes legacy XLS import, not serial tracking, warehouses, offline sales, finance, CRM or the other outstanding enterprise workflows.
