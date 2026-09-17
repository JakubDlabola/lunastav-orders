"""
Create the 'CUSTOM' generic product used for custom line items in the order form.

    python setup_custom_product.py          # dry run
    python setup_custom_product.py --apply  # create / update
"""
import os, sys, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL, DB, USER, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_USER'], os.environ['ODOO_API_KEY']

uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
call = lambda model, method, args, kw=None: m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

apply = '--apply' in sys.argv

TAX_ID = 21   # 12% G — same as all other LUNASTAV products
UOM_KS = 1    # Ks (pieces) — default; overridden per order line by the form

existing = call('product.template', 'search_read',
                [[('default_code', 'in', ['XXX', 'CUSTOM'])]],
                {'fields': ['id', 'name', 'default_code', 'type']})

if existing:
    tmpl_id = existing[0]['id']
    print(f'Product template CUSTOM already exists: id={tmpl_id} name={existing[0]["name"]!r}')
    if apply:
        call('product.template', 'write', [[tmpl_id], {
            'name':         'Vlastní položka',
            'default_code': 'XXX',
            'type':         'service',
            'uom_id':       UOM_KS,
            'taxes_id':     [[6, 0, [TAX_ID]]],
            'list_price':   0.0,
            'active':       True,
        }])
        print('  Updated.')
    else:
        print('  (dry run — pass --apply to update)')
else:
    print('Creating product template CUSTOM...')
    if apply:
        tmpl_id = call('product.template', 'create', [{
            'name':       'Vlastní položka',
            'default_code': 'CUSTOM',
            'type':       'service',
            'uom_id':     UOM_KS,
            'taxes_id':   [[6, 0, [TAX_ID]]],
            'list_price': 0.0,
        }])
        print(f'  Created product.template id={tmpl_id}')
        prod = call('product.product', 'search_read',
                    [[('product_tmpl_id', '=', tmpl_id)]],
                    {'fields': ['id', 'default_code']})
        print(f'  product.product: {prod}')
    else:
        print('  (dry run — pass --apply to create)')
