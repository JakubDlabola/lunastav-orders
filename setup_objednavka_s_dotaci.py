"""
"Objednávka s dotací?" (S dotací / Bez dotace) on the opportunity and on the order.

- crm.lead.x_objednavka_s_dotaci: read-only, tracked; set when an order of the opportunity is signed
  (S dotací if any signed order has Výše dotace > 0, else Bez dotace). Shown in place of the old
  "Realizace:" field (x_studio_realizace is only hidden, its data stays). CZ only.
- sale.order.x_objednavka_s_dotaci: read-only, tracked; written by the order form (grant dialog) and,
  if still empty, on signing by Výše dotace.
- automation on sale.order: state → sale (Objednávka podepsána).
- --backfill: CZ opportunities with a signed order, and CZ orders (grant > 0 → S dotací, no grant but
  with lines → Bez dotace, empty orders stay empty); without chatter entries.
Undo: archive the two views and the automation (the fields can stay).

    python setup_objednavka_s_dotaci.py                       # dry run
    python setup_objednavka_s_dotaci.py --apply [--backfill]
"""
import os
import sys
import xmlrpc.client

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, '..', 'contract_service', '.env'))
URL, DB, USER, KEY = (os.environ[k] for k in ('ODOO_URL', 'ODOO_DB', 'ODOO_USER', 'ODOO_API_KEY'))
uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
call = lambda model, method, a, kw=None: m.execute_kw(DB, uid, KEY, model, method, a, kw or {})
apply, backfill = '--apply' in sys.argv, '--backfill' in sys.argv
dry = '' if apply else '[dry] '

FIELD = 'x_objednavka_s_dotaci'
LABEL = 'Objednávka s dotací?'
VALUES = [('s_dotaci', 'S dotací'), ('bez_dotace', 'Bez dotace')]
SK_COMPANY = 2
CRM_STUDIO_VIEW = 4338  # "Odoo Studio: crm.lead.form customization" — holds Realizace:; not edited
NO_TRACK = {'context': {'tracking_disable': True, 'mail_notrack': True, 'mail_auto_subscribe_no_notify': True}}


def ensure_field(model):
    if call('ir.model.fields', 'search', [[('model', '=', model), ('name', '=', FIELD)]]):
        print(f'field {model}.{FIELD}: exists')
        return
    print(f'{dry}field {model}.{FIELD}: create')
    if apply:
        call('ir.model.fields', 'create', [{
            'model_id': call('ir.model', 'search', [[('model', '=', model)]])[0], 'name': FIELD,
            'field_description': LABEL, 'ttype': 'selection', 'state': 'manual', 'copied': False, 'tracking': 100,
            'selection_ids': [(0, 0, {'value': v, 'name': n, 'sequence': i}) for i, (v, n) in enumerate(VALUES)]}])


def ensure_view(name, model, inherit_id, arch):
    vals = {'name': name, 'model': model, 'type': 'form', 'mode': 'extension', 'inherit_id': inherit_id,
            'priority': 500, 'arch_db': arch}
    existing = call('ir.ui.view', 'search', [[('name', '=', name)]], {'context': {'active_test': False}})
    print(f'{dry}view "{name}": {"update" if existing else "create"}')
    if apply:
        if existing:
            call('ir.ui.view', 'write', [existing, {**vals, 'active': True}])
        else:
            existing = [call('ir.ui.view', 'create', [vals])]
        print('  view id', existing[0])


ensure_field('crm.lead')
ensure_field('sale.order')

ensure_view('LUNASTAV: crm.lead form — objednávka s dotací', 'crm.lead', CRM_STUDIO_VIEW, f"""<data>
  <xpath expr="//field[@name='x_studio_realizace']" position="after">
    <field name="{FIELD}" readonly="1" invisible="company_id == {SK_COMPANY}"/>
  </xpath>
  <xpath expr="//field[@name='x_studio_realizace']" position="attributes">
    <attribute name="invisible">1</attribute>
  </xpath>
</data>""")
sale_form = call('ir.model.data', 'search_read', [[('module', '=', 'sale'), ('name', '=', 'view_order_form')]],
                 {'fields': ['res_id']})[0]['res_id']
