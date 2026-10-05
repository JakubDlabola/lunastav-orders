"""
Products for the windows & doors calculator (okna.py): category Okna, VAT 12% G, sale only.
Idempotent: existing codes are updated (name, category, unit, tax), missing ones created.

    python setup_okna_products.py           # dry run
    python setup_okna_products.py --apply
"""
import os
import sys
import xmlrpc.client

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, '..', 'contract_service', '.env'))
URL, DB, USER, KEY = (os.environ[k] for k in ('ODOO_URL', 'ODOO_DB', 'ODOO_USER', 'ODOO_API_KEY'))
uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
call = lambda model, method, a, kw=None: m.execute_kw(DB, uid, KEY, model, method, a, kw or {})
apply = '--apply' in sys.argv

CATEG_OKNA, TAX_12G = 7, 21
UOM = {'Ks': 1, 'm': 9}
PRODUCTS = [  # code, name, unit, type
    ('4010A', 'Okno 1-křídlé', 'Ks', 'consu'),
    ('4010B', 'Okno 2-křídlé', 'Ks', 'consu'),
    ('4010C', 'Okno 3-křídlé', 'Ks', 'consu'),
    ('4011A', 'Balkónové dveře 1-křídlé', 'Ks', 'consu'),
    ('4011B', 'Balkónové dveře 2-křídlé', 'Ks', 'consu'),
    ('4012A', 'Vchodové dveře 1-křídlé', 'Ks', 'consu'),
    ('4012B', 'Vchodové dveře 2-křídlé', 'Ks', 'consu'),
    ('4020', 'Parapet vnitřní PVC', 'm', 'consu'),
    ('4021', 'Žaluzie interiér', 'Ks', 'consu'),
    ('4022', 'Síť proti hmyzu', 'Ks', 'consu'),
    ('4030', 'Montáž plastových výplní včetně systému parozábran', 'm', 'service'),
    ('4031', 'Demontáž oken – PVC', 'm', 'service'),
    ('4032', 'Likvidace oken a drobné suti', 'm', 'service'),
    ('4033', 'Zednické zapravení po montáži parozábran', 'm', 'service'),
    ('4039', 'Další služby (okna)', 'Ks', 'service'),
]

for code, name, unit, ptype in PRODUCTS:
    vals = {'name': name, 'default_code': code, 'categ_id': CATEG_OKNA, 'uom_id': UOM[unit], 'type': ptype,
            'taxes_id': [(6, 0, [TAX_12G])], 'sale_ok': True, 'purchase_ok': False, 'list_price': 0.0}
    existing = call('product.template', 'search', [[('default_code', '=', code)]], {'context': {'active_test': False}})
    print(('' if apply else '[dry] ') + f'{code:6} {name:52} {unit:3} {ptype:8} {"update" if existing else "create"}')
    if apply:
        if existing:
            call('product.template', 'write', [existing, vals])
        else:
            call('product.template', 'create', [vals])
if apply:
    got = call('product.product', 'search_read', [[('default_code', 'in', [p[0] for p in PRODUCTS])]],
               {'fields': ['default_code', 'categ_id', 'taxes_id', 'uom_id']})
    print(f'check: {len(got)}/{len(PRODUCTS)} products,',
          'all Okna + 12% G:', all(g['categ_id'][0] == CATEG_OKNA and g['taxes_id'] == [TAX_12G] for g in got))
