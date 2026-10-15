"""
Korespondenční adresa on the order: field x_korespondencni_adresa (sale.order, char) shown in the
"Smlouva o dílo" tab right under Adresa realizace. The order form writes "Shodná s trvalou adresou"
or the address typed in; the contract and dodatek print it under "Trvale bytem/Se sídlem".
Undo: archive the view "LUNASTAV: sale.order form — korespondenční adresa" (the field can stay).

    python setup_korespondencni_adresa.py           # dry run
    python setup_korespondencni_adresa.py --apply
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

FIELD = 'x_korespondencni_adresa'
STUDIO_VIEW = 4597  # "Odoo Studio: sale.order.form customization" — holds the Smlouva o dílo tab; not edited
NAME = 'LUNASTAV: sale.order form — korespondenční adresa'
ARCH = f"""<data>
  <xpath expr="//field[@name='x_studio_adresa_realizace']" position="after">
    <field name="{FIELD}"/>
  </xpath>
</data>"""

model_id = call('ir.model', 'search', [[('model', '=', 'sale.order')]])[0]
if call('ir.model.fields', 'search', [[('model', '=', 'sale.order'), ('name', '=', FIELD)]]):
    print(f'field {FIELD}: exists')
else:
    print(('' if apply else '[dry] ') + f'field {FIELD}: create')
    if apply:
        call('ir.model.fields', 'create', [{
            'model_id': model_id, 'name': FIELD, 'field_description': 'Korespondenční adresa', 'ttype': 'char',
            'state': 'manual', 'copied': True, 'tracking': 0}])

vals = {'name': NAME, 'model': 'sale.order', 'type': 'form', 'mode': 'extension', 'inherit_id': STUDIO_VIEW,
        'priority': 500, 'arch_db': ARCH}
existing = call('ir.ui.view', 'search', [[('name', '=', NAME)]], {'context': {'active_test': False}})
print(('' if apply else '[dry] ') + f'view "{NAME}": {"update" if existing else "create"}')
if apply:
    if existing:
        call('ir.ui.view', 'write', [existing, {**vals, 'active': True}])
    else:
        existing = [call('ir.ui.view', 'create', [vals])]
    print('view id', existing[0])
