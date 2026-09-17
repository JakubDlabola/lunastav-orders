"""
Backfill orders_log.jsonl from Odoo for orders created before the log feature existed.

Identifies past orders by the presence of a Smlouva_*.pdf attachment, then reconstructs
as much of the form state as possible from the order lines.

    python backfill_log.py [--log-file /path/to/orders_log.jsonl] [--apply]

Without --apply: dry run (prints what would be added, writes nothing).
"""
import os, sys, json, uuid, re, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL = os.environ['ODOO_URL']
DB  = os.environ['ODOO_DB']
KEY = os.environ['ODOO_API_KEY']
USR = os.environ['ODOO_USER']

uid   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USR, KEY, {})
model = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
call  = lambda m, method, args, kw=None: model.execute_kw(DB, uid, KEY, m, method, args, kw or {})

# ── CLI args ─────────────────────────────────────────────────────────────────
apply_flag = '--apply' in sys.argv
log_file = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--log-file'), None)
if not log_file:
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'orders_log.jsonl')

print(f'Log file : {log_file}')
print(f'Dry run  : {not apply_flag}')

# ── Load existing log_ids so we don't duplicate ───────────────────────────────
existing_order_ids: set = set()
if os.path.exists(log_file):
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                e = json.loads(line)
                if e.get('order_id'):
                    existing_order_ids.add(int(e['order_id']))
            except Exception:
                pass
print(f'Already logged order IDs: {len(existing_order_ids)}')

# ── Find orders with Smlouva_*.pdf attachment ─────────────────────────────────
attachments = call('ir.attachment', 'search_read',
    [[['res_model', '=', 'sale.order'], ['name', 'like', 'Smlouva_'], ['mimetype', '=', 'application/pdf']]],
    {'fields': ['res_id', 'name', 'create_date'], 'limit': 2000})

order_ids = list({a['res_id'] for a in attachments if a['res_id'] not in existing_order_ids})
print(f'Orders with Smlouva_*.pdf (new to log): {len(order_ids)}')
if not order_ids:
    print('Nothing to backfill.')
    sys.exit(0)

# ── Read order metadata ───────────────────────────────────────────────────────
orders = call('sale.order', 'read', [order_ids], {
    'fields': ['name', 'partner_id', 'opportunity_id', 'user_id', 'date_order',
               'order_line'],
})

# ── Attachment date lookup (best proxy for when the contract was generated) ───
att_date_by_order: dict = {}
for a in attachments:
    oid = a['res_id']
    if oid not in att_date_by_order:
        att_date_by_order[oid] = a.get('create_date', '')[:19].replace(' ', 'T')

# ── Product code → field mappings ─────────────────────────────────────────────
REF_MAP_INV = {'3000': 'thermofloc', '3100': 'supafil', '3200': 'strikana'}

def code_to_form(product_code: str, qty: float, form: dict):
    code = product_code.upper()
    # Insulation products
    for prefix, material in REF_MAP_INV.items():
        if code.startswith(prefix):
            suffix = code[len(prefix):]
            if suffix == 'A':
                form['has_roof']      = True
                form['material_roof'] = material
                form['qty_m2_roof']   = str(qty)
            elif suffix == 'C':
                form['has_sikminy']      = True
                form['material_sikminy'] = material
                form['qty_m2_sikminy']   = str(qty)
            elif suffix == 'B':
                form['has_ceiling']      = True
                form['material_ceiling'] = material
                form['qty_m2_ceiling']   = str(qty)
            return
    # Doors
    if code == '4100':
        form['has_doors']    = True
        form['qty_m2_doors'] = str(qty)
        return
    # Windows
    if code == '4000A':
        form['has_windows'] = True
        form['qty_win_a']   = str(qty)
        return
    if code == '4000B':
        form['has_windows'] = True
        form['qty_win_b']   = str(qty)
        return
    if code == '4000C':
        form['has_windows'] = True
        form['qty_win_c']   = str(qty)
        return
    # Blinds / nets
    if code == '4001A':
        form['has_blinds'] = True
        form['qty_blinds'] = str(qty)
        return
    if code == '4001B':
        form['has_nets'] = True
        form['qty_nets'] = str(qty)
        return
    # Pochozi (ceiling add-ons)
    if code == '5100':
        form['qty_5100'] = str(qty)
        return
    if code == '5101':
        form['qty_5101'] = str(qty)
        return
    # Extras (roof)
    if code in ('5000A', '5000B', '5000C'):
        form[f'extra_{code.lower()}'] = True
        return

