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

| Co se přenese | Co se nepřenese |
|---|---|
| Typ práce (střecha, strop, šikminy, okna, dveře…) | Jméno a kontaktní údaje klienta |
| Materiál a plocha (m²) | Zbývající výše dotace (Kč) |
| Tloušťka izolace | |
| Termín dokončení (výběr dní) | |
| Dotace zapnuta/vypnuta | |
| Žaluzie, sítě, doplňky | |
| Vlastní položky | |
| Ručně upravený text polí Popis díla / Termín / Stavební připravenost (jen pokud byl text skutečně ručně změněn) | Automaticky generované texty (ty se přegenerují z nových parametrů) |

**Kontaktní údaje a dotační zůstatek zůstanou beze změny** — šablona doplní pouze parametry práce, formulář je stále namířen na aktuálního klienta a aktuální příležitost.

> **Tip:** Šablona funguje nejlépe u opakujících se typů zakázek (stejný materiál, stejná plocha). Po načtení šablony vždy zkontrolujte plochy a ceny — kalkulace se spustí automaticky.
