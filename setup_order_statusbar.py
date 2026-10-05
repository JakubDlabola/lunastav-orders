"""
Order form: move the stage statusbar (Objednávka vytvořena / odeslána / podepsána) out of the header
into its own full-width row at the top of the sheet. In the header it shares the row with the buttons
and Odoo folds it to the current stage only on smaller screens.
Undo: archive the view "LUNASTAV: sale.order form — statusbar v listu".

    python setup_order_statusbar.py           # dry run
    python setup_order_statusbar.py --apply
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

NAME = 'LUNASTAV: sale.order form — statusbar v listu'
ARCH = """<data>
  <xpath expr="//sheet/div[@name='button_box']" position="before">
    <div name="x_statusbar_row" class="d-flex justify-content-end mb-3"/>
  </xpath>
  <xpath expr="//div[@name='x_statusbar_row']" position="inside">
    <xpath expr="//header/field[@name='state']" position="move"/>
  </xpath>
</data>"""

base = call('ir.model.data', 'search_read', [[('module', '=', 'sale'), ('name', '=', 'view_order_form')]],
            {'fields': ['res_id']})[0]['res_id']
vals = {'name': NAME, 'model': 'sale.order', 'type': 'form', 'mode': 'extension', 'inherit_id': base,
        'priority': 500, 'arch_db': ARCH}
existing = call('ir.ui.view', 'search', [[('name', '=', NAME)]], {'context': {'active_test': False}})
print(('' if apply else '[dry] ') + f'view "{NAME}": {"update" if existing else "create"}')
if apply:
    if existing:
        call('ir.ui.view', 'write', [existing, vals])
    else:
        call('ir.ui.view', 'create', [vals])
    arch = call('sale.order', 'get_views', [[[False, 'form']]], {})['views']['form']['arch']
    header = arch[arch.index('<header'):arch.index('</header>')]
    print('statusbar left the header:', 'widget="statusbar"' not in header,
          '| statusbar row in sheet:', 'x_statusbar_row' in arch)
