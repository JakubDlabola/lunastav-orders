"""
Add a "Stáhnout přílohy" smart button to the res.partner form view.

Steps:
  1. Create ir.actions.server on res.partner that returns act_url → Railway endpoint
  2. Add smart button in the partner form's button_box that triggers the server action

    python setup_partner_download_button.py          # dry run
    python setup_partner_download_button.py --apply  # apply
"""
import os, sys, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL, DB, USER, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_USER'], os.environ['ODOO_API_KEY']
SERVICE_KEY = os.environ['SERVICE_KEY']
RAILWAY_URL = 'https://lunastav-production.up.railway.app'

uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
call = lambda model, method, args, kw=None: m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

apply = '--apply' in sys.argv

PARTNER_MODEL_ID = call('ir.model', 'search', [[('model', '=', 'res.partner')]])[0]
ACTION_NAME = 'LUNASTAV: Stáhnout přílohy kontaktu'
VIEW_NAME   = 'LUNASTAV: res.partner form — download attachments button'

# ── 1. Find base res.partner form view ───────────────────────────────────────
base_views = call('ir.ui.view', 'search_read',
                  [[('model', '=', 'res.partner'), ('type', '=', 'form'),
                    ('inherit_id', '=', False)]],
                  {'fields': ['id', 'name', 'priority']})
base_views.sort(key=lambda v: v['priority'])
base_view_id = base_views[0]['id']
print(f'Base res.partner form view: id={base_view_id} ({base_views[0]["name"]})')

# ── 2. Create ir.actions.server ───────────────────────────────────────────────
existing_action = call('ir.actions.server', 'search_read',
                       [[('name', '=', ACTION_NAME)]],
                       {'fields': ['id']})
if existing_action:
    action_id = existing_action[0]['id']
    print(f'Server action already exists: id={action_id}')
else:
    # The code embeds SERVICE_KEY directly — server actions are admin-only in Odoo.
    action_code = (
        "action = {\n"
        "    'type': 'ir.actions.act_url',\n"
        f"    'url': '{RAILWAY_URL}/download-partner-attachments?partner_id=' + str(record.id) + '&key={SERVICE_KEY}',\n"
        "    'target': 'new',\n"
        "}"
    )
    print(f'Server action code:\n{action_code}')
    if apply:
        action_id = call('ir.actions.server', 'create', [{
            'name':             ACTION_NAME,
            'model_id':         PARTNER_MODEL_ID,
            'state':            'code',
            'code':             action_code,
            'binding_model_id': PARTNER_MODEL_ID,
            'binding_type':     'action',
        }])
        print(f'  Created server action id={action_id}')
    else:
        print('  (dry run)')
        action_id = '<action_id>'

# ── 3. Add smart button to res.partner form ───────────────────────────────────
FORM_ARCH = f"""<data>
    <xpath expr="//div[@name='button_box']" position="inside">
        <button name="{action_id}" type="action" class="oe_stat_button" icon="fa-download" string="Přílohy"/>
    </xpath>
</data>"""

print(f'\nForm view arch:\n{FORM_ARCH}')

existing_view = call('ir.ui.view', 'search_read',
                     [[('name', '=', VIEW_NAME), ('model', '=', 'res.partner')]],
                     {'fields': ['id']})
if existing_view:
    print(f'Form inherit view already exists (id={existing_view[0]["id"]}) — deleting and recreating.')
    if apply:
        call('ir.ui.view', 'unlink', [[existing_view[0]['id']]])

if apply:
    vid = call('ir.ui.view', 'create', [{
        'name':       VIEW_NAME,
        'model':      'res.partner',
        'type':       'form',
        'inherit_id': base_view_id,
        'arch_base':  FORM_ARCH,
        'priority':   100,
    }])
    print(f'  Created form inherit view id={vid}')
else:
    print('  (dry run — pass --apply to create)')
