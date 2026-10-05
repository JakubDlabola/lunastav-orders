"""Windows & doors calculator (port of the Úsporami portal "Okna napřímo" calculator, ceník 2026).

Prices in okna_cenik_2026.json are without VAT. Dimensions are rounded up to the next point of the
price grid; anything above the grid is rejected. The browser shows the same prices (okna_form.js),
but order lines are always recomputed here from the submitted items.
"""
import json
import os

CENIK = json.load(open(os.path.join(os.path.dirname(__file__), 'okna_cenik_2026.json'), encoding='utf-8'))

TYPES = {  # calculator type → (Odoo product code, label)
    'jednokridla': ('4010A', 'Okno 1-křídlé'),
    'dvoukridla': ('4010B', 'Okno 2-křídlé'),
    'trojkridla': ('4010C', 'Okno 3-křídlé'),
    'bd_jedno': ('4011A', 'Balkónové dveře 1-křídlé'),
    'bd_dvou': ('4011B', 'Balkónové dveře 2-křídlé'),
    'vd_jedno': ('4012A', 'Vchodové dveře 1-křídlé'),
    'vd_dvou': ('4012B', 'Vchodové dveře 2-křídlé'),
}
DOOR_TYPES = {'bd_jedno', 'bd_dvou', 'vd_jedno', 'vd_dvou'}
SURFACES = {'Bila': 'bílá', 'Dekor1str': 'dekor 1-stranný', 'Dekor2str': 'dekor 2-stranný'}
GLASS = {'trojsklo': 'trojsklo', 'dvojsklo': 'dvojsklo'}
PARAPET_GROUPS = {1: 'bílá', 2: 'dekor'}
BASIC_WORK = {  # the four basic services, priced per running metre of the items' perimeter
    'Montáž plastových výplní včetně systému parozábran': '4030',
    'Demontáž oken - PVC': '4031',
    'Likvidace oken a drobné suti': '4032',
    'Zednické zapravení po montáži parozábran': '4033',
}
CODE_PARAPET, CODE_ZALUZIE, CODE_SIT, CODE_OTHER_WORK = '4020', '4021', '4022', '4039'
ALL_CODES = ({c for c, _ in TYPES.values()} | set(BASIC_WORK.values())
             | {CODE_PARAPET, CODE_ZALUZIE, CODE_SIT, CODE_OTHER_WORK})
WORK = {w['nazev']: w for w in CENIK['work']}


class CenikError(ValueError):
    pass


def _point(value, points):
    for i, p in enumerate(points):
        if p >= value:
            return i
    return None


def vypln(povrch, typ, sirka, vyska):
    """Price of one window/door without VAT."""
    table = CENIK['windows'].get(povrch, {}).get(typ)
    if not table:
        raise CenikError(f'Neznámý typ výplně {typ} / povrch {povrch}.')
    i, j = _point(sirka, table['widths']), _point(vyska, table['heights'])
    if i is None or j is None:
        raise CenikError(f'Rozměr {sirka}×{vyska} mm je mimo rozsah ceníku pro {TYPES[typ][1]} '
                         f'(max {table["widths"][-1]}×{table["heights"][-1]} mm).')
    return table['grid'][j][i]


def parapet_za_metr(skupina, hloubka):
    table = CENIK['accessories']['parapet_pvc_interier']
    i = _point(hloubka, table['depths'])
    if i is None:
        raise CenikError(f'Hloubka parapetu {hloubka} mm je nad rozsahem ceníku (max {table["depths"][-1]} mm).')
    return (table['g1'] if skupina == 1 else table['g2'])[i]


def stineni(druh, sirka, vyska):
    """Interior blinds ('zaluzie') or insect net ('site'), price per piece."""
    table = CENIK['accessories'][druh]
    i, j = _point(sirka, table['widths']), _point(vyska, table['heights'])
    if i is None or j is None:
        raise CenikError(f'Rozměr {sirka}×{vyska} mm je mimo rozsah ceníku ({"žaluzie" if druh == "zaluzie" else "síť"}).')
    return table['grid'][j][i]


def obvod_bm(items):
    """Running metres of all items' perimeters (default quantity of the basic services)."""
    return round(10 * sum(2 * (it['sirka'] + it['vyska']) / 1000 * it['ks'] for it in items)) / 10


def plocha_m2(items):
    return sum(it['sirka'] * it['vyska'] / 1e6 * it['ks'] for it in items)


def _num(v, field, minimum=0):
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise CenikError(f'Neplatná hodnota {field}: {v!r}')
    if n < minimum:
        raise CenikError(f'Neplatná hodnota {field}: {v!r}')
    return n


