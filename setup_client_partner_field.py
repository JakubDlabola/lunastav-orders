"""
Klient column (clickable link) in sign.request list view + form view:

  1. x_client_partner_id many2one field (res.partner, stored) — created in a prior
     run (id=30420); this script is idempotent.
  2. List view (id=1311): x_client_partner_id as a clickable link.
     Requires a companion <field column_invisible="True"> alongside the visible
     field — without it Odoo auto-injects one and leaves a <notsentinel> artifact
     that fails _validate_tag_list.
  3. Form view (id=1314): x_client_partner_id before reference_doc (clickable).
  4. Backfill x_client_partner_id on all existing records via Objednatel item.

    python setup_client_partner_field.py          # dry run
    python setup_client_partner_field.py --apply  # apply
"""
import os, sys, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL, DB, USER, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_USER'], os.environ['ODOO_API_KEY']
uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
call = lambda model, method, args, kw=None: m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

apply = '--apply' in sys.argv

SIGN_MODEL_ID      = 665
OBJEDNATEL_ROLE_ID = 15
BASE_LIST_VIEW_ID  = 1311   # sign.request list (js_class="sign_list")
BASE_FORM_VIEW_ID  = 1314   # sign.request form

# ── 1. Verify x_client_partner_id field exists ────────────────────────────────
existing = call('ir.model.fields', 'search_read',
                [[('model_id', '=', SIGN_MODEL_ID), ('name', '=', 'x_client_partner_id')]],
                {'fields': ['id']})
if existing:
    print(f'Field x_client_partner_id: exists (id={existing[0]["id"]})')
else:
    print('Field x_client_partner_id: MISSING — creating...')
    if apply:
        fid = call('ir.model.fields', 'create', [{
            'model_id':          SIGN_MODEL_ID,
            'name':              'x_client_partner_id',
            'field_description': 'Klient',
            'ttype':             'many2one',
            'relation':          'res.partner',
            'store':             True,
            'on_delete':         'set null',
        }])
        print(f'  Created field id={fid}')
    else:
        print('  (dry run)')

# ── 2. List view: x_client_partner_id as clickable link ──────────────────────
# Three hidden rules for the sign_list js_class validation:
#   a) x_client_partner_id needs a column_invisible companion (prevents notsentinel auto-injection)
#   b) x_client_name (char) must also be present in the combined arch alongside
#      the many2one — without it the validator still rejects the partner many2one
#   c) Only fresh create works; write on an existing view fails (Studio mixin path)
LIST_VIEW_NAME = 'LUNASTAV: sign.request list — client partner column'
LIST_ARCH = """<data>
    <xpath expr="//field[@name='reference']" position="after">
        <field name="x_client_name" column_invisible="True"/>
        <field name="x_client_partner_id" string="Kontakt" widget="many2one_avatar_user" readonly="1" optional="show"/>
        <field name="x_client_partner_id" column_invisible="True"/>
    </xpath>
</data>"""

existing_list = call('ir.ui.view', 'search_read',
                     [[('model', '=', 'sign.request'),
                       ('inherit_id', '=', BASE_LIST_VIEW_ID),
                       ('name', 'like', 'LUNASTAV: sign.request list')]],
                     {'fields': ['id', 'name']})

print(f'\nList views found: {[(v["id"], v["name"]) for v in existing_list]}')

if existing_list:
    # Delete all existing variants — write on a Studio-managed view fails, must recreate
    if apply:
        ids = [v['id'] for v in existing_list]
        call('ir.ui.view', 'unlink', [ids])
        print(f'  Deleted existing list view(s): {ids}')
    else:
        print(f'  (dry run — would delete {[v["id"] for v in existing_list]})')

print(f'  Creating list view with many2one + companion...')
if apply:
    vid = call('ir.ui.view', 'create', [{
        'name':       LIST_VIEW_NAME,
        'model':      'sign.request',
        'type':       'list',
        'inherit_id': BASE_LIST_VIEW_ID,
        'arch_base':  LIST_ARCH,
        'priority':   100,
    }])
    print(f'  Created list view id={vid}')
else:
    print('  (dry run)')

# ── 3. Form view: x_client_partner_id before reference_doc ───────────────────
FORM_VIEW_NAME = 'LUNASTAV: sign.request form — client partner link'
FORM_ARCH = """<data>
    <xpath expr="//field[@name='reference_doc']" position="before">
        <field name="x_client_partner_id" string="Klient" readonly="1"/>
    </xpath>
</data>"""

existing_form = call('ir.ui.view', 'search_read',
                     [[('name', '=', FORM_VIEW_NAME), ('model', '=', 'sign.request')]],
                     {'fields': ['id']})
if existing_form:
    print(f'\nForm view "{FORM_VIEW_NAME}": exists (id={existing_form[0]["id"]})')
else:
    print(f'\nForm view "{FORM_VIEW_NAME}": missing — creating...')
    if apply:
        vid = call('ir.ui.view', 'create', [{
            'name':       FORM_VIEW_NAME,
            'model':      'sign.request',
            'type':       'form',
            'inherit_id': BASE_FORM_VIEW_ID,
            'arch_base':  FORM_ARCH,
            'priority':   100,
        }])
        print(f'  Created form view id={vid}')
    else:
        print('  (dry run)')

# ── 4. Backfill x_client_partner_id ──────────────────────────────────────────
if not apply:
    print('\nDry run complete — pass --apply to update views and backfill.')
    sys.exit()

requests = call('sign.request', 'search_read',
                [[['x_client_partner_id', '=', False]]],
                {'fields': ['id', 'reference']})
print(f'\nSign requests without x_client_partner_id: {len(requests)}')

updated = 0
for req in requests:
    items = call('sign.request.item', 'search_read',
                 [[('sign_request_id', '=', req['id']), ('role_id', '=', OBJEDNATEL_ROLE_ID)]],
                 {'fields': ['partner_id']})
    if items and items[0].get('partner_id'):
        pid   = items[0]['partner_id'][0]
        pname = items[0]['partner_id'][1]
        call('sign.request', 'write', [[req['id']], {'x_client_partner_id': pid}])
        print(f"  req {req['id']} ({req['reference']}) → {pid} ({pname})")
        updated += 1
    else:
        print(f"  req {req['id']} ({req['reference']}) — no Objednatel partner, skipped")

print(f'\nBackfilled {updated} records.')
