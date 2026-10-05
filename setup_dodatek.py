"""
Dodatek ke smlouvě o dílo (CZ) — Odoo side of the /dodatek-form flow in app.py.

  1. sign.request.x_cz_dodatek_cislo / x_cz_smlouva_cislo (set by app.py on dodatek sign requests only)
  2. ir.sequence 'lunastav.cz.dodatek': DCZ + yy + 4 digits, own counter per year
     (2026 starts at 0200, every later year at 0001 — Odoo creates the yearly range itself)
  3. models x_cz_dodatek / x_cz_dodatek_line + sale.order.x_cz_dodatek_ids, access rights, views,
     menu Prodej > Objednávky > Dodatky
  4. sale.order form: button "Otevřít formulář pro generaci dodatku" (orders with a contract sent or
     signed) and a "Dodatky" tab
  5. sign e-mails: extension views on the CZ templates 1289/1291 — a dodatek row is shown instead of the
     contract text when the request is a dodatek; contracts and SK dodatky render exactly as before
  6. automations: signed dodatek → signed PDF + certificate on the order, client and opportunity, status
     Podepsáno; certificate created later → copied; request cancelled/refused → status Zrušeno.
     The contract automations (56/57/58) only react to P2…/OP-… references, so they ignore dodatky.
Idempotent: re-running updates views/automations/actions and only adds missing fields.

    python setup_dodatek.py           # dry run
    python setup_dodatek.py --apply
"""
import datetime
import os
import sys
import xmlrpc.client

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, '.env'))
load_dotenv(os.path.join(HERE, '..', 'contract_service', '.env'))

URL, DB, USER, KEY = (os.environ[k] for k in ('ODOO_URL', 'ODOO_DB', 'ODOO_USER', 'ODOO_API_KEY'))
SERVICE_KEY = os.environ['SERVICE_KEY']
RAILWAY_URL = 'https://lunastav-orders-production.up.railway.app'
uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
call = lambda model, method, a, kw=None: m.execute_kw(DB, uid, KEY, model, method, a, kw or {})
apply = '--apply' in sys.argv

SEQ_CODE, SEQ_START_2026 = 'lunastav.cz.dodatek', 200
REQUEST_VIEW_ID, COMPLETED_VIEW_ID = 1289, 1291
D, L = 'x_cz_dodatek', 'x_cz_dodatek_line'


def say(msg):
    print(('' if apply else '[dry] ') + msg)


def xmlid(module, name):
    return call('ir.model.data', 'search_read', [[('module', '=', module), ('name', '=', name)]],
                {'fields': ['res_id']})[0]['res_id']


def model_id(name):
    ids = call('ir.model', 'search', [[('model', '=', name)]])
    return ids[0] if ids else None


def ensure_model(name, label, order):
    if model_id(name):
        say(f'model {name}: exists')
        return
    say(f'model {name}: create')
    if apply:
        call('ir.model', 'create', [{
            'name': label, 'model': name, 'state': 'manual', 'order': order,
            'field_id': [(0, 0, {'name': 'x_name', 'field_description': 'Název', 'ttype': 'char',
                                 'state': 'manual', 'required': True})],
        }])


def ensure_field(model, name, label, ttype, **extra):
    if call('ir.model.fields', 'search', [[('model', '=', model), ('name', '=', name)]]):
        return
    say(f'field {model}.{name}: create')
    if apply:
        call('ir.model.fields', 'create', [{'model_id': model_id(model), 'name': name, 'field_description': label,
                                            'ttype': ttype, 'state': 'manual', **extra}])


def ensure_record(model, domain, vals, label):
    ids = call(model, 'search', [domain], {'context': {'active_test': False}})
    say(f'{label}: {"update id=%d" % ids[0] if ids else "create"}')
    if not apply:
        return ids[0] if ids else None
    if ids:
        call(model, 'write', [ids, vals])
        return ids[0]
    return call(model, 'create', [vals])


def field_id(model, name):
    return call('ir.model.fields', 'search', [[('model', '=', model), ('name', '=', name)]])[0]


