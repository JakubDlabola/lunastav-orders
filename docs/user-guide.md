# User Guide — LUNASTAV Order Form

## Accessing the form
Open `https://lunastav-production.up.railway.app/order/<ORDER_ID>?key=lunastav-smlouva-2025`

Replace `<ORDER_ID>` with the Odoo sale order ID (numeric).

## Filling in the form

### 1. Client details
Pre-filled from Odoo. You can override the name, address, email, phone, and date of birth here — the contract will use your overrides, and the partner record in Odoo is updated.

### 2. Work types
Check one or more boxes:

| Type | What it covers |
|------|---------------|
| Střecha | Flat/pitched roof insulation |
| Strop | Ceiling insulation |
| Šikminy | Rafter/sloped ceiling insulation |
| Okna | Window replacement |

Each selected type shows its own section below.

### 3. Insulation sections (Střecha / Strop / Šikminy)
- **Materiál** — select the insulation product
- **Tloušťka izolace** — thickness in cm (default 35)
- **Plocha** — area in m²

### 4. Windows section (Okna)
Enter quantities for each window type (A/B/C). Optionally add blinds (žaluzie) and insect screens (sítě).

### 5. Price preview
The right panel updates live and shows:
- Effective price per m² (after grant)
- Total grant amount
- Záloha (deposit) and Doplatek (balance)

### 6. Additional options
- **Doprava** — delivery charge (Kč, incl. VAT)
- **Pochozí vrstva** — walkable surface products
- **Stavební připravenost** — site readiness notes (appear in contract)
- **Popis díla** — auto-generated from selections; you can edit manually

### 7. Payment split
- Default: 60% záloha / 40% doplatek
- Windows-only orders: 80% / 20%
- Custom split: check "Vlastní rozdělení"

### 8. Submitting
Click **Odeslat smlouvu k podpisu**. The system will:
1. Update the Odoo order
2. Generate and attach the PDF contract
3. Send the signing request — client receives an email with a link to sign first, then the company co-signs

## Signing flow
- Client receives email → clicks link → signs in browser (no account needed)
- After client signs, company representative receives notification and co-signs
- Both parties receive a signed copy by email

## Troubleshooting

| Problem | Likely cause |
|---------|-------------|
| Form won't submit | Check the checklist that appears above the button — all red items must be resolved |
| "Produkt nenalezen v Odoo" error | The material/product code combination doesn't exist in Odoo — contact the dev |
| Wrong client name on contract | Edit the "Jméno klienta" field on the form before submitting |