# ── CRM lead lookup (batch) ───────────────────────────────────────────────────
opp_ids = [o['opportunity_id'][0] for o in orders if o.get('opportunity_id')]
leads_map: dict = {}
if opp_ids:
    leads = call('crm.lead', 'read', [list(set(opp_ids))],
                 {'fields': ['id', 'name', 'user_id']})
    leads_map = {l['id']: l for l in leads}

# ── Order lines lookup (batch) ────────────────────────────────────────────────
all_line_ids = []
for o in orders:
    all_line_ids.extend(o.get('order_line', []))
lines = call('sale.order.line', 'read', [all_line_ids],
             {'fields': ['order_id', 'product_id', 'product_uom_qty']})
lines_by_order: dict = {}
for ln in lines:
    oid = ln['order_id'][0]
    lines_by_order.setdefault(oid, []).append(ln)

# ── Process each order ────────────────────────────────────────────────────────
entries = []
for o in orders:
    oid    = o['id']
    lead   = leads_map.get(o['opportunity_id'][0]) if o.get('opportunity_id') else None
    opp_name = (lead.get('name') or '') if lead else ''
    sp_name  = ((lead.get('user_id') or [None, ''])[1] or '') if lead else \
               ((o.get('user_id') or [None, ''])[1] or '')

    form: dict = {}
    for ln in lines_by_order.get(oid, []):
        if ln.get('product_id'):
            code = ln['product_id'][1] if isinstance(ln['product_id'], list) else ''
            # product_id is [id, display_name]; extract default_code via search if needed
            # For now extract code from display_name heuristic like "[3000A] ..."
            m = re.match(r'\[([^\]]+)\]', code)
            if m:
                code_to_form(m.group(1), ln.get('product_uom_qty', 0), form)

    # Fetch actual default_code for products (more reliable than display name)
    prod_ids = [ln['product_id'][0] for ln in lines_by_order.get(oid, []) if ln.get('product_id')]
    if prod_ids:
        prods = call('product.product', 'read', [list(set(prod_ids))],
                     {'fields': ['id', 'default_code']})
        prod_code_map = {p['id']: (p.get('default_code') or '') for p in prods}
        form = {}  # reset and rebuild from reliable codes
        for ln in lines_by_order.get(oid, []):
            if ln.get('product_id'):
                pid = ln['product_id'][0]
                code = prod_code_map.get(pid, '')
                if code:
                    code_to_form(code, ln.get('product_uom_qty', 0), form)

    created_at = att_date_by_order.get(oid, (o.get('date_order') or '')[:19].replace(' ', 'T'))
    partner_name = (o['partner_id'][1] if o.get('partner_id') else '') or ''

    entry = {
        'log_id':           uuid.uuid4().hex,
        'order_id':         oid,
        'order_name':       o.get('name', ''),
        'partner_name':     partner_name,
        'opportunity_name': opp_name,
        'salesperson':      sp_name,
        'created_at':       created_at,
        'form':             form,
        '_backfilled':      True,
    }
    entries.append(entry)
    flag = '[WOULD ADD]' if not apply_flag else '[ADDING]'
    print(f'{flag} {o["name"]:12s}  {partner_name[:30]:30s}  {created_at[:10]}  form_keys={list(form.keys())}')

if apply_flag:
    with open(log_file, 'a', encoding='utf-8') as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    print(f'\nWrote {len(entries)} entries to {log_file}')
else:
    print(f'\nDry run complete — {len(entries)} entries would be added. Pass --apply to write.')