# ── 1. sign.request fields ───────────────────────────────────────────────────
ensure_field('sign.request', 'x_cz_dodatek_cislo', 'Dodatek č. (CZ)', 'char', store=True)
ensure_field('sign.request', 'x_cz_smlouva_cislo', 'Ke smlouvě o dílo č. (CZ)', 'char', store=True)

# ── 2. sequence ──────────────────────────────────────────────────────────────
seq = call('ir.sequence', 'search_read', [[('code', '=', SEQ_CODE)]], {'fields': ['id']})
seq_id = seq[0]['id'] if seq else None
say(f'sequence {SEQ_CODE}: {"exists id=%d" % seq_id if seq_id else "create"} (DCZ%(range_y)s + 4 digits, yearly)')
if apply and not seq_id:
    seq_id = call('ir.sequence', 'create', [{
        'name': 'LUNASTAV CZ: Dodatek ke smlouvě o dílo', 'code': SEQ_CODE, 'implementation': 'no_gap',
        'prefix': 'DCZ%(range_y)s', 'padding': 4, 'number_increment': 1, 'use_date_range': True,
        'company_id': False}])
if seq_id or not apply:
    year = datetime.date.today().year
    rng = seq_id and call('ir.sequence.date_range', 'search_read', [[
        ('sequence_id', '=', seq_id), ('date_from', '=', f'{year}-01-01')]], {'fields': ['number_next_actual']})
    if rng:
        say(f'sequence {SEQ_CODE}: {year} range exists, next={rng[0]["number_next_actual"]}')
    elif year == 2026:
        say(f'sequence {SEQ_CODE}: create 2026 range starting at {SEQ_START_2026}')
        if apply:
            call('ir.sequence.date_range', 'create', [{'sequence_id': seq_id, 'date_from': '2026-01-01',
                                                       'date_to': '2026-12-31', 'number_next_actual': SEQ_START_2026}])

