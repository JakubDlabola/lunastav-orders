import base64
import os
import re
import xmlrpc.client

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.responses import HTMLResponse

from contract import generate_contract

load_dotenv()

ODOO_URL     = os.environ['ODOO_URL']
ODOO_DB      = os.environ['ODOO_DB']
ODOO_USER    = os.environ['ODOO_USER']
ODOO_API_KEY = os.environ['ODOO_API_KEY']
SERVICE_KEY  = os.environ['SERVICE_KEY']

app = FastAPI(title='LUNASTAV Order Service')


def odoo_connect():
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_API_KEY, {})
    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    return uid, models


@app.get('/generate', response_class=HTMLResponse)
def generate(order_id: int = Query(...), key: str = Query(...)):
    if key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail='Unauthorized')

    uid, models = odoo_connect()

    def call(model, method, args, kw={}):
        return models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, model, method, args, kw)

    orders = call('sale.order', 'read', [[order_id]], {'fields': [
        'name', 'partner_id', 'amount_total', 'amount_untaxed', 'amount_tax', 'order_line',
        'x_studio_adresa_realizace', 'x_studio_popis_dila',
        'x_studio_zaloha_kc', 'x_studio_termin_zalohy_1',
        'x_studio_doplatek_kc', 'x_studio_termin_dokonceni_1',
        'x_studio_stavebni_pripravenost', 'x_studio_datum_podpisu_smlouvy',
        'x_studio_float_field_45q_1jsh2tmcd', 'x_studio_vyse_dotace_kc',
        'x_studio_cena_po_odecteni_dotace',
    ]})
    if not orders:
        raise HTTPException(status_code=404, detail=f'Order {order_id} not found')
    order = orders[0]

    partner = call('res.partner', 'read', [[order['partner_id'][0]]], {'fields': [
        'name', 'street', 'zip', 'city', 'email', 'phone',
    ]})[0]

    lines = call('sale.order.line', 'read', [order['order_line']], {'fields': [
        'product_id', 'name', 'product_uom_qty', 'product_uom_id',
        'price_unit', 'price_subtotal', 'discount', 'display_type', 'is_downpayment',
    ]})

    pdf_bytes = generate_contract(order, partner, lines)

    filename = f"Smlouva_{order['name']}.pdf"
    call('ir.attachment', 'create', [{
        'name': filename,
        'res_model': 'sale.order',
        'res_id': order_id,
        'type': 'binary',
        'datas': base64.b64encode(pdf_bytes).decode(),
        'mimetype': 'application/pdf',
    }])

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Smlouva vygenerována</title></head>
<body style="font-family:Arial,sans-serif;text-align:center;padding:60px;color:#333;background:#f9f9f9;">
  <div style="background:#fff;border-radius:8px;padding:40px;max-width:480px;margin:auto;box-shadow:0 2px 8px rgba(0,0,0,.1);">
    <div style="font-size:56px;margin-bottom:12px;">✓</div>
    <h2 style="margin:0 0 12px;">Smlouva vygenerována</h2>
    <p>Soubor <strong>{filename}</strong> byl uložen jako příloha objednávky v Odoo.</p>
    <p style="color:#888;font-size:13px;">Vraťte se do Odoo, obnovte stránku a najdete přílohu v přílohách objednávky.</p>
    <button onclick="window.close()"
      style="margin-top:20px;padding:10px 28px;font-size:14px;cursor:pointer;
             background:#c8a840;color:#fff;border:none;border-radius:4px;">
      Zavřít okno
    </button>
  </div>
