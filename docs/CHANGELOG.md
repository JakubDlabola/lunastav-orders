# Changelog

## [2026-09-03] — Tlačítko „Přílohy" na kartě kontaktu
- Nový endpoint Railway `GET /download-partner-attachments?partner_id=&key=` — stáhne všechny binární přílohy kontaktu jako ZIP soubor
- Na formuláři kontaktu (res.partner) přidán smart button „Přílohy" (fa-download) — volá ir.actions.server id=1382, který vrátí act_url → Railway → stažení ZIPu v novém tabu
- Přílohy jsou deduplikovány (pokud mají více souborů stejný název)

## [2026-09-02] — Sloupec Kontakt v Podpisech a CRM s klikatelným avatarem
- Widget `many2one_avatar_user` funguje i na polích many2one → res.partner (nejen res.users) a jeho click handler obchází interceptor řádku — tím se odblokoval klikatelný avatar
- Sloupec přejmenován z „Klient" na „Kontakt" v přehledu Podpisů (sign.request list view id=4654)
- Nový sloupec „Kontakt" přidán do přehledu CRM příležitostí (crm.lead list view id=4655) — zobrazuje `partner_id` s `widget="many2one_avatar_user"`, kliknutí na avatar otevře kontaktní stránku

## [2026-09-02] — Klient jako klikatelný odkaz v přehledu podpisů
- `x_client_partner_id` (many2one → res.partner, uložené, id=30420) přidáno na sign.request; doplněno zpětně do 95 záznamů z role Objednatel (role_id=15)
- Sloupec Klient v přehledu podpisů je nyní klikatelný odkaz přímo na kontakt v Odoo — vyžaduje tři obezličky sign_list validace: (a) `column_invisible` companion pro many2one, (b) `x_client_name` char musí být v kombinovaném arch (skrytý), (c) view musí být nový CREATE, ne WRITE na stávající
- Ve formuláři podpisu je `x_client_partner_id` přidáno před pole Dokument jako záložní klikatelný odkaz
- `_create_sign_request()` nyní zapisuje `x_client_partner_id` při vytváření nových žádostí

## [2026-09-02] — CRM fáze Podepsáno při podpisu klienta
- Automatizace 58 (LUNASTAV: Dilci podpis) rozšířena: po podpisu klienta (Objednatel, role=15) se propojená CRM příležitost přesune do fáze Podepsáno (id=6)
- Chráněné fáze: Vyhráno (id=4) a Žádost o dotaci schválená (id=7) — fáze se nikdy neposune zpět
- Podpis Lukáše Najmana (Zhotovitel) změnu fáze nespouští
- Zpráva do chatteru („Částečný podpis přijat…") se nyní přidává jak k zakázce, tak k CRM záznamu

## [2026-09-02] — Dotace pro Dveře (stejná jako Okna)
- Dveře jsou nově zapojeny do dotačního fondu: fDoors = GRANT_RATE.windows × qDoors (8 000 Kč/m²)
- grantPerM2Doors počítán proporcionálně stejně jako grantPerM2Win; eligible_doors = katalogová cena − dotace na m²
- Náhled zobrazuje efektivní cenu po dotaci; na objednávkový řádek v Odoo jde katalogová cena

## [2026-09-02] — Typ práce Dveře + oprava dotace Stropu v kombinaci
- Nový typ práce „Dveře" (fialová, mezi Šikminy a Okny): jedno pole — Plocha dveří (m²), výchozí hodnota 1,8
- Pevná cena 23 277,77 Kč/m² vč. DPH (1,8 m² = 41 900 Kč); kód produktu 4100; aplikována kosmetická sleva 3 %
- Dveře bez dotace; podmínka winOnly nyní zahrnuje i !hasDoors
- Pokud je Strop kombinován se Střechou nebo Šikminy, nastaví se eCeil na 750 Kč/m² (dotace plně pokrývá strop), oblast minimální sazby se ignoruje

## [2026-09-02] — Sloupec se jménem klienta v přehledu podpisů
- Přidáno uložené pole `x_client_name` (char) na `sign.request` v Odoo (field id=30418)
- Sloupec „Klient" přidán do listového pohledu podpisů (id=1311) přes XPath dědičný pohled (id=4634)
- `_create_sign_request()` nyní zapisuje `x_client_name` při vytváření
- Doplněno zpětně do všech 86 existujících žádostí o podpis z řádku předmětu e-mailu

## [2026-08-30] — Oprava výše kosmetické 3% slevy
- Pokud je skutečná sleva nižší než 3 %, katalogová základna se přepočítá na `amount_untaxed / 0,97`, aby zobrazená částka v Kč odpovídala přesně 3 % ze zobrazené katalogové ceny
- Opravuje nesrovnalost „Sleva: 3 % = 179 Kč" u zakázek Šikminy/Střecha s plnou dotací

## [2026-08-30] — Typ práce Šikminy
- Nový typ práce „Šikminy" (azurová, mezi Stropem a Okny ve formuláři)
- Stejné možnosti materiálu a logika dotace/ceny jako Střecha (GRANT_RATE.roof = 2 000 Kč/m²)
- Kód produktu používá příponu ‚A' (stejné produkty jako Střecha: 3000A, 3100A, 3200A)
- Režim winOnly aktualizován — zakázky Šikminy + Okna používají standardní rozdělení, nikoli vynucené 80/20
- Plocha šikminy zahrnuta do insul_area smlouvy a Popisu díla