# ── 3. models + fields ───────────────────────────────────────────────────────
ensure_model(D, 'Dodatek ke smlouvě o dílo', 'id desc')
ensure_model(L, 'Dodatek – položka', 'id')
if model_id(D) and model_id(L):
    ensure_field(D, 'x_order_id', 'Objednávka', 'many2one', relation='sale.order', on_delete='cascade', index=True)
    ensure_field(D, 'x_partner_id', 'Zákazník', 'many2one', relation='res.partner', on_delete='set null')
    ensure_field(D, 'x_lead_id', 'Příležitost', 'many2one', relation='crm.lead', on_delete='set null')
    ensure_field(D, 'x_stav', 'Stav', 'selection', selection_ids=[
        (0, 0, {'value': 'odeslano', 'name': 'Odesláno k podpisu', 'sequence': 1}),
        (0, 0, {'value': 'podepsano', 'name': 'Podepsáno', 'sequence': 2}),
        (0, 0, {'value': 'zruseno', 'name': 'Zrušeno', 'sequence': 3}),
        (0, 0, {'value': 'chyba', 'name': 'Chyba při odeslání', 'sequence': 4}),
    ])
    ensure_field(D, 'x_test', 'Test', 'boolean')
    ensure_field(D, 'x_datum_odeslani', 'Odesláno', 'datetime')
    ensure_field(D, 'x_datum_podpisu', 'Podepsáno', 'datetime')
    ensure_field(D, 'x_smlouva_cislo', 'Ke smlouvě o dílo č.', 'char')
    ensure_field(D, 'x_smlouva_datum', 'Smlouva ze dne', 'date')
    ensure_field(D, 'x_klient_jmeno', 'Objednatel', 'char')
    ensure_field(D, 'x_currency_id', 'Měna', 'many2one', relation='res.currency')
    for name, label in [('x_cena_pred_slevou', 'Cena před slevou'), ('x_sleva', 'Sleva celkem'),
                        ('x_cena_bez_dph', 'Cena bez DPH po slevě'), ('x_dph', 'DPH'),
                        ('x_cena_s_dph', 'Celkem s DPH'), ('x_dotace', 'Dotace NZÚ'),
                        ('x_konecna_cena', 'Konečná cena po odečtení dotace'),
                        ('x_zaloha', 'Záloha'), ('x_doplatek', 'Doplatek')]:
        ensure_field(D, name, label, 'monetary', currency_field='x_currency_id')
    ensure_field(D, 'x_sleva_pct', 'Sleva (%)', 'float')
    ensure_field(D, 'x_zaloha_pct', 'Záloha (%)', 'float')
    ensure_field(D, 'x_termin_zalohy', 'Záloha splatná od', 'char')
    ensure_field(D, 'x_sign_request_id', 'Žádost o podpis', 'many2one', relation='sign.request', on_delete='set null')
    ensure_field(D, 'x_pdf_id', 'PDF dodatku', 'many2one', relation='ir.attachment', on_delete='set null')
    ensure_field(D, 'x_podepsany_pdf_id', 'Podepsaný dodatek', 'many2one', relation='ir.attachment', on_delete='set null')

    ensure_field(L, 'x_dodatek_id', 'Dodatek', 'many2one', relation=D, on_delete='cascade', index=True)
    ensure_field(L, 'x_sequence', 'Pořadí', 'integer')
    ensure_field(L, 'x_kod', 'Kód', 'char')
    ensure_field(L, 'x_mnozstvi', 'Množství', 'float')
    ensure_field(L, 'x_jednotka', 'MJ', 'char')
    ensure_field(L, 'x_currency_id', 'Měna', 'many2one', relation='res.currency')
    ensure_field(L, 'x_jednotkova_cena', 'Cena/MJ bez DPH', 'monetary', currency_field='x_currency_id')
    ensure_field(L, 'x_sleva_pct', 'Sleva (%)', 'float')
    ensure_field(L, 'x_celkem', 'Celkem bez DPH', 'monetary', currency_field='x_currency_id')
    if apply:
        call('ir.model', 'write', [[model_id(L)], {'order': 'x_sequence, id'}])

    ensure_field(D, 'x_line_ids', 'Položky', 'one2many', relation=L, relation_field='x_dodatek_id')
    ensure_field(D, 'x_obchodnik_id', 'Obchodník', 'many2one', relation='res.users',
                 related='x_order_id.user_id', store=True, readonly=True)
    for name, label, ttype, related in [
        ('x_pdf_soubor', 'PDF dodatku', 'binary', 'x_pdf_id.datas'),
        ('x_pdf_nazev', 'PDF dodatku – název', 'char', 'x_pdf_id.name'),
        ('x_podepsany_soubor', 'Podepsaný dodatek', 'binary', 'x_podepsany_pdf_id.datas'),
        ('x_podepsany_nazev', 'Podepsaný dodatek – název', 'char', 'x_podepsany_pdf_id.name'),
    ]:
        ensure_field(D, name, label, ttype, related=related, store=False, readonly=True)
    ensure_field('sale.order', 'x_cz_dodatek_ids', 'Dodatky', 'one2many', relation=D, relation_field='x_order_id')

# ── access ───────────────────────────────────────────────────────────────────
groups = {g: xmlid('sales_team', g) for g in ('group_sale_salesman', 'group_sale_manager')}
for model in (D, L):
    if not model_id(model):
        continue
    for g, unlink in (('group_sale_salesman', False), ('group_sale_manager', True)):
        ensure_record('ir.model.access', [('model_id', '=', model_id(model)), ('group_id', '=', groups[g])],
                      {'name': f'{model} {g}', 'model_id': model_id(model), 'group_id': groups[g],
                       'perm_read': True, 'perm_create': True, 'perm_write': True, 'perm_unlink': unlink},
                      f'access {model}/{g}')

# ── views + menu ─────────────────────────────────────────────────────────────
LIST = """<list string="Dodatky" create="0" decoration-success="x_stav == 'podepsano'" decoration-muted="x_stav == 'zruseno'" decoration-danger="x_stav == 'chyba'">
  <field name="x_name"/>
  <field name="x_stav" widget="badge" decoration-success="x_stav == 'podepsano'" decoration-info="x_stav == 'odeslano'" decoration-danger="x_stav == 'chyba'"/>
  <field name="x_smlouva_cislo"/>
  <field name="x_klient_jmeno"/>
  <field name="x_order_id" optional="hide"/>
  <field name="x_obchodnik_id" optional="show" widget="many2one_avatar_user"/>
  <field name="x_currency_id" column_invisible="1"/>
  <field name="x_cena_s_dph" sum="Celkem"/>
  <field name="x_dotace" optional="hide"/>
  <field name="x_konecna_cena"/>
  <field name="x_datum_odeslani"/>
  <field name="x_datum_podpisu"/>
  <field name="x_test" optional="hide"/>
</list>"""