ensure_view('LUNASTAV: sale.order form — objednávka s dotací', 'sale.order', sale_form, f"""<data>
  <xpath expr="//field[@name='partner_id']" position="after">
    <field name="{FIELD}" readonly="1" invisible="company_id == {SK_COMPANY}"/>
  </xpath>
</data>""")

AUTOMATION = 'LUNASTAV CZ: Objednávka s dotací? při podpisu objednávky'
CODE = f"""# order signed (Objednávka podepsána): opportunity = S dotací if any of its signed orders has a grant
for order in records:
    if order.company_id.id == {SK_COMPANY}:
        continue
    if not order.{FIELD}:
        order.write({{'{FIELD}': 's_dotaci' if order.x_studio_vyse_dotace_kc else 'bez_dotace'}})
    lead = order.opportunity_id
    if lead:
        signed = lead.order_ids.filtered(lambda o: o.state == 'sale')
        val = 's_dotaci' if any(o.x_studio_vyse_dotace_kc for o in signed) else 'bez_dotace'
        if lead.{FIELD} != val:
            lead.write({{'{FIELD}': val}})
"""
existing = call('base.automation', 'search', [[('name', '=', AUTOMATION)]], {'context': {'active_test': False}})
print(f'{dry}automation "{AUTOMATION}": {"update" if existing else "create"}')
if apply:
    so_model = call('ir.model', 'search', [[('model', '=', 'sale.order')]])[0]
    state_field = call('ir.model.fields', 'search', [[('model', '=', 'sale.order'), ('name', '=', 'state')]])[0]
    action_vals = {'name': AUTOMATION, 'model_id': so_model, 'state': 'code', 'code': CODE}
    vals = {'name': AUTOMATION, 'model_id': so_model, 'trigger': 'on_write', 'active': True,
            'trigger_field_ids': [(6, 0, [state_field])],
            'filter_pre_domain': "[('state', '!=', 'sale')]", 'filter_domain': "[('state', '=', 'sale')]"}
    if existing:
        auto = call('base.automation', 'read', [existing, ['action_server_ids']])[0]
        call('ir.actions.server', 'write', [auto['action_server_ids'], action_vals])
        call('base.automation', 'write', [existing, vals])
    else:
        existing = [call('base.automation', 'create', [{**vals, 'action_server_ids': [(0, 0, action_vals)]}])]
    print('  automation id', existing[0])

if backfill or not apply:
    orders = call('sale.order', 'search_read', [[('company_id', '!=', SK_COMPANY)]],
                  {'fields': ['state', 'x_studio_vyse_dotace_kc', 'order_line', 'opportunity_id'],
                   'context': {'active_test': False}})
    by_val = {'s_dotaci': [], 'bez_dotace': []}
    for o in orders:
        if o['x_studio_vyse_dotace_kc']:
            by_val['s_dotaci'].append(o['id'])
        elif o['order_line']:
            by_val['bez_dotace'].append(o['id'])
    leads = {}
    for o in orders:
        if o['state'] == 'sale' and o['opportunity_id']:
            lid = o['opportunity_id'][0]
            leads[lid] = leads.get(lid, False) or bool(o['x_studio_vyse_dotace_kc'])
    lead_val = {'s_dotaci': [l for l, g in leads.items() if g], 'bez_dotace': [l for l, g in leads.items() if not g]}
    print(f'{dry}backfill orders: S dotací {len(by_val["s_dotaci"])}, Bez dotace {len(by_val["bez_dotace"])}, '
          f'empty {len(orders) - len(by_val["s_dotaci"]) - len(by_val["bez_dotace"])}')
    print(f'{dry}backfill opportunities: S dotací {len(lead_val["s_dotaci"])}, Bez dotace {len(lead_val["bez_dotace"])}')
    if apply and backfill:
        for model, groups in (('sale.order', by_val), ('crm.lead', lead_val)):
            for val, ids in groups.items():
                for i in range(0, len(ids), 200):
                    call(model, 'write', [ids[i:i + 200], {FIELD: val}], NO_TRACK)
        print('backfill done')
