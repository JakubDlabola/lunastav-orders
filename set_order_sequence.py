"""
One-time script: configure the sale.order sequence to OYYNN+N format.
  Prefix  : P%(y)s   → P26 in 2026, P27 in 2027, …
  Padding : 4         → 0001 … 9999
  Date range reset : enabled (resets to 0001 each new year)
  Current number (2026) : 1555

Run once from the order_service directory:
    python set_order_sequence.py
"""

import os
import xmlrpc.client
from datetime import date

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))

URL     = os.environ['ODOO_URL']
DB      = os.environ['ODOO_DB']
USER    = os.environ['ODOO_USER']
API_KEY = os.environ['ODOO_API_KEY']

common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
uid    = common.authenticate(DB, USER, API_KEY, {})
m      = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

def call(model, method, args, kw=None):
    return m.execute_kw(DB, uid, API_KEY, model, method, args, kw or {})

# Find the sale.order sequence
seq_ids = call('ir.sequence', 'search', [[['code', '=', 'sale.order']]])
if not seq_ids:
    raise SystemExit('Could not find sequence with code=sale.order')

seq_id = seq_ids[0]
print(f'Found sequence id={seq_id}')

# Update prefix, padding, and enable date-range (yearly reset)
call('ir.sequence', 'write', [[seq_id], {
    'prefix':         'P%(y)s',
    'padding':        4,
    'use_date_range': True,
    'number_next':    1509,   # fallback; overridden by date_range below
}])
print('Sequence updated: prefix=P%(y)s, padding=4, use_date_range=True')

# Set or create the 2026 date range and pin next number to 1509
today = date.today()
year_start = f'{today.year}-01-01'
year_end   = f'{today.year}-12-31'

dr_ids = call('ir.sequence.date_range', 'search', [[
    ['sequence_id', '=', seq_id],
    ['date_from',   '=', year_start],
]])
if dr_ids:
    call('ir.sequence.date_range', 'write', [[dr_ids[0]], {'number_next': 1509}])
    print(f'Updated existing date range for {today.year}: number_next=1509')
else:
    new_id = call('ir.sequence.date_range', 'create', [{
        'sequence_id': seq_id,
        'date_from':   year_start,
        'date_to':     year_end,
        'number_next': 1509,
    }])
    print(f'Created date range for {today.year} (id={new_id}): number_next=1509')

print('Done. Next order will be P261509.')
