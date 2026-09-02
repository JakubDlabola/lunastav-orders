# Code Overview

## Deployment
FastAPI app on Railway. Auto-deploys from `main` branch of `https://github.com/JakubDlabola/lunastav-orders.git`.
Production URL: `lunastav-production.up.railway.app`

## Entry point: `app.py`

### Order form flow
1. `GET /order/{order_id}` — fetches the Odoo sale order and renders the HTML form
2. `POST /order/{order_id}` — validates input, builds Odoo order lines, creates sign request

### Key constants
| Constant | Value | Purpose |
|----------|-------|---------|
| `TAX_RATE` | 1.12 | Converts excl. → incl. VAT |
| `COSMETIC_DISC` | 3.0 | Discount % shown on every line (cosmetic) |
| `GRANT_RATE` | roof=2000, ceiling=750, windows=8000 | Max grant per m² / window |
| `LISTED` | roof=2002, ceiling=751 | Listed price per m² (excl. VAT) used in contract |
| `REF_MAP` | thermofloc→3000, supafil→3100, strikana→3200 | Material → Odoo product prefix |

### Product code suffixes
- `A` = Střecha / Šikminy (e.g. `3000A`)
- `B` = Strop (e.g. `3000B`)
- `4000A/B/C` = Windows, `4001A/B` = Windows (variant)
- `D` = Doprava, `5000A/B/C` = Pochozí vrstva, `5100/5101` = Žaluzie/Sítě

### Work types
| Type | Grant logic | JS section |
|------|-------------|------------|
| Střecha | `GRANT_RATE.roof`, `roofMinRate()` floor | `#roof-section` |
| Strop | `GRANT_RATE.ceiling`, `ceilMinRate()` floor | `#ceiling-section` |
| Šikminy | same as Střecha | `#sikminy-section` |
| Okna | `GRANT_RATE.windows` per window | `#windows-section` |

### Sign request creation (`_create_sign_request`)
- Uploads PDF as `ir.attachment`, creates `sign.template` + `sign.document`
- Places signature fields on the contract sig page and the T&C last page
- Roles: id=15 Objednatel (client signs first), id=18 Zhotovitel (company after)
- Custom fields written at create: `x_client_name`, `x_crm_opportunity`, `x_crm_tipar`, `x_crm_obchodnik`

## `contract.py`

Generates the PDF contract from `Smlouva-LUNASTAV-vzor.docx` via python-docx + LibreOffice.

### Discount logic
- `real_listed_excl` = sum of listed prices (not Odoo price_unit) for insulation lines + windows
- `actual_pct = round(real_discount / real_listed * 100)`
- `discount_pct = max(3, actual_pct)` — always shows at least 3% (cosmetic)
- If `actual_pct < 3`: rescale `real_listed` to `amount_untaxed / 0.97` so the Kč amount is consistent with the 3% label

## Odoo connection
XML-RPC via `execute_kw`. Credentials from `.env`:
- `ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_API_KEY`

### Relevant Odoo model IDs
| Model | ID | Notes |
|-------|----|-------|
| `sign.request` | 665 | Custom fields: x_client_name (30418), x_crm_opportunity (30397), x_crm_tipar (30399), x_crm_obchodnik (30401) |
| Sign list view | 1311 | Extended by view id=4634 (LUNASTAV client column) |
| Objednatel role | 15 | Client signer |
| Zhotovitel role | 18 | Company signer |
| Company partner | 3 | Lukáš Najman |
