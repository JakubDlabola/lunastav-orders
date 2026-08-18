"""
Copy signed contracts and completion certificates from completed sign.request
records to the related sale.order, res.partner, and crm.lead.

Run manually after a signing completes, or schedule as needed.
    python copy_signed_docs.py              # process last 30 days
    python copy_signed_docs.py 90           # process last N days

Run probe_sign_fields.py first if you want to inspect what Odoo stores.
"""
import os, sys, xmlrpc.client
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL, DB, USER, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_USER'], os.environ['ODOO_API_KEY']
uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

def call(model, method, args, kw=None):
    return m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

def attach(name, data_b64, mimetype, res_model, res_id):
    """Attach a file to a record, skipping if already present (by name)."""
    existing = call('ir.attachment', 'search_read',
                    [[('res_model', '=', res_model), ('res_id', '=', res_id),
                      ('name', '=', name)]],
                    {'fields': ['id'], 'limit': 1})
    if existing:
        print(f'    skip (already present): {res_model} #{res_id} ← {name}')
        return
    call('ir.attachment', 'create', [{
        'name': name, 'res_model': res_model, 'res_id': res_id,
        'type': 'binary', 'datas': data_b64, 'mimetype': mimetype,
    }])
    print(f'    attached: {res_model} #{res_id} ← {name}')

# ─── Discover which binary fields exist on sign.request ─────────────────────
_sr_fields = call('sign.request', 'fields_get', [], {'attributes': ['type']})
_BINARY_CANDIDATES = [f for f in ('completed_document', 'completion_pdf', 'signed_pdf')
                      if f in _sr_fields and _sr_fields[f]['type'] == 'binary']

days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

requests = call('sign.request', 'search_read',
                [[('state', '=', 'signed'), ('create_date', '>=', since)]],
                {'fields': ['id', 'reference', 'create_date'], 'order': 'id asc'})

print(f'Found {len(requests)} completed sign request(s) since {since}')
if _BINARY_CANDIDATES:
    print(f'Binary fields to check: {_BINARY_CANDIDATES}')
print()

for req in requests:
    ref = req['reference']
    rid = req['id']
    print(f'{ref}  (sign.request id={rid}  signed {req["create_date"]})')

    orders = call('sale.order', 'search_read', [[('name', '=', ref)]],
                  {'fields': ['id', 'partner_id', 'opportunity_id']})
    if not orders:
        print(f'  WARNING: no sale.order found for reference "{ref}", skipping\n')
        continue

    order      = orders[0]
    order_id   = order['id']
    partner_id = order['partner_id'][0]     if order.get('partner_id')     else None
    lead_id    = order['opportunity_id'][0] if order.get('opportunity_id') else None

    docs = []  # [(filename, base64_data, mimetype), ...]

    # 1. ir.attachment records linked to the sign.request (most reliable)
    atts = call('ir.attachment', 'search_read',
                [[('res_model', '=', 'sign.request'), ('res_id', '=', rid),
                  ('mimetype', 'ilike', 'pdf')]],
                {'fields': ['name', 'datas', 'mimetype'], 'order': 'id asc'})
    for a in atts:
        if a.get('datas'):
            docs.append((a['name'], a['datas'], a['mimetype']))

    # 2. Binary fields on the sign.request record itself (field names vary by version)
    if _BINARY_CANDIDATES:
        vals = call('sign.request', 'read', [[rid], _BINARY_CANDIDATES])
        if vals:
            v = vals[0]
            label_map = {
                'completed_document': f'{ref}_podepsana_smlouva.pdf',
                'signed_pdf':         f'{ref}_podepsana_smlouva.pdf',
                'completion_pdf':     f'{ref}_certifikat_dokonceni.pdf',
            }
            for field, fname in label_map.items():
                data = v.get(field)
                if data and data is not False:
                    # Skip if already captured from ir.attachment (same content)
                    if not any(d[0] == fname for d in docs):
                        docs.append((fname, data, 'application/pdf'))

    if not docs:
        print('  No PDF documents found — run probe_sign_fields.py to investigate.\n')
        continue

    print(f'  {len(docs)} document(s) to distribute:')
    for name, data, mime in docs:
        attach(name, data, mime, 'sale.order', order_id)
        if partner_id:
            attach(name, data, mime, 'res.partner', partner_id)
        if lead_id:
            attach(name, data, mime, 'crm.lead', lead_id)
    print()

print('Done.')
