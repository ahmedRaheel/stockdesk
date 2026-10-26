# StockDesk 1.22 — variant families, pack conversion and BOM assembly

This release adds three catalog/inventory capabilities. The remaining enterprise scope is not fully complete. Prior exclusions for payment/notification/accounting/e-commerce providers, device-specific hardware and native clients remain in effect.

## Variant families

Open **Variants, recipes and packs → Variant families**. Create a named family with one to six axes (such as size/color), then assign existing catalog SKUs with exactly those attributes. Each variant keeps its own SKU, barcode, selling price, cost, unit and stock. Create those products through Inventory first; this feature does not manufacture a combinatorial matrix of new products automatically.

Combinations are unique within a family, with case-insensitive duplicate detection. A SKU belongs to one family at a time. Assignments can be edited, moved to another family or detached without changing stock or historical invoice lines. Existing SKU snapshots continue to identify historical sales. A persistent product revision prevents stale edits even after detach/reassign cycles. Family names and active state are editable with optimistic versions; axes are fixed after creation. Disabling a family stops new assignments, not sales of already assigned SKUs.

Family names and attribute labels are included in product API searches and POS search/display. Product management permission is required for writes; catalog readers may read definitions. Lists are searched/paginated. Mutations are tenant-locked, CSRF-protected and audited.

## Pack conversion

A pack recipe defines one output SKU and exactly one component SKU with a quantity per output unit. For example, `PACK-6 = 6 × UNIT`. **Build / pack** deducts component quantities and adds output stock. **Unpack** consumes the pack SKU and returns component quantities. The quantity field always measures output units/packs from the recipe definition; unpacking 2 PACK-6 creates 12 UNIT.

Conversions are explicit inventory operations, not alternative price-only barcodes or automatic conversions at checkout. Both SKUs are independently sold through existing POS, purchasing and returns. The application does not infer interchangeable units from names or prices.

## Recipes / BOM

A BOM defines one output SKU and up to 50 distinct stocked components per output unit. Assemble an entered quantity, assign an output lot/expiry, record a note, preview exact component batches, then confirm. Output stock becomes available to ordinary checkout immediately after confirmation.

Recipes may refer to already stocked intermediate output SKUs. Cyclic definitions are rejected. Assembly consumes stocked components only; it does not recursively manufacture shortages. General BOM disassembly, variable yield/scrap, labor/overhead accounting, work orders and production scheduling are not included. Pack recipes alone support reverse conversion.

After the first posted job, a recipe's output SKU, type and component ratios are frozen. Its name and active state can still change. Use a new output SKU/recipe for a different physical conversion. This avoids unpacking old stock under a newly changed ratio.

## Stock, expiry and cost controls

- Preview allocates non-expired input batches in FEFO order. Whole-unit rules apply to input and output SKUs; quantities cannot be silently rounded beyond three decimal places.
- Output expiry must not exceed the earliest consumed expiry, and cannot be in the past. When any consumed batch is dated, an output expiry is mandatory. Expiry-tracked output SKUs also require a date. Every job requires an output lot and note.
- Confirmation rechecks recipe version, batch allocations and input stock revisions. A stale preview is rejected; insufficient stock never triggers automatic replenishment.
- Input OUT movements, output IN movements, the frozen recipe snapshot and immutable job record are posted in one transaction. The recorded result includes source batch IDs/lots/quantities and movement IDs. Failed output writes roll back earlier input debits.
- Identical request retries return the recorded result without consuming stock again. Reusing the request for different data is rejected.
- The preview's input cost is a current-catalog estimate. It is **not** receipt-layer/FIFO/LIFO valuation. Output product costs are not changed automatically, and no general-ledger entries are posted. Landed costs and advanced valuation remain outstanding.

## API

Prefix: `/api/v1/tenants/{tenant}/catalog-tools`.

- `GET/POST /families`; GET supports `q` and `offset` (50 rows).
- `GET/PUT /families/{id}`; detail supports variant `offset`; updates require current `version`.
- `GET /variants/{product}` returns current persistent revision and assignment, if any.
- `PUT /families/{id}/variants/{product}` with `version`, `attributes`; DELETE uses `?version=N` and preserves the product.
- `GET/POST /recipes`; GET supports `q` and `offset` (50 rows).
- `GET/PUT /recipes/{id}`; updates require current `version`.
- `POST /recipes/{id}/preview` with `version`, `direction=build|unpack`, `quantity`, `lot`, nullable `expires`, `note`.
- `POST /recipes/{id}/jobs` adds `request` and the preview `quote_token`.
- `GET /jobs?offset=N` returns 50 immutable job results per page.

Recipe reads and all assembly operations require existing `stock` permission (which includes cost access in supported roles). Variant writes require `product`; reads require `read`. No permission defaults or external integrations were added.

## Upgrade

Back up existing PostgreSQL, preserve `.env`, and deploy backend and frontend together using the README commands. Migration **028_catalog_assembly.sql** adds families, variant metadata/revisions, recipe/job records and the search-label view. Existing migrations 001–027 are unchanged. Existing products start without family membership. There is no stock backfill, cost revaluation or new database container. The HTTP-compatible request-ID helper remains in use.
