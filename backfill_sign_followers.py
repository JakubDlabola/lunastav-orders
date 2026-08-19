"""
Retroactively subscribe each sale order's salesperson as a follower on their
sign.request, so Sign/User salespeople can see existing signing documents.

    python backfill_sign_followers.py          # dry run (prints what would happen)
    python backfill_sign_followers.py --apply  # actually subscribes
"""
import os, sys, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL, DB, USER, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_USER'], os.environ['ODOO_API_KEY']
uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

def call(model, method, args, kw=None):
    return m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

apply = '--apply' in sys.argv

requests = call('sign.request', 'search_read',
                [[('reference', 'like', 'P2'), ('state', '!=', 'canceled')]],
                {'fields': ['id', 'reference', 'message_partner_ids'], 'order': 'id asc'})

print(f'Found {len(requests)} sign request(s)  (dry run — pass --apply to commit)\n' if not apply
      else f'Found {len(requests)} sign request(s)  — applying\n')

subscribed = skipped = missing = 0

for req in requests:
    ref = req['reference']
    rid = req['id']

    orders = call('sale.order', 'search_read', [[('name', '=', ref)]],
                  {'fields': ['id', 'user_id'], 'limit': 1})
    if not orders or not orders[0].get('user_id'):
        print(f'  {ref}: no order or no salesperson — skip')
        missing += 1
        continue

    order      = orders[0]
    sp_user_id = order['user_id'][0]
    sp_name    = order['user_id'][1]

    users = call('res.users', 'read', [[sp_user_id]], {'fields': ['partner_id']})
    if not users:
        print(f'  {ref}: user {sp_user_id} not found — skip')
        missing += 1
        continue

    sp_partner_id = users[0]['partner_id'][0]

    if sp_partner_id in req['message_partner_ids']:
        print(f'  {ref}: {sp_name} already a follower — skip')
        skipped += 1
        continue

    if apply:
        call('sign.request', 'message_subscribe', [[rid], [sp_partner_id]])

    print(f'  {ref}: {"subscribed" if apply else "would subscribe"} {sp_name} (partner {sp_partner_id})')
    subscribed += 1

print(f'\n{"Applied" if apply else "Would apply"}: {subscribed}  |  already present: {skipped}  |  no salesperson: {missing}')
