"""
Make the Klient (partner_id) column in the CRM lead list view show as a
clickable avatar.  partner_id is already in the base view (id=1427) with
optional="hide" and no widget — we override its attributes via XPath to
show it by default with widget="many2one_avatar".

    python setup_crm_client_column.py          # dry run
    python setup_crm_client_column.py --apply  # apply
"""
import os, sys, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL, DB, USER, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_USER'], os.environ['ODOO_API_KEY']
uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
call = lambda model, method, args, kw=None: m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

apply = '--apply' in sys.argv

BASE_LIST_VIEW_ID = 1427   # crm.lead.list.opportunity
VIEW_NAME = 'LUNASTAV: crm.lead list — client avatar column'

# partner_id already exists in base view with optional="hide" and no widget.
# Position="attributes" avoids adding a duplicate and sidesteps Studio write issues.
ARCH = """<data>
    <xpath expr="//field[@name='partner_id']" position="attributes">
        <attribute name="widget">many2one_avatar_user</attribute>
        <attribute name="string">Kontakt</attribute>
        <attribute name="optional">show</attribute>
        <attribute name="readonly">1</attribute>
    </xpath>
</data>"""

print(f'Arch:\n{ARCH}')

existing = call('ir.ui.view', 'search_read',
                [[('name', '=', VIEW_NAME), ('model', '=', 'crm.lead')]],
                {'fields': ['id']})

if existing:
    print(f'View already exists (id={existing[0]["id"]}) — will delete and recreate.')
    if apply:
        call('ir.ui.view', 'unlink', [[existing[0]['id']]])
        print(f'  Deleted id={existing[0]["id"]}')
    else:
        print('  (dry run)')

print('Creating view...')
if apply:
    vid = call('ir.ui.view', 'create', [{
        'name':       VIEW_NAME,
        'model':      'crm.lead',
        'type':       'list',
        'inherit_id': BASE_LIST_VIEW_ID,
        'arch_base':  ARCH,
        'priority':   100,
    }])
    print(f'  Created view id={vid}')
else:
    print('  (dry run — pass --apply to create)')