FORM = """<form string="Dodatek ke smlouvě o dílo" create="0" edit="0">
  <header>
    <field name="x_stav" widget="statusbar" statusbar_visible="odeslano,podepsano"/>
  </header>
  <sheet>
    <div class="oe_title"><h1><field name="x_name" readonly="1"/></h1></div>
    <group>
      <group string="Dodatek">
        <field name="x_smlouva_cislo"/>
        <field name="x_smlouva_datum"/>
        <field name="x_order_id"/>
        <field name="x_lead_id"/>
        <field name="x_datum_odeslani"/>
        <field name="x_datum_podpisu"/>
        <field name="x_test" invisible="not x_test"/>
      </group>
      <group string="Objednatel">
        <field name="x_klient_jmeno"/>
        <field name="x_partner_id"/>
        <field name="x_obchodnik_id" widget="many2one_avatar_user"/>
      </group>
    </group>
    <field name="x_line_ids" nolabel="1">
      <list create="0" delete="0">
        <field name="x_sequence" column_invisible="1"/>
        <field name="x_kod"/>
        <field name="x_name" string="Položka"/>
        <field name="x_mnozstvi"/>
        <field name="x_jednotka"/>
        <field name="x_currency_id" column_invisible="1"/>
        <field name="x_jednotkova_cena"/>
        <field name="x_sleva_pct"/>
        <field name="x_celkem" sum="Celkem"/>
      </list>
    </field>
    <group>
      <group string="Souhrn">
        <field name="x_currency_id" invisible="1"/>
        <field name="x_cena_pred_slevou"/>
        <field name="x_sleva_pct"/>
        <field name="x_sleva"/>
        <field name="x_cena_bez_dph"/>
        <field name="x_dph"/>
        <field name="x_cena_s_dph"/>
        <field name="x_dotace"/>
        <field name="x_konecna_cena"/>
      </group>
      <group string="Platby">
        <field name="x_zaloha_pct"/>
        <field name="x_zaloha"/>
        <field name="x_termin_zalohy"/>
        <field name="x_doplatek"/>
      </group>
    </group>
    <group string="Dokumenty">
      <field name="x_sign_request_id"/>
      <field name="x_pdf_nazev" invisible="1"/>
      <field name="x_podepsany_nazev" invisible="1"/>
      <field name="x_pdf_soubor" filename="x_pdf_nazev"/>
      <field name="x_podepsany_soubor" filename="x_podepsany_nazev" invisible="not x_podepsany_soubor"/>
    </group>
    <notebook>
      <page name="nahled" string="Náhled dodatku">
        <field name="x_podepsany_soubor" widget="pdf_viewer" nolabel="1" invisible="not x_podepsany_soubor"/>
        <field name="x_pdf_soubor" widget="pdf_viewer" nolabel="1" invisible="x_podepsany_soubor"/>
      </page>
    </notebook>
  </sheet>
</form>"""

SEARCH = """<search string="Dodatky">
  <field name="x_name"/>
  <field name="x_klient_jmeno"/>
  <field name="x_smlouva_cislo"/>
  <field name="x_order_id"/>
  <field name="x_obchodnik_id"/>
  <filter name="odeslano" string="Odesláno k podpisu" domain="[('x_stav', '=', 'odeslano')]"/>
  <filter name="podepsano" string="Podepsáno" domain="[('x_stav', '=', 'podepsano')]"/>
  <filter name="zruseno" string="Zrušeno" domain="[('x_stav', '=', 'zruseno')]"/>
  <filter name="chyba" string="Chyba při odeslání" domain="[('x_stav', '=', 'chyba')]"/>
  <separator/>
  <filter name="bez_testu" string="Bez testovacích" domain="[('x_test', '=', False)]"/>
  <separator/>
  <filter name="datum_odeslani" string="Datum odeslání" date="x_datum_odeslani"/>
  <filter name="datum_podpisu" string="Datum podpisu" date="x_datum_podpisu"/>
  <group>
    <filter name="gb_stav" string="Stav" context="{'group_by': 'x_stav'}"/>
    <filter name="gb_obchodnik" string="Obchodník" context="{'group_by': 'x_obchodnik_id'}"/>
    <filter name="gb_odeslani" string="Měsíc odeslání" context="{'group_by': 'x_datum_odeslani:month'}"/>
  </group>
</search>"""

