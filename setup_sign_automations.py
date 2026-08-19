"""
Create Odoo automations:
1. sign.completed.document on_write (file field) : upload signed PDF, move order to 'sale', win CRM
   Odoo writes the signed PDF in a separate UPDATE after the INSERT, so on_write is the right trigger.
2. sign.request.item state -> completed : post partial-sign chatter on order
"""
import os, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL, DB, USER, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_USER'], os.environ['ODOO_API_KEY']
uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
def call(model, method, args, kw=None):
    return m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

def model_id(name):
    ids = call('ir.model', 'search', [[['model', '=', name]]])
    return ids[0]

sign_comp_doc_mid = model_id('sign.completed.document')
sign_req_mid      = model_id('sign.request')
sign_item_mid     = model_id('sign.request.item')

# field id for sign.completed.document.file (trigger fires when signed PDF is written)
file_field_id = call('ir.model.fields', 'search',
    [[['model', '=', 'sign.completed.document'], ['name', '=', 'file']]])[0]
print(f'sign.completed.document.file field id: {file_field_id}')

# Remove old automations if re-running
for name in ['LUNASTAV: Smlouva podepsana', 'LUNASTAV: Dilci podpis']:
    old = call('base.automation', 'search', [[['name', '=', name]]])
    if old:
        call('base.automation', 'unlink', [old])
        print(f'Removed: {name}')

# ── Automation 1: sign.completed.document.file written ───────────────────────
# Fires when Odoo writes the signed PDF binary — record.file is guaranteed
# available. Certificate is searched separately via ir.attachment on the request.
# order.state == 'sent' guard prevents re-processing on subsequent writes.
CODE_SIGNED = (
    "req = record.sign_request_id\n"
    "if req.reference.startswith('P2'):\n"
    "    order = env['sale.order'].search([('name', '=', req.reference)], limit=1)\n"
    "    if order and order.state == 'sent':\n"
    "        order.with_context(tracking_disable=True).sudo().write({'state': 'sale'})\n"
    "        targets = [\n"
    "            ('sale.order',  order.id),\n"
    "            ('res.partner', order.partner_id.id if order.partner_id else None),\n"
    "            ('crm.lead',    order.opportunity_id.id if order.opportunity_id else None),\n"
    "        ]\n"
    # Signed PDF → all three targets using record.file directly (always available here)
    "        if record.file:\n"
    "            for res_model, res_id in targets:\n"
    "                if not res_id:\n"
    "                    continue\n"
    "                fname = ('Podepsano_' + req.reference + '.pdf') if res_model == 'sale.order' else (req.reference + '.pdf')\n"
    "                if not env['ir.attachment'].sudo().search([('res_model', '=', res_model), ('res_id', '=', res_id), ('name', '=', fname)], limit=1):\n"
    "                    env['ir.attachment'].sudo().create({'name': fname, 'res_model': res_model, 'res_id': res_id, 'datas': record.file, 'mimetype': 'application/pdf'})\n"
    # Certificate → all three targets (searched by name on the sign.request ir.attachments)
    "        certs = env['ir.attachment'].sudo().search([('res_model', '=', 'sign.request'), ('res_id', '=', req.id), ('name', 'ilike', 'certificate')])\n"
    "        for cert in certs:\n"
    "            if not cert.datas:\n"
    "                continue\n"
    "            for res_model, res_id in targets:\n"
    "                if not res_id:\n"
    "                    continue\n"
    "                if not env['ir.attachment'].sudo().search([('res_model', '=', res_model), ('res_id', '=', res_id), ('name', '=', cert.name)], limit=1):\n"
    "                    env['ir.attachment'].sudo().create({'name': cert.name, 'res_model': res_model, 'res_id': res_id, 'datas': cert.datas, 'mimetype': 'application/pdf'})\n"
    "        order.sudo().message_post(\n"
    "            body='Smlouva podepsána oběma stranami. Přidán podepsaný dokument.',\n"
    "            message_type='comment',\n"
    "            subtype_xmlid='mail.mt_note',\n"
    "        )\n"
    "        if order.opportunity_id:\n"
    "            try:\n"
    "                order.opportunity_id.sudo().action_set_won()\n"
    "            except Exception:\n"
    "                won = env['crm.stage'].search([('is_won', '=', True)], limit=1)\n"
    "                if won:\n"
    "                    order.opportunity_id.sudo().write({'stage_id': won.id, 'probability': 100})\n"
)

auto1 = call('base.automation', 'create', [{
    'name': 'LUNASTAV: Smlouva podepsana',
    'model_id': sign_comp_doc_mid,
    'trigger': 'on_write',
    'trigger_field_ids': [(4, file_field_id)],
    'filter_domain': "[('file', '!=', False)]",
    'action_server_ids': [(0, 0, {
        'name': 'LUNASTAV: Smlouva podepsana - code',
        'model_id': sign_comp_doc_mid,
        'state': 'code',
        'code': CODE_SIGNED,
    })],
    'active': True,
}])
print(f'Created automation 1 (on_write sign.completed.document.file): id={auto1}')

# ── Automation 2: sign.request.item state -> completed ─────────────────────
# trg_selection_field_id=2168 (sign.request.item.state = 'completed')
# Guard: order.state == 'sent' prevents stale firings.
CODE_ITEM = (
    "req = record.sign_request_id\n"
    "if req.reference.startswith('P2'):\n"
    "    order = env['sale.order'].search([('name', '=', req.reference)], limit=1)\n"
    "    if order and order.state == 'sent':\n"
    "        signed_names = []\n"
    "        unsigned_names = []\n"
    "        for item in req.request_item_ids:\n"
    "            name = (item.partner_id.name if item.partner_id else None) or item.signer_email or '?'\n"
    "            if item.state == 'completed':\n"
    "                signed_names.append(name)\n"
    "            else:\n"
    "                unsigned_names.append(name)\n"
    "        if unsigned_names:\n"
    "            order.sudo().message_post(\n"
    "                body='Částečný podpis přijat. Podepsáno: ' + ', '.join(signed_names) + '. Čeká na podpis: ' + ', '.join(unsigned_names) + '.',\n"
    "                message_type='comment',\n"
    "                subtype_xmlid='mail.mt_note',\n"
    "            )\n"
)

auto2 = call('base.automation', 'create', [{
    'name': 'LUNASTAV: Dilci podpis',
    'model_id': sign_item_mid,
    'trigger': 'on_state_set',
    'trg_selection_field_id': 2168,
    'action_server_ids': [(0, 0, {
        'name': 'LUNASTAV: Dilci podpis - code',
        'model_id': sign_item_mid,
        'state': 'code',
        'code': CODE_ITEM,
    })],
    'active': True,
}])
print(f'Created automation 2 (partial sign): id={auto2}')
print('Done.')