</body></html>"""


@app.get('/order-form', response_class=HTMLResponse)
def order_form_get(order_id: int = Query(...), key: str = Query(...)):
    if key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail='Unauthorized')

    uid, models = odoo_connect()

    def call(model, method, args, kw={}):
        return models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, model, method, args, kw)

    orders = call('sale.order', 'read', [[order_id]], {'fields': ['name', 'partner_id', 'opportunity_id']})
    if not orders:
        raise HTTPException(status_code=404, detail=f'Objednávka {order_id} nenalezena')
    order = orders[0]

    partner_name = order['partner_id'][1] if order['partner_id'] else 'Neznámý zákazník'

    zastavena_plocha = ''
    remaining_grant_k = '250000'
    if order.get('opportunity_id'):
        leads = call('crm.lead', 'read', [[order['opportunity_id'][0]]],
                     {'fields': ['name', 'x_studio_zastavena_plocha']})
        if leads:
            lead = leads[0]
            zastavena_plocha = lead.get('x_studio_zastavena_plocha') or ''
            m = re.search(r'->\$(\d+)', lead['name'])
            if m:
                remaining_grant_k = str(int(m.group(1)) * 1000)

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Nová objednávka</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: Arial, sans-serif; background: #f5f5f5; color: #333; margin: 0; padding: 20px; }}
    .card {{ background: #fff; border-radius: 8px; padding: 32px; max-width: 580px; margin: auto; box-shadow: 0 2px 8px rgba(0,0,0,.12); }}
    h2 {{ margin: 0 0 4px; font-size: 20px; }}
    .subtitle {{ color: #888; font-size: 13px; margin-bottom: 28px; }}
    .field-label {{ font-weight: bold; font-size: 14px; margin: 20px 0 8px; display: block; }}
    .options {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .opt-wrap {{ position: relative; }}
    .opt-wrap input[type=radio] {{ position: absolute; opacity: 0; width: 0; height: 0; }}
    .opt-btn {{ display: inline-block; padding: 8px 18px; border: 2px solid #ddd; border-radius: 6px; cursor: pointer; font-size: 14px; transition: border-color .15s, background .15s; user-select: none; }}
    .opt-wrap input[type=radio]:checked ~ .opt-btn {{ border-color: #c8a840; background: #fdf8ea; }}
    .opt-btn:hover {{ border-color: #c8a840; }}
    input[type=number] {{ width: 100%; padding: 9px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 15px; margin-top: 2px; }}
    .preview {{ background: #f9f9f9; border: 1px solid #eee; border-radius: 6px; padding: 16px 20px; margin-top: 20px; font-size: 14px; }}
    .preview-row {{ display: flex; justify-content: space-between; margin-bottom: 6px; }}
    .preview-row.grant {{ color: #2a7a3e; font-weight: 500; }}
    .preview-row.total {{ font-weight: bold; font-size: 15px; border-top: 1px solid #ddd; padding-top: 10px; margin-top: 6px; margin-bottom: 0; }}
    .split-note {{ font-size: 12px; color: #888; margin-top: 6px; }}
    button[type=submit] {{ width: 100%; margin-top: 28px; padding: 13px; font-size: 15px; background: #c8a840; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }}
    button[type=submit]:hover {{ background: #b5942e; }}
    button[type=submit]:disabled {{ background: #ccc; cursor: default; }}
    .hidden {{ display: none !important; }}
    .grant-info {{ font-size: 13px; color: #555; margin-top: 4px; }}
  </style>
</head>
<body>
<div class="card">
  <h2>Nová objednávka</h2>
  <div class="subtitle">{partner_name} &middot; {order['name']}</div>

  <form method="post" action="/order-form" id="mainForm">
    <input type="hidden" name="order_id" value="{order_id}">
    <input type="hidden" name="key" value="{key}">
    <input type="hidden" name="eligible_amount" id="inp_eligible">
    <input type="hidden" name="discount_pct" id="inp_discount">

    <span class="field-label">Typ práce</span>
    <div class="options">
      <label class="opt-wrap"><input type="radio" name="work_type" value="roof" onchange="onTypeChange()"><span class="opt-btn">Střecha</span></label>
      <label class="opt-wrap"><input type="radio" name="work_type" value="ceiling" onchange="onTypeChange()"><span class="opt-btn">Strop</span></label>
      <label class="opt-wrap"><input type="radio" name="work_type" value="windows" onchange="onTypeChange()"><span class="opt-btn">Okna</span></label>
    </div>

    <div id="material-section" class="hidden">
      <span class="field-label">Materiál</span>
      <div class="options">
        <label class="opt-wrap"><input type="radio" name="material" value="thermofloc" onchange="calc()"><span class="opt-btn">Thermofloc</span></label>
        <label class="opt-wrap"><input type="radio" name="material" value="supafil" onchange="calc()"><span class="opt-btn">SUPAFIL LOFT PRO</span></label>
        <label class="opt-wrap"><input type="radio" name="material" value="strikana" onchange="calc()"><span class="opt-btn">Stříkaná izolace</span></label>
      </div>
    </div>

    <span class="field-label">Zbývající dotace (Kč)</span>
    <input type="number" id="remaining_grant_k" value="{remaining_grant_k}" min="0" step="1000" oninput="calc()" placeholder="bez omezení">
    <div class="grant-info" style="margin-top:4px;">Výchozí 250 000 Kč; prázdné pole = bez omezení</div>

    <div id="qty-m2-section" class="hidden">
      <span class="field-label">Zastavěná plocha (m²)</span>
      <input type="number" name="qty_m2" id="qty_m2" value="{zastavena_plocha}" min="1" step="1" oninput="calc()">
    </div>

    <div id="qty-windows-section" class="hidden">
      <span class="field-label">Počet oken</span>
      <input type="number" name="qty_windows" id="qty_windows" value="1" min="1" step="1" oninput="calc()">
    </div>

    <div id="preview" class="preview hidden">
      <div class="preview-row"><span>Cena bez slevy</span><span id="pv-base">—</span></div>
      <div class="preview-row grant"><span>Způsobilé náklady (dotace)</span><span id="pv-eligible">—</span></div>
      <div class="preview-row"><span>Sleva</span><span id="pv-disc">—</span></div>
      <div class="preview-row total"><span>Celkem k úhradě</span><span id="pv-total">—</span></div>
      <div class="preview-row hidden" id="pv-zaloha-row"><span id="pv-zaloha-label">Záloha</span><span id="pv-zaloha">—</span></div>
      <div class="preview-row hidden" id="pv-doplatek-row"><span id="pv-doplatek-label">Doplatek</span><span id="pv-doplatek">—</span></div>
    </div>

    <div id="split-section" class="hidden">
      <span class="field-label">Záloha / doplatek</span>
      <div class="options" id="split-opts">
        <label class="opt-wrap"><input type="radio" name="split" value="60-40"><span class="opt-btn">60 / 40</span></label>
        <label class="opt-wrap"><input type="radio" name="split" value="20-80"><span class="opt-btn">20 / 80</span></label>
        <label class="opt-wrap"><input type="radio" name="split" value="0-100"><span class="opt-btn">Bez zálohy</span></label>
      </div>
      <div class="split-note" id="split-note"></div>
    </div>

    <button type="submit" id="submitBtn" disabled>Vytvořit objednávku</button>
  </form>
</div>
<script>
const GRANT_RATE = {{roof: 2000, ceiling: 750, windows: 8000}};
const LISTED    = {{roof: 2002, ceiling: 751, windows: 8000}};
const SYM = 250;

function getRemK() {{
  const v = parseFloat(document.getElementById('remaining_grant_k').value);
  return isNaN(v) ? null : v;
}}

function fmt(n) {{
  return new Intl.NumberFormat('cs-CZ').format(Math.round(n)) + ' Kč';
}}

function getType() {{ return document.querySelector('input[name=work_type]:checked')?.value; }}
function getMat()  {{ return document.querySelector('input[name=material]:checked')?.value; }}
function getSplit(){{ return document.querySelector('input[name=split]:checked')?.value; }}

function onTypeChange() {{
  const t = getType();
  document.getElementById('material-section').classList.toggle('hidden', t === 'windows');
  document.getElementById('qty-m2-section').classList.toggle('hidden', t === 'windows');
  document.getElementById('qty-windows-section').classList.toggle('hidden', t !== 'windows');
  document.getElementById('split-section').classList.remove('hidden');

  const isWin = t === 'windows';
  const opts = document.querySelectorAll('#split-opts label');
  opts.forEach(l => l.classList.toggle('hidden', isWin));
  document.getElementById('split-note').textContent = isWin ? 'Pro okna je vždy záloha 80 %, doplatek 20 %.' : '';
  calc();
}}

function calc() {{
  const t = getType();
  if (!t) return;

  const qty = t === 'windows'
    ? (parseFloat(document.getElementById('qty_windows').value) || 0)
    : (parseFloat(document.getElementById('qty_m2').value) || 0);

  if (!qty) {{ document.getElementById('preview').classList.add('hidden'); return; }}

  const listed_total = LISTED[t] * qty;
  const formula_total = GRANT_RATE[t] * qty;
  const remK = getRemK();
  const eligible = remK !== null ? Math.min(formula_total, remK) : formula_total;
  const disc = Math.max(0, (1 - eligible / listed_total)) * 100;
  const total = eligible + SYM;

  document.getElementById('pv-base').textContent = fmt(listed_total);
  document.getElementById('pv-eligible').textContent = fmt(eligible);
  document.getElementById('pv-disc').textContent = disc.toFixed(2) + ' %';
  document.getElementById('pv-total').textContent = fmt(total);

  const splitVal = t === 'windows' ? '80-20' : (getSplit() || '');
  if (splitVal) {{
    const [a, b] = splitVal.split('-').map(Number);
    document.getElementById('pv-zaloha-label').textContent = `Záloha (${{a}} %)`;
    document.getElementById('pv-doplatek-label').textContent = `Doplatek (${{b}} %)`;
    document.getElementById('pv-zaloha').textContent = fmt(Math.round(total * a / 100));
    document.getElementById('pv-doplatek').textContent = fmt(Math.round(total * b / 100));
    document.getElementById('pv-zaloha-row').classList.remove('hidden');
    document.getElementById('pv-doplatek-row').classList.remove('hidden');
  }} else {{
    document.getElementById('pv-zaloha-row').classList.add('hidden');
    document.getElementById('pv-doplatek-row').classList.add('hidden');
  }}

  document.getElementById('preview').classList.remove('hidden');

  document.getElementById('inp_eligible').value = eligible;
  document.getElementById('inp_discount').value = disc.toFixed(4);

  checkSubmit();
}}

function checkSubmit() {{
  const t = getType();
  const split = t === 'windows' ? '80-20' : getSplit();
  const mat = t === 'windows' ? true : getMat();
  const eligible = document.getElementById('inp_eligible').value;
  document.getElementById('submitBtn').disabled = !(t && mat && split && eligible);
}}

document.getElementById('mainForm').addEventListener('change', () => {{ calc(); checkSubmit(); }});
</script>
</body>
</html>"""