def normalize_items(raw_items):
    """Validated items from the form JSON (prices are never taken from the browser)."""
    items = []
    for raw in raw_items or []:
        typ, povrch = raw.get('typ'), raw.get('povrch')
        if typ not in TYPES or povrch not in SURFACES:
            raise CenikError(f'Neznámý typ nebo povrch výplně: {typ} / {povrch}')
        it = {'typ': typ, 'povrch': povrch, 'sklo': raw.get('sklo') if raw.get('sklo') in GLASS else 'trojsklo',
              'sirka': int(_num(raw.get('sirka'), 'šířka', 1)), 'vyska': int(_num(raw.get('vyska'), 'výška', 1)),
              'ks': int(_num(raw.get('ks') or 1, 'počet ks', 1)), 'parapet': None, 'zaluzie': None, 'sit': None}
        p = raw.get('parapet')
        if p and _num(p.get('delkaM'), 'délka parapetu') > 0:
            if _num(p.get('delkaM'), 'délka parapetu') > 50:
                raise CenikError('Délka parapetu se zadává v metrech (max 50 m).')
            it['parapet'] = {'hloubka': int(_num(p.get('hloubka'), 'hloubka parapetu', 1)),
                             'skupina': 2 if int(_num(p.get('skupina') or 1, 'skupina')) == 2 else 1,
                             'delkaM': _num(p.get('delkaM'), 'délka parapetu')}
        for key in ('zaluzie', 'sit'):
            s = raw.get(key)
            if s and _num(s.get('sirka') or 0, 'šířka') > 0 and _num(s.get('vyska') or 0, 'výška') > 0:
                it[key] = {'sirka': int(_num(s['sirka'], 'šířka', 1)), 'vyska': int(_num(s['vyska'], 'výška', 1))}
        items.append(it)
    return items


def work_quantities(items, prace):
    """[(name, quantity)] of the selected services. prace = {'basic': {name: {'on', 'manual'}}, 'dalsi': {name: qty}}"""
    prace = prace or {}
    out = []
    obvod = obvod_bm(items)
    for name in BASIC_WORK:
        state = (prace.get('basic') or {}).get(name, {'on': True, 'manual': None})
        if not state.get('on'):
            continue
        manual = state.get('manual')
        qty = _num(manual, name) if manual not in (None, '') else obvod
        if qty > 0:
            out.append((name, qty))
    for name, qty in (prace.get('dalsi') or {}).items():
        if name in WORK and name not in BASIC_WORK and _num(qty, name) > 0:
            out.append((name, _num(qty, name)))
    return out


def _fmt(n):
    return f'{n:g}'.replace('.', ',')


def lines(items, prace):
    """Order lines without VAT: [{code, name, qty, unit, price}] where price is per unit and qty × price is
    the calculator's amount. unit: 'Ks', 'm', 'm²', 'km' (Odoo UoM names)."""
    out = []
    for n, it in enumerate(items, start=1):
        code, label = TYPES[it['typ']]
        price = vypln(it['povrch'], it['typ'], it['sirka'], it['vyska'])
        out.append({'code': code, 'unit': 'Ks', 'qty': it['ks'], 'price': price,
                    'name': f'{label}, {SURFACES[it["povrch"]]}, {it["sirka"]} × {it["vyska"]} mm, {it["sklo"]}'})
        ref = f' (k pol. {n})' if len(items) > 1 else ''
        if it['parapet']:
            p = it['parapet']
            out.append({'code': CODE_PARAPET, 'unit': 'm', 'qty': round(p['delkaM'] * it['ks'], 2),
                        'price': parapet_za_metr(p['skupina'], p['hloubka']),
                        'name': f'Parapet vnitřní PVC {p["hloubka"]} mm, {PARAPET_GROUPS[p["skupina"]]}, '
                                f'{_fmt(p["delkaM"])} m{ref}'})
        for key, code, label in (('zaluzie', CODE_ZALUZIE, 'Žaluzie interiér'), ('sit', CODE_SIT, 'Síť proti hmyzu')):
            if it[key]:
                s = it[key]
                out.append({'code': code, 'unit': 'Ks', 'qty': it['ks'],
                            'price': stineni('zaluzie' if key == 'zaluzie' else 'site', s['sirka'], s['vyska']),
                            'name': f'{label} {s["sirka"]} × {s["vyska"]} mm{ref}'})
    unit_map = {'bm': 'm', 'm2': 'm²', 'km': 'km'}
    for name, qty in work_quantities(items, prace):
        w = WORK[name]
        unit = unit_map.get(w['jednotka'], 'Ks')
        label = name if unit != 'Ks' or w['jednotka'] == 'ks' else f'{name} ({w["jednotka"]})'
        out.append({'code': BASIC_WORK.get(name, CODE_OTHER_WORK), 'unit': unit, 'qty': qty,
                    'price': w['cena'], 'name': label})
    return out


COSMETIC_DISC = 3.0  # every line shows the 3 % discount: unit price = price / 0.97, discount 3 %


def _round2(value):
    """Round half up to 0.01 like Odoo (tolerant of binary representation error)."""
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(repr(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def unit_price(price):
    """Odoo unit price of a line whose discounted unit price is `price`."""
    return _round2(price / (1 - COSMETIC_DISC / 100))


def total_without_vat(rows):
    """Sum of the lines' subtotals exactly as Odoo computes them (rounded unit price, 3 % off, rounded line)."""
    return _round2(sum(_round2(unit_price(r['price']) * (1 - COSMETIC_DISC / 100) * r['qty']) for r in rows))