action_id = None
if model_id(D):
    for vtype, arch in (('list', LIST), ('form', FORM), ('search', SEARCH)):
        ensure_record('ir.ui.view', [('model', '=', D), ('type', '=', vtype), ('inherit_id', '=', False)],
                      {'name': f'{D}.{vtype}', 'model': D, 'type': vtype, 'arch_db': arch}, f'view {D}.{vtype}')
    act = ensure_record('ir.actions.act_window', [('name', '=', 'Dodatky'), ('res_model', '=', D)],
                        {'name': 'Dodatky', 'res_model': D, 'view_mode': 'list,form',
                         'context': "{'search_default_bez_testu': 1}",
                         'help': '<p>Dodatky ke smlouvám o dílo vytvořené tlačítkem na objednávce.</p>'},
                        'action Dodatky')
    menu_groups_field = 'group_ids' if 'group_ids' in call('ir.ui.menu', 'fields_get', [], {'attributes': ['type']}) else 'groups_id'
    ensure_record('ir.ui.menu', [('name', '=', 'Dodatky'), ('parent_id', '=', xmlid('sale', 'sale_order_menu'))],
                  {'name': 'Dodatky', 'parent_id': xmlid('sale', 'sale_order_menu'), 'sequence': 3,
                   'action': f'ir.actions.act_window,{act}' if act else False,
                   menu_groups_field: [(6, 0, [groups['group_sale_salesman']])]},
                  'menu Prodej > Objednávky > Dodatky')

# ── 4. button + tab on the order ─────────────────────────────────────────────
BUTTON_CODE = f"""action = {{
    'type': 'ir.actions.act_url',
    'url': '{RAILWAY_URL}/dodatek-form?order_id=%s&key={SERVICE_KEY}' % record.id,
    'target': 'new',
}}"""
so_model = model_id('sale.order')
button_action = ensure_record('ir.actions.server', [('name', '=', 'Otevřít formulář pro generaci dodatku'),
                                                    ('model_id', '=', so_model)],
                              {'name': 'Otevřít formulář pro generaci dodatku', 'model_id': so_model,
                               'state': 'code', 'code': BUTTON_CODE}, 'server action Dodatek button')

if model_id(D) and button_action:
    ORDER_FORM = f"""<data>
  <xpath expr="//button[@name='1338']" position="after">
    <button string="Otevřít formulář pro generaci dodatku" type="action" name="{button_action}"
            invisible="state not in ('sent', 'sale')"/>
  </xpath>
  <xpath expr="//notebook" position="inside">
    <page name="x_cz_dodatky" string="Dodatky" invisible="not x_cz_dodatek_ids">
      <field name="x_cz_dodatek_ids" readonly="1">
        <list decoration-success="x_stav == 'podepsano'" decoration-muted="x_stav == 'zruseno'" decoration-danger="x_stav == 'chyba'">
          <field name="x_name"/>
          <field name="x_stav" widget="badge" decoration-success="x_stav == 'podepsano'" decoration-info="x_stav == 'odeslano'" decoration-danger="x_stav == 'chyba'"/>
          <field name="x_currency_id" column_invisible="1"/>
          <field name="x_cena_s_dph"/>
          <field name="x_dotace"/>
          <field name="x_konecna_cena"/>
          <field name="x_datum_odeslani"/>
          <field name="x_datum_podpisu"/>
          <field name="x_test" optional="hide"/>
        </list>
      </field>
    </page>
  </xpath>
</data>"""
    ensure_record('ir.ui.view', [('name', '=', 'LUNASTAV: sale.order form — Dodatek')],
                  {'name': 'LUNASTAV: sale.order form — Dodatek', 'model': 'sale.order', 'type': 'form',
                   'mode': 'extension', 'inherit_id': xmlid('sale', 'view_order_form'), 'priority': 400,
                   'arch_db': ORDER_FORM},
                  'view sale.order form Dodatek')

