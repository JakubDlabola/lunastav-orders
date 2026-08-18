"""
Probe what fields and attachments are available on a completed sign.request.
Run this after at least one signing has been completed, to verify field names
before running copy_signed_docs.py.

    python probe_sign_fields.py
"""
import os, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL, DB, USER, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_USER'], os.environ['ODOO_API_KEY']
uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

def call(model, method, args, kw=None):
    return m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

# Find most recent completed sign.request
recs = call('sign.request', 'search_read', [[('state', '=', 'signed')]],
            {'fields': ['id', 'reference', 'state', 'create_date'],
             'order': 'id desc', 'limit': 3})
print(f'Found {len(recs)} signed sign.request records:')
for r in recs:
    print(f'  id={r["id"]}  reference={r["reference"]}  date={r["create_date"]}')

if not recs:
    print('No completed sign requests found.')
    raise SystemExit(0)

rid = recs[0]['id']
print(f'\nProbing sign.request id={rid}...')

# 1. All fields available on the model
all_fields = call('sign.request', 'fields_get', [], {'attributes': ['string', 'type']})
pdf_fields = {k: v for k, v in all_fields.items()
              if 'pdf' in k.lower() or 'document' in k.lower() or 'attach' in k.lower()
              or 'certif' in k.lower() or 'completed' in k.lower()}
print('\nRelevant fields on sign.request:')
for k, v in sorted(pdf_fields.items()):
    print(f'  {k:40s}  [{v["type"]:12s}]  {v["string"]}')

# 2. Try reading specific binary fields
candidate_fields = [f for f, v in pdf_fields.items() if v['type'] in ('binary', 'many2many', 'one2many')]
print(f'\nReading candidate binary/relation fields: {candidate_fields}')
if candidate_fields:
    vals = call('sign.request', 'read', [[rid], candidate_fields])
    if vals:
        for f in candidate_fields:
            val = vals[0].get(f)
            if val is False or val is None:
                print(f'  {f}: (empty)')
            elif isinstance(val, (list, tuple)):
                print(f'  {f}: {val} (relation IDs)')
            else:
                print(f'  {f}: {str(val)[:80]}... ({len(val)} chars base64)')

# 3. ir.attachment records on this sign.request
atts = call('ir.attachment', 'search_read',
            [[('res_model', '=', 'sign.request'), ('res_id', '=', rid)]],
            {'fields': ['id', 'name', 'mimetype', 'file_size', 'create_date'],
             'order': 'id asc'})
print(f'\nir.attachment records on sign.request id={rid} ({len(atts)} found):')
for a in atts:
    print(f'  id={a["id"]:5d}  {a["name"]:50s}  {a["mimetype"]:25s}  {a["file_size"]} bytes')

if not atts:
    print('  (none)')

print('\nProbe complete.')
