# Uživatelská příručka — objednávkový formulář LUNASTAV

## Přístup k formuláři
Otevřete `https://lunastav-orders-production.up.railway.app/order/<ORDER_ID>?key=lunastav-smlouva-2025`

Místo `<ORDER_ID>` doplňte číselné ID zakázky z Odoo.

## Vyplnění formuláře

### 1. Údaje klienta
Předvyplněno z Odoo. Jméno, adresu, e-mail, telefon a datum narození lze na formuláři upravit — smlouva použije vaše hodnoty a partner v Odoo se také aktualizuje.

### 2. Typ prací
Zaškrtněte jeden nebo více typů:

| Typ | Co zahrnuje |
|-----|-------------|
| Střecha | Zateplení ploché nebo šikmé střechy |
| Strop | Zateplení stropu |
| Šikminy | Zateplení krokví / šikmých podhledů |
| Okna | Výměna oken |

Každý zaškrtnutý typ zobrazí odpovídající sekci níže.

### 3. Sekce zateplení (Střecha / Strop / Šikminy)
- **Materiál** — vyberte izolační produkt
- **Tloušťka izolace** — tloušťka v cm (výchozí hodnota 35)
- **Plocha** — plocha v m²

### 4. Sekce oken (Okna)
Zadejte počty pro každý typ okna (A/B/C). Volitelně přidejte žaluzie a sítě proti hmyzu.

### 5. Náhled ceny
Panel na pravé straně se aktualizuje průběžně a zobrazuje:
- Efektivní cenu za m² (po dotaci)
- Celkovou výši dotace
- Zálohu a doplatek

### 6. Další možnosti
- **Doprava** — cena dopravy (Kč vč. DPH)
- **Pochozí vrstva** — produkty pochozí vrstvy
- **Stavební připravenost** — poznámky k připravenosti stavby (zobrazí se ve smlouvě)
- **Popis díla** — generuje se automaticky z výběru; lze ručně upravit

### 7. Rozdělení platby
- Výchozí: 60 % záloha / 40 % doplatek
- Pouze okna: 80 % / 20 %
- Vlastní rozdělení: zaškrtněte „Vlastní rozdělení"

### 8. Odeslání
Klikněte na **Odeslat smlouvu k podpisu**. Systém provede:
1. Aktualizaci zakázky v Odoo
2. Vygenerování a připojení PDF smlouvy
3. Odeslání žádosti o podpis — klient obdrží e-mail s odkazem pro podpis jako první, poté spolupodepisuje zhotovitel

## Průběh podpisu
- Klient obdrží e-mail → klikne na odkaz → podepíše v prohlížeči (bez nutnosti registrace)
- Po podpisu klientem obdrží zástupce firmy upozornění a spolupodepíše
- Obě strany obdrží e-mailem podepsanou kopii

## Řešení problémů

| Problém | Pravděpodobná příčina |
|---------|-----------------------|
| Formulář nelze odeslat | Zkontrolujte seznam chyb nad tlačítkem — všechny červené položky musí být vyřešeny |
| Chyba „Produkt nenalezen v Odoo" | Kombinace materiálu a produktového kódu v Odoo neexistuje — kontaktujte vývojáře |
| Špatné jméno klienta na smlouvě | Před odesláním upravte pole „Jméno klienta" na formuláři |
