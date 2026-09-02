"""
Update automation 58 (LUNASTAV: Dilci podpis) to flip CRM to Podepsáno
when the client (Objednatel) signs, unless already in Vyhráno or Žádost o dotaci schválená.

    python setup_podepsano_stage.py          # dry run — print new code
    python setup_podepsano_stage.py --apply  # write to Odoo
"""
import os, sys, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL, DB, USER, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_USER'], os.environ['ODOO_API_KEY']
uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
call = lambda model, method, args, kw=None: m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

SERVER_ACTION_ID = 1371  # LUNASTAV: Dilci podpis - code

NEW_CODE = """\
req = record.sign_request_id
if req.reference.startswith('P2'):
    order = env['sale.order'].search([('name', '=', req.reference)], limit=1)
    if order:
        lead = order.opportunity_id or None

        # Flip CRM to Podepsano when the client (Objednatel) signs —
        # but skip if already in a later protected stage.
        PODEPSANO_ID     = 6
        PROTECTED_STAGES = {4, 7}  # Vyhrano (Won), Zadost o dotaci schvalena
        if record.role_id and record.role_id.name == 'Objednatel':
            if lead and lead.stage_id.id not in PROTECTED_STAGES:
                lead.sudo().write({'stage_id': PODEPSANO_ID})

        # Chatter note posted to both the sale order and the CRM entry
        if order.state == 'sent':
            signed_names = []
            unsigned_names = []
            for item in req.request_item_ids:
                name = (item.partner_id.name if item.partner_id else None) or item.signer_email or '?'
                if item.state == 'completed':
                    signed_names.append(name)
                else:
                    unsigned_names.append(name)
            if unsigned_names:
                body = ('\\u010c\\u00e1ste\\u010dn\\u00fd podpis p\\u0159ijat. Podeps\\u00e1no: '
                        + ', '.join(signed_names)
                        + '. \\u010cek\\u00e1 na podpis: ' + ', '.join(unsigned_names) + '.')
                order.sudo().message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_note')
                if lead:
                    lead.sudo().message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_note')
"""

print('New code for ir.actions.server id=1371:')
print('─' * 60)
print(NEW_CODE)
print('─' * 60)

if '--apply' not in sys.argv:
    print('Dry run — pass --apply to write to Odoo.')
    sys.exit()

call('ir.actions.server', 'write', [[SERVER_ACTION_ID], {'code': NEW_CODE}])
print('Updated ir.actions.server id=1371.')