# ── 5. sign e-mails ──────────────────────────────────────────────────────────
# record = sign.request.item; the dodatek row replaces the contract text row of the CZ table
REQUEST_ARCH = """<data>
  <xpath expr="//table[1]/tr[1]/td[1]" position="attributes">
    <attribute name="t-if">not record.sign_request_id.x_cz_dodatek_cislo</attribute>
  </xpath>
  <xpath expr="//table[1]/tr[1]" position="after">
    <tr t-if="record.sign_request_id.x_cz_dodatek_cislo"><td valign="top">
        <t t-if="record.role_id.name != 'Objednatel'">
            <p><strong>Zaměřovač:</strong> <t t-out="record.sign_request_id.x_crm_obchodnik or ''"/></p>
        </t>
        <p>Dobrý den, <t t-out="record.partner_id.name"/>,</p>
        <p>žádáme Vás o podpis dodatku č. <strong><t t-out="record.sign_request_id.x_cz_dodatek_cislo"/></strong> ke smlouvě o dílo č. <strong><t t-out="record.sign_request_id.x_cz_smlouva_cislo"/></strong>.</p>
        <p>Pro přístup k dokumentu klikněte na tlačítko níže.</p>
        <p style="color:#888;">Pokud jste dodatek již podepsal(a), nemusíte provádět žádné další kroky.</p>
    </td></tr>
  </xpath>
</data>"""
# record = sign.request
COMPLETED_ARCH = """<data>
  <xpath expr="//table[1]/tr[1]/td[1]" position="attributes">
    <attribute name="t-if">not record.x_cz_dodatek_cislo</attribute>
  </xpath>
  <xpath expr="//table[1]/tr[1]" position="after">
    <tr t-if="record.x_cz_dodatek_cislo"><td valign="top">
        <p>Dobrý den, <t t-out="recipient_name"/>,</p>
        <p>v příloze Vám zasíláme podepsaný dodatek č. <strong><t t-out="record.x_cz_dodatek_cislo"/></strong> ke smlouvě o dílo č. <strong><t t-out="record.x_cz_smlouva_cislo"/></strong>.</p>
        <p>V případě jakýchkoliv dotazů se na nás neváhejte obrátit.</p>
        <p>Děkujeme za Vaši důvěru a těšíme se na spolupráci.</p>
    </td></tr>
  </xpath>
</data>"""
if call('ir.model.fields', 'search', [[('model', '=', 'sign.request'), ('name', '=', 'x_cz_dodatek_cislo')]]):
    for name, parent, arch in (('LUNASTAV CZ: sign e-mail request — dodatek', REQUEST_VIEW_ID, REQUEST_ARCH),
                               ('LUNASTAV CZ: sign e-mail completed — dodatek', COMPLETED_VIEW_ID, COMPLETED_ARCH)):
        ensure_record('ir.ui.view', [('name', '=', name)],
                      {'name': name, 'type': 'qweb', 'mode': 'extension', 'inherit_id': parent,
                       'priority': 210, 'arch_db': arch}, f'view "{name}"')

# ── 6. automations ───────────────────────────────────────────────────────────
TARGETS = """
def _targets(order):
    return [('sale.order', order.id), ('res.partner', order.partner_id.id), ('crm.lead', order.opportunity_id.id)]


def _copy(res_model, res_id, name, datas):
    Att = env['ir.attachment'].sudo()
    att = Att.search([('res_model', '=', res_model), ('res_id', '=', res_id), ('name', '=', name)], limit=1)
    if not att and datas:
        att = Att.create({'name': name, 'res_model': res_model, 'res_id': res_id, 'datas': datas,
                          'mimetype': 'application/pdf'})
    return att


def _dodatek_and_order(req):
    dod = env['x_cz_dodatek'].sudo().search([('x_sign_request_id', '=', req.id)], limit=1)
    order = dod.x_order_id if dod else env['sale.order'].sudo().search([('name', '=', req.x_cz_smlouva_cislo)], limit=1)
    return dod, order
"""

