# StockDesk 1.24 — camera entry, cashier PINs and operational till reports

This release implements three POS workflows. The other requested payment, offline, inventory, purchasing, finance, CRM, khata, reporting, forecasting and alert modules remain open in CHECKLIST.md. Previously agreed provider, device-specific hardware and native-client exclusions remain unchanged.

## Camera code entry

In POS, choose **Scan with camera**. The browser must provide BarcodeDetector with QR support and camera access on HTTPS or localhost. Plain HTTP on a remote EC2 IP cannot use the camera; the existing HTTP UUID fallback continues to support ordinary checkout. Unsupported decoders, denied permissions and missing cameras show explicit fallback messages. Manual and keyboard scanner input remain available.

The camera scans one QR/barcode value, releases its tracks, fills the code field, and asks the cashier to review quantity and press **Add to bill**. It never opens a QR URL or repeatedly adds an item while the camera sees the same code. Closing, navigating away or hiding the page releases the stream, including late permission responses. Recognized formats are limited to those the browser advertises. There is no bundled software decoder for unsupported browsers.

## Cashier PINs

A built-in Cashier signs in with their account password, opens **Switch cashier**, and sets a 6–12 digit PIN using their current password. PINs use Argon2 hashes. Managers/Owners/admin accounts and custom-role accounts cannot be selected as PIN identities. Users with team-management permission may revoke a cashier PIN; full-password cashiers may revoke their own.

An already authenticated operator with sale permission selects an enrolled cashier and enters that cashier's PIN. Ten failed attempts per initiating account or target cashier in fifteen minutes are rate-limited in PostgreSQL. Failure counters survive rejected transactions; successful switches clear the corresponding counters. The old browser session is removed and a new HttpOnly session is issued, restricted to this business and the cashier's PIN revision, for at most eight hours. Bearer-based switching is rejected.

Other businesses, including businesses where that account is an Owner, are not exposed through the switched session. Changing membership activity/role/custom role or account activity/admin status deletes enrolled PINs and scoped sessions. PIN replacement/revocation invalidates all prior PIN sessions. Password-authenticated sessions retain their ordinary behavior. PIN sessions cannot update PINs; sign out and authenticate with a password first.

Hold or clear the active bill before switching; switching is disabled while the current cart, receipt or transaction is active. Reload discards transient UI state and fetches the new cashier's permissions/till/held bills. Other open tabs reload when notified of a switch; use one active POS tab per workstation. Audits record initiating and target identities, never credentials.

## Operational X/Z reports

**Till sessions → View X report** reads the current open till without closing it. Closing atomically stores a numbered Z report, a SHA-256 digest and counted/expected cash evidence. Repeated identical closes reuse the same report; changed closing data is rejected. Database triggers reject edits/deletions of Z reports and return events. **View Z report** loads the frozen snapshot. The UI exports the exact report and digest as JSON.

Reports show original invoice subtotal/discount/tax/total, credit sales, tender totals, return credits/tax, net sales/tax, cash movements, opening/expected/counted cash and variance, plus invoice and return references. Gross invoice evidence uses original pre-adjustment amounts; partial/full return events are attributed to the operator's currently open till. A later return does not alter an earlier Z report. Cash adjustments already create refund movements; legacy full returns still require one manual cash-out entry when cash is actually paid. Never subtract invoice return credit twice from expected cash.

Return events begin with migration 031. Historical return dates are not invented, and old closed sessions are not backfilled with reconstructed Z reports. Transactions without an open till stay outside these reports. Invoice credits are not proof of external settlement. These are operational reports, not a tax-authority-certified fiscal device, statutory filing, or FBR submission.

## Deployment

Migrations 030 and 031 are new; previously shipped migrations are unchanged. Keep the existing external PostgreSQL/Docker setup. No additional dependency, database container or device SDK is added. No live AWS deployment or physical camera acceptance is claimed.
