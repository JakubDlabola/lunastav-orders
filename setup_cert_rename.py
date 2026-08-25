"""
Create a base.automation that prefixes "Certificate of completion" attachments
on sign.request with the client (Objednatel) partner name.

    python setup_cert_rename.py          # dry run
    python setup_cert_rename.py --apply  # create the automation in Odoo
    python setup_cert_rename.py --remove # delete it
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

apply  = '--apply'  in sys.argv
remove = '--remove' in sys.argv

existing = call('base.automation', 'search_read',
                [[('name', '=', RULE_NAME)]],
                {'fields': ['id']})

if remove:
    if existing:
        call('base.automation', 'unlink', [[existing[0]['id']]])
        print(f'Removed automation: {RULE_NAME}')
    else:
        print('Automation not found.')
    sys.exit()

if existing:
    print(f'Automation already exists (id={existing[0]["id"]}).')
    print('Run with --remove first to recreate it.')
    sys.exit()

# Look up ir.attachment model id
att_model = call('ir.model', 'search_read',
                 [[('model', '=', 'ir.attachment')]],
                 {'fields': ['id']})[0]
att_model_id = att_model['id']

# Python code run when a new ir.attachment is created that matches our domain
code = """\
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

print(f'Model id (ir.attachment): {att_model_id}')
print(f'Rule name: {RULE_NAME}')
print(f'Code:\n{code}')

if not apply:
    print('\nDry run — pass --apply to create in Odoo.')
    sys.exit()

# Create the server action
action_id = call('ir.actions.server', 'create', [{
    'name':     RULE_NAME,
    'model_id': att_model_id,
    'state':    'code',
    'code':     code,
}])

# Create the automation rule
rule_id = call('base.automation', 'create', [{
    'name':              RULE_NAME,
    'model_id':          att_model_id,
    'trigger':           'on_create',
    'filter_domain':     "['|', ('name','ilike','Certificate of completion'), '|', ('name','ilike','Podepsano_'), '|', '&', ('res_model','=','res.partner'), ('name','ilike','.pdf'), '&', ('res_model','in',['crm.lead','sign.request']), ('name','ilike','.pdf')]",
    'action_server_ids': [(4, action_id)],
    'active':            True,
}])

print(f'Created automation id={rule_id} with server action id={action_id}')
print('New certificates will be prefixed with the client name automatically.')