SIGNED_CODE = TARGETS + """
req = record.sign_request_id
if req and req.x_cz_dodatek_cislo and record.file:
    dod, order = _dodatek_and_order(req)
    if order:
        signed = False
        for res_model, res_id in _targets(order):
            if not res_id:
                continue
            fname = ('Podepsano_' + req.reference + '.pdf') if res_model == 'sale.order' else (req.reference + '.pdf')
            att = _copy(res_model, res_id, fname, record.file)
            if res_model == 'sale.order':
                signed = att
        for cert in env['ir.attachment'].sudo().search([('res_model', '=', 'sign.request'), ('res_id', '=', req.id), ('name', 'ilike', 'certificate')]):
            for res_model, res_id in _targets(order):
                if res_id:
                    _copy(res_model, res_id, cert.name, cert.datas)
        if dod and dod.x_stav != 'podepsano':
            dod.write({'x_stav': 'podepsano', 'x_datum_podpisu': datetime.datetime.now(),
                       'x_podepsany_pdf_id': signed.id if signed else False})
        order.sudo().message_post(
            body='Dodatek %s podepsán oběma smluvními stranami. Přidán podepsaný dokument.' % req.reference,
            message_type='comment', subtype_xmlid='mail.mt_note')
"""

CERT_CODE = TARGETS + """
if record.res_model == 'sign.request' and record.datas:
    req = env['sign.request'].sudo().with_context(active_test=False).browse(record.res_id)
    if req.exists() and req.x_cz_dodatek_cislo:
        dod, order = _dodatek_and_order(req)
        if order:
            for res_model, res_id in _targets(order):
                if res_id:
                    _copy(res_model, res_id, record.name, record.datas)
"""

CANCEL_CODE = """
for req in records:
    if req.x_cz_dodatek_cislo and req.state in ('canceled', 'refused'):
        env['x_cz_dodatek'].sudo().search([('x_sign_request_id', '=', req.id), ('x_stav', '=', 'odeslano')]).write({'x_stav': 'zruseno'})
"""

AUTOMATIONS = [
    ('LUNASTAV CZ: Dodatek podepsán', 'sign.completed.document', 'on_write',
     "[('file', '!=', False)]", ('sign.completed.document', 'file'), SIGNED_CODE),
    ('LUNASTAV CZ: Certifikát dodatku', 'ir.attachment', 'on_create',
     "[('res_model', '=', 'sign.request'), ('name', 'ilike', 'certificate')]", None, CERT_CODE),
    ('LUNASTAV CZ: Dodatek zrušen', 'sign.request', 'on_write',
     "[('state', 'in', ['canceled', 'refused'])]", ('sign.request', 'state'), CANCEL_CODE),
]
if model_id(D) and call('ir.model.fields', 'search', [[('model', '=', 'sign.request'), ('name', '=', 'x_cz_dodatek_cislo')]]):
    for name, model, trigger, domain, trig_field, code in AUTOMATIONS:
        mid = model_id(model)
        action_vals = {'name': name + ' - code', 'model_id': mid, 'state': 'code', 'code': code}
        auto_vals = {'name': name, 'model_id': mid, 'trigger': trigger, 'filter_domain': domain, 'active': True}
        if trig_field:
            auto_vals['trigger_field_ids'] = [(6, 0, [field_id(*trig_field)])]
        existing = call('base.automation', 'search_read', [[('name', '=', name)]],
                        {'fields': ['action_server_ids'], 'context': {'active_test': False}})
        say(f'automation "{name}": {"update" if existing else "create"}')
        if not apply:
            continue
        if existing:
            call('ir.actions.server', 'write', [existing[0]['action_server_ids'][:1], action_vals])
            call('base.automation', 'write', [[existing[0]['id']], auto_vals])
        else:
            auto_vals['action_server_ids'] = [(0, 0, action_vals)]
            call('base.automation', 'create', [auto_vals])
elif not apply:
    for name, *_ in AUTOMATIONS:
        say(f'automation "{name}": create (after the models exist)')
