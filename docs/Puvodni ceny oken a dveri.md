# Původní ceny oken a dveří (do 6. 10. 2026)

Ceny, které objednávkový formulář používal před přechodem na kalkulačku oken z portálu Úsporami (`okna_cenik_2026.json`). Odoo produkty s těmito kódy zůstávají kvůli starším objednávkám, formulář je už nepoužívá.

## Okna (cena za m², vč. DPH 12 %)

| Kód | Produkt | Cena |
|---|---|---|
| 4000A | Okno, nebarvené | 9 000 Kč/m² |
| 4000B | Okno, jednostranná barva | 9 900 Kč/m² |
| 4000C | Okno, oboustranná barva | 10 800 Kč/m² |
| 4001A | Žaluzie | 1 000 Kč/m² |
| 4001B | Síť proti hmyzu | 1 000 Kč/m² |

- Okna: výchozí rozdělení platby 80 / 20, pokud zakázka obsahuje jen okna
- Žaluzie a sítě: plocha se předvyplňovala plochou oken

## Dveře

| Kód | Produkt | Cena |
|---|---|---|
| 4100 | Dveře | 23 277,77 Kč/m² vč. DPH (1,8 m² = 41 900 Kč) |

- Výchozí plocha dveří 1,8 m²
- Cena už obsahovala kosmetickou slevu 3 %; v Odoo šla jako `23 277,77 / 0,97 / 1,12` bez DPH se slevou 3 %

## Dotace

- Okna i dveře: 8 000 Kč/m² (NZÚ), podíl na zbývající dotaci poměrem k ostatním typům práce
- Klient platil u oken a dveří ceníkovou cenu minus dotace na m²