@app.post('/order-form', response_class=HTMLResponse)
def order_form_post(
    order_id: int = Form(...),
    key: str = Form(...),
    work_type: str = Form(...),
    material: str = Form(None),
    qty_m2: str = Form(''),
    qty_windows: str = Form(''),
    eligible_amount: float = Form(...),
    discount_pct: float = Form(...),
    split: str = Form(None),
):
    if key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail='Unauthorized')

    uid, models = odoo_connect()

    def call(model, method, args, kw={}):
        return models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, model, method, args, kw)

    if work_type == 'windows':
        ref = '4000'
        qty = float(qty_windows or 1)
        split_pct = (80, 20)
    else:
        suffix = 'A' if work_type == 'roof' else 'B'
        ref_map = {'thermofloc': '3000', 'supafil': '3100', 'strikana': '3200'}
        ref = ref_map[material] + suffix
        qty = float(qty_m2 or 0)
        if split:
            a, b = split.split('-')
            split_pct = (int(a), int(b))
        else:
            split_pct = (60, 40)

    prods = call('product.product', 'search_read',
                 [[['default_code', '=', ref]]],
                 {'fields': ['id', 'name'], 'limit': 1})
    if not prods:
        raise HTTPException(status_code=400, detail=f'Produkt [{ref}] nenalezen v Odoo')
    product_id = prods[0]['id']

    sym_prods = call('product.product', 'search_read',
                     [[['default_code', '=', 'PRACE']]],
                     {'fields': ['id'], 'limit': 1})

    listed = {'roof': 2002, 'ceiling': 751, 'windows': 8000}[work_type]

    order_lines = [
        (5, 0, 0),
        (0, 0, {
            'product_id': product_id,
            'product_uom_qty': qty,
            'price_unit': listed,
            'discount': round(discount_pct, 4),
        }),
    ]
    if sym_prods:
        order_lines.append((0, 0, {
            'product_id': sym_prods[0]['id'],
            'product_uom_qty': 1,
            'price_unit': 250,
            'discount': 0,
        }))

    total = eligible_amount + 250
    zaloha   = round(total * split_pct[0] / 100)
    doplatek = round(total * split_pct[1] / 100)

    call('sale.order', 'write', [[order_id], {
        'order_line': order_lines,
        'x_studio_zaloha_kc': zaloha,
        'x_studio_doplatek_kc': doplatek,
        'x_studio_vyse_dotace_kc': eligible_amount,
    }])

    def fmt_czk(v):
        return f"{round(v):,}".replace(',', ' ') + ' Kč'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Objednávka vytvořena</title></head>
