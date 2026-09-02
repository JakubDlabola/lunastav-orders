# Changelog

## [2026-09-02] — Dveře grant (same as Okna)
- Dveře now participates in the grant pool: fDoors = GRANT_RATE.windows × qDoors (8 000 Kč/m²)
- grantPerM2Doors computed proportionally like grantPerM2Win; eligible_doors = listed − grant per m²
- Preview shows effective rate after grant; listed price still goes on the Odoo order line

## [2026-09-02] — Dveře work type + Strop combined-mode grant fix
- New "Dveře" work type (violet, between Šikminy and Okna): one field — Plocha dveří (m²), default 1.8
- Fixed price 23 277,77 Kč/m² incl. VAT (1,8 m² = 41 900 Kč); product code 4100; cosmetic 3% discount applied
- No grant for doors; winOnly mode now also requires !hasDoors
- When Strop is combined with Střecha or Šikminy, eCeil is set to 750 Kč/m² (grant covers it exactly), bypassing the area-based floor

## [2026-09-02] — Client name column in Signatures list
- Added `x_client_name` stored char field to `sign.request` in Odoo (field id=30418)
- Added "Klient" column to Sign list view (id=1311) via XPath inherit view (id=4634)
- `_create_sign_request()` now writes `x_client_name` at create time
- Backfilled all 86 existing sign requests from their subject line

## [2026-08-30] — Cosmetic 3% discount amount fix
- When the real discount is below 3%, the listed-price base is rescaled to `amount_untaxed / 0.97` so the displayed Kč amount is exactly 3% of the shown listed price
- Prevents the "Sleva: 3% = 179 Kč" inconsistency on full-grant Šikminy/Střecha orders

## [2026-08-30] — Šikminy work type
- New work type "Šikminy" (cyan, between Strop and Okna in the order form)
- Same material options and grant/price logic as Střecha (GRANT_RATE.roof = 2 000 Kč/m²)
- Product code uses 'A' suffix (same products as Střecha: 3000A, 3100A, 3200A)
- `winOnly` mode updated — Šikminy + Okna orders use normal split, not forced 80/20
- Contract insul_area and Popis díla include Šikminy area
