"""
Add a "Přílohy" smart button to the crm.lead form view.

Steps:
  1. Create ir.actions.server on crm.lead that returns act_url → Railway endpoint
  2. Add smart button in the lead form's button_box that triggers the server action

    python setup_crm_download_button.py          # dry run
    python setup_crm_download_button.py --apply  # apply
"""
import os, sys, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL, DB, USER, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_USER'], os.environ['ODOO_API_KEY']
SERVICE_KEY = os.environ['SERVICE_KEY']
RAILWAY_URL = 'https://lunastav-orders-production.up.railway.app'

uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
call = lambda model, method, args, kw=None: m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

apply = '--apply' in sys.argv

CRM_MODEL_ID = call('ir.model', 'search', [[('model', '=', 'crm.lead')]])[0]
BASE_FORM_VIEW_ID = 1418   # crm.lead.form
ACTION_NAME = 'LUNASTAV: Stáhnout přílohy příležitosti'
VIEW_NAME   = 'LUNASTAV: crm.lead form — download attachments button'

# ── 1. Create or update ir.actions.server ────────────────────────────────────
action_code = (
    "action = {\n"
    "    'type': 'ir.actions.act_url',\n"
    f"    'url': '{RAILWAY_URL}/download-attachments?model=crm.lead&record_id=' + str(record.id) + '&key={SERVICE_KEY}',\n"
    "    'target': 'new',\n"
    "}"
)
print(f'Server action code:\n{action_code}')

existing_action = call('ir.actions.server', 'search_read',
                       [[('name', '=', ACTION_NAME)]],
                       {'fields': ['id']})
if existing_action:
    action_id = existing_action[0]['id']
    print(f'Server action already exists: id={action_id} — updating...')
    if apply:
        call('ir.actions.server', 'write', [[action_id], {'code': action_code}])
        print(f'  Updated server action id={action_id}')
    else:
        print('  (dry run)')
else:
    print('Creating server action...')
    if apply:
        action_id = call('ir.actions.server', 'create', [{
            'name':             ACTION_NAME,
            'model_id':         CRM_MODEL_ID,
            'state':            'code',
            'code':             action_code,
            'binding_model_id': CRM_MODEL_ID,
            'binding_type':     'action',
        }])
        print(f'  Created server action id={action_id}')
    else:
        print('  (dry run)')
        action_id = '<action_id>'

# ── 2. Add smart button to crm.lead form ─────────────────────────────────────
FORM_ARCH = f"""<data>
    <xpath expr="//div[@name='button_box']" position="inside">
        <button name="{action_id}" type="action" class="oe_stat_button" icon="fa-download" string="Přílohy"/>
    </xpath>
</data>"""

print(f'\nForm view arch:\n{FORM_ARCH}')

existing_view = call('ir.ui.view', 'search_read',
                     [[('name', '=', VIEW_NAME), ('model', '=', 'crm.lead')]],
                     {'fields': ['id']})
if existing_view:
    print(f'Form inherit view already exists (id={existing_view[0]["id"]}) — deleting and recreating.')
    if apply:
        call('ir.ui.view', 'unlink', [[existing_view[0]['id']]])

if apply:
    vid = call('ir.ui.view', 'create', [{
        'name':       VIEW_NAME,
        'model':      'crm.lead',
        'type':       'form',
        'inherit_id': BASE_FORM_VIEW_ID,
        'arch_base':  FORM_ARCH,
        'priority':   100,
    }])
    print(f'  Created form inherit view id={vid}')
else:
    print('  (dry run — pass --apply to create)')