<body style="font-family:Arial,sans-serif;text-align:center;padding:60px;color:#333;background:#f9f9f9;">
  <div style="background:#fff;border-radius:8px;padding:40px;max-width:480px;margin:auto;box-shadow:0 2px 8px rgba(0,0,0,.1);">
    <div style="font-size:56px;margin-bottom:12px;">&#10003;</div>
    <h2 style="margin:0 0 16px;">Objednávka vytvořena</h2>
    <table style="width:100%;font-size:14px;border-collapse:collapse;text-align:left;">
      <tr><td style="padding:6px 0;color:#888;">Způsobilé náklady</td><td style="text-align:right;font-weight:bold;">{fmt_czk(eligible_amount)}</td></tr>
      <tr><td style="padding:6px 0;color:#888;">Celkem k úhradě</td><td style="text-align:right;font-weight:bold;">{fmt_czk(total)}</td></tr>
      <tr><td style="padding:6px 0;color:#888;">Záloha ({split_pct[0]} %)</td><td style="text-align:right;">{fmt_czk(zaloha)}</td></tr>
      <tr><td style="padding:6px 0;color:#888;">Doplatek ({split_pct[1]} %)</td><td style="text-align:right;">{fmt_czk(doplatek)}</td></tr>
    </table>
    <p style="color:#888;font-size:13px;margin-top:20px;">Vraťte se do Odoo a obnovte stránku objednávky.</p>
    <button onclick="window.close()"
      style="margin-top:12px;padding:10px 28px;font-size:14px;cursor:pointer;
             background:#c8a840;color:#fff;border:none;border-radius:4px;">
      Zavřít okno
    </button>
  </div>
</body></html>"""


@app.get('/health')
def health():
    return {'status': 'ok'}
