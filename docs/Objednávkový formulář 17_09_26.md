# Co je nového v objednávkovém formuláři

## Náhled smlouvy před odesláním

Po vyplnění a odeslání formuláře se nyní zobrazí **náhled vygenerované smlouvy ve formátu PDF** přímo v prohlížeči — ještě předtím, než se cokoliv zapíše do Odoo nebo odešle k podpisu.

Na náhledové stránce máte dvě možnosti:
- **Zpět na formulář** — vrátíte se zpět s tím, že všechna pole zůstanou vyplněná přesně tak, jak byla. Nic se neztratí, lze cokoliv opravit.
- **Potvrdit a odeslat k podpisu** — teprve po kliknutí na toto tlačítko se zakázka zapíše do Odoo, smlouva se uloží jako příloha a odešle se žádost o elektronický podpis.

---

## Načíst šablonu ze starší zakázky

V záhlaví formuláře (vpravo nahoře) je nové tlačítko **„Načíst šablonu"**.

Po kliknutí se otevře vyhledávací panel, kde lze hledat podle:
- čísla zakázky (např. `P261812`)
- jména klienta
- názvu příležitosti
- jména obchodníka

Po výběru zakázky ze seznamu se do formuláře automaticky přenesou **pracovní parametry**:

| Co se přenese |
|---|---|
| Typ práce (střecha, strop, šikminy, okna, dveře…) |
| Materiál a plocha (m²) | 
| Tloušťka izolace |
| Termín dokončení (výběr dní) |
| Dotace zapnuta/vypnuta |
| Žaluzie, sítě, doplňky |
| Vlastní položky |
| Ručně upravený text polí Popis díla / Termín / Stavební připravenost (jen pokud byl text skutečně ručně změněn) |


**Kontaktní údaje a dotační zůstatek zůstanou beze změny** — šablona doplní pouze parametry práce, formulář je stále namířen na aktuálního klienta a aktuální příležitost.

> **Tip:** Šablona funguje nejlépe u opakujících se typů zakázek (stejný materiál, stejná plocha). Po načtení šablony vždy zkontrolujte plochy a ceny — kalkulace se spustí automaticky.

---

## Vlastní položky

Ve formuláři je sekce **„Vlastní položky"** (pod standardními typy prací). Slouží pro libovolné řádky, které nespadají do běžné nabídky — například doprava, lešení, poplatek za likvidaci odpadu apod.

Pro každou vlastní položku se vyplní:
- **Popis** — text, který se zobrazí ve smlouvě
- **Množství** — číslo
- **Jednotka** — ks / m / m²
- **Jednotková cena bez DPH** (Kč)

Tlačítkem **„+ Přidat položku"** lze přidat libovolný počet řádků. Každý řádek lze samostatně odstranit křížkem vpravo.

Vlastní položky se zobrazí ve smlouvě jako standardní řádky zakázky. DPH 12 % se přičítá automaticky, sleva ani dotace se na vlastní položky nevztahují.

Vlastní položky se ukládají do logu a při načtení šablony se přenesou do nového formuláře — stačí pak upravit jen popis nebo cenu.
