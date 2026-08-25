"""
Patch the existing 'LUNASTAV: prefix client name on completion certificate' automation
to also handle signed PDF copies on res.partner, crm.lead, and sign.request records
(which Odoo names {reference}.pdf, not Podepsano_…).

    python patch_cert_rename.py          # dry run — prints proposed code & domain
    python patch_cert_rename.py --apply  # writes the patch to Odoo
"""
import os, sys, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL  = os.environ['ODOO_URL']
DB   = os.environ['ODOO_DB']
USER = os.environ['ODOO_USER']
KEY  = os.environ['ODOO_API_KEY']

uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
def call(model, method, args, kw=None):
    return m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

RULE_NAME = 'LUNASTAV: prefix client name on completion certificate'

existing = call('base.automation', 'search_read',
                [[('name', '=', RULE_NAME)]],
                {'fields': ['id', 'action_server_ids']})
if not existing:
    print('Automation not found. Run setup_cert_rename.py --apply first.')
    sys.exit(1)

rule = existing[0]
rule_id = rule['id']
action_id = rule['action_server_ids'][0] if rule['action_server_ids'] else None
print(f'Found automation id={rule_id}, server action id={action_id}')

# ── New domain ────────────────────────────────────────────────────────────────
# Catches:
#   1. "Certificate of completion" anywhere
#   2. "Podepsano_" anywhere (sale.order signed copy)
#   3. Any .pdf on res.partner  (signed copy named {reference}.pdf)
#   4. Any .pdf on crm.lead or sign.request (signed copy)
new_domain = (
    "['|', ('name','ilike','Certificate of completion'),"
    " '|', ('name','ilike','Podepsano_'),"
    " '|', '&', ('res_model','=','res.partner'), ('name','ilike','.pdf'),"
    "      '&', ('res_model','in',['crm.lead','sign.request']), ('name','ilike','.pdf')]"
)

# ── New code ──────────────────────────────────────────────────────────────────
new_code = """\
name = record.name or ''

sign_req = env['sign.request'].browse(False)

if 'Podepsano_' in name:
    ref = name.replace('Podepsano_', '').replace('.pdf', '')
    sign_req = env['sign.request'].search([('reference', '=', ref)], order='id desc', limit=1)
elif 'Certificate of completion' in name:
    if record.res_model == 'sign.request':
        sign_req = env['sign.request'].browse(record.res_id)
    elif record.res_model == 'sale.order':
        order = env['sale.order'].browse(record.res_id)
        sign_req = env['sign.request'].search([('reference', '=', order.name)], order='id desc', limit=1)
    elif record.res_model == 'crm.lead':
        lead = env['crm.lead'].browse(record.res_id)
        for o in lead.order_ids.sorted('id', reverse=True):
            sq = env['sign.request'].search([('reference', '=', o.name)], order='id desc', limit=1)
            if sq:
                sign_req = sq
                break
    elif record.res_model == 'res.partner':
        sign_req = env['sign.request'].search(
            [('request_item_ids.partner_id', '=', record.res_id)],
            order='id desc', limit=1
        )
elif name.endswith('.pdf') and record.res_model in ('sign.request', 'res.partner', 'crm.lead'):
    # Signed PDF copy — Odoo names it {reference}.pdf (or already {client} - {reference}.pdf)
    if record.res_model == 'sign.request':
        sign_req = env['sign.request'].browse(record.res_id)
    elif record.res_model == 'res.partner':
        ref = name.replace('.pdf', '')
        if ref:
            sign_req = env['sign.request'].search([('reference', '=', ref)], order='id desc', limit=1)
        if not sign_req:
            sign_req = env['sign.request'].search(
                [('request_item_ids.partner_id', '=', record.res_id)],
                order='id desc', limit=1
            )
    elif record.res_model == 'crm.lead':
        lead = env['crm.lead'].browse(record.res_id)
        for o in lead.order_ids.sorted('id', reverse=True):
            sq = env['sign.request'].search([('reference', '=', o.name)], order='id desc', limit=1)
            if sq:
                sign_req = sq
                break

if sign_req:
    client_name = ''
    for item in sign_req.request_item_ids:
        if 'objednatel' in (item.role_id.name or '').lower():
            client_name = item.partner_id.name or ''
            break
    if client_name and not name.startswith(client_name):
        record.write({'name': client_name + ' - ' + name})
"""

print(f'\n=== New domain ===\n{new_domain}')
print(f'\n=== New code ===\n{new_code}')

if '--apply' not in sys.argv:
    print('\nDry run — pass --apply to write to Odoo.')
    sys.exit()

call('base.automation', 'write', [[rule_id], {'filter_domain': new_domain}])
if action_id:
    call('ir.actions.server', 'write', [[action_id], {'code': new_code}])
print(f'\nPatched automation id={rule_id} and server action id={action_id}.')
print('New signed PDF copies on partner/CRM/sign.request will now be renamed.')
