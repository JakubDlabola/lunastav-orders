import base64
import os
import random
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

    odoo_order_url = f'{ODOO_URL}/odoo/sales/{order_id}'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Smlouva vygenerována</title></head>
<body style="font-family:Arial,sans-serif;text-align:center;padding:60px;color:#333;background:#f9f9f9;">
  <div style="background:#fff;border-radius:8px;padding:40px;max-width:480px;margin:auto;box-shadow:0 2px 8px rgba(0,0,0,.1);">
    <div style="font-size:56px;margin-bottom:12px;">&#10003;</div>
    <h2 style="margin:0 0 12px;">Smlouva vygenerována</h2>
    <p style="color:#888;font-size:13px;">Přesměrování zpět do Odoo&hellip;</p>
  </div>
  <script>
    try {{
      if (window.opener) {{
        window.opener.location.href = '{odoo_order_url}';
        window.close();
      }} else {{
        window.location.href = '{odoo_order_url}';
      }}
    }} catch(e) {{
      window.location.href = '{odoo_order_url}';
    }}
  </script>
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
    .opt-wrap input[type=radio], .opt-wrap input[type=checkbox] {{ position: absolute; opacity: 0; width: 0; height: 0; }}
    .opt-btn {{ display: inline-block; padding: 8px 18px; border: 2px solid #ddd; border-radius: 6px; cursor: pointer; font-size: 14px; transition: border-color .15s, background .15s; user-select: none; }}
    .opt-wrap input[type=radio]:checked ~ .opt-btn, .opt-wrap input[type=checkbox]:checked ~ .opt-btn {{ border-color: #c8a840; background: #fdf8ea; }}
    .opt-btn:hover {{ border-color: #c8a840; }}
    .type-section {{ border-left: 3px solid #c8a840; padding-left: 14px; margin-top: 16px; }}
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
    <input type="hidden" name="eligible_roof"        id="inp_elig_roof"    value="0">
    <input type="hidden" name="eligible_ceiling"     id="inp_elig_ceiling" value="0">
    <input type="hidden" name="eligible_windows"     id="inp_elig_windows" value="0">
    <input type="hidden" name="discount_pct_roof"    id="inp_disc_roof"    value="0">
    <input type="hidden" name="discount_pct_ceiling" id="inp_disc_ceiling" value="0">
    <input type="hidden" name="discount_pct_windows" id="inp_disc_windows" value="0">
    <input type="hidden" name="grant_amount"         id="inp_grant_amount" value="0">

    <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;padding:12px 16px;background:#f0f8f0;border:1px solid #c8e6c9;border-radius:6px;">
      <input type="checkbox" id="grant_enabled" checked onchange="calc()" style="width:18px;height:18px;cursor:pointer;accent-color:#2a7a3e;">
      <label for="grant_enabled" style="font-size:14px;cursor:pointer;font-weight:500;">Zákazník čerpá dotaci NZÚ</label>
    </div>

    <span class="field-label">Typ práce</span>
    <div class="options">
      <label class="opt-wrap"><input type="checkbox" name="has_roof"    id="chk_roof"    onchange="onTypesChange()"><span class="opt-btn">Střecha</span></label>
      <label class="opt-wrap"><input type="checkbox" name="has_ceiling" id="chk_ceiling" onchange="onTypesChange()"><span class="opt-btn">Strop</span></label>
      <label class="opt-wrap"><input type="checkbox" name="has_windows" id="chk_windows" onchange="onTypesChange()"><span class="opt-btn">Okna</span></label>
    </div>

    <div id="roof-section" class="hidden type-section">
      <span class="field-label">Materiál — Střecha</span>
      <div class="options">
        <label class="opt-wrap"><input type="radio" name="material_roof" value="thermofloc" onchange="calc()"><span class="opt-btn">Thermofloc</span></label>
        <label class="opt-wrap"><input type="radio" name="material_roof" value="supafil" onchange="calc()"><span class="opt-btn">SUPAFIL LOFT PRO</span></label>
        <label class="opt-wrap"><input type="radio" name="material_roof" value="strikana" onchange="calc()"><span class="opt-btn">Stříkaná izolace</span></label>
      </div>
      <span class="field-label">Plocha střechy (m²)</span>
      <input type="number" name="qty_m2_roof" id="qty_m2_roof" value="{zastavena_plocha}" min="1" step="1" oninput="calc()">
      <span class="field-label">Doplňkové práce</span>
      <div class="options">
        <label class="opt-wrap"><input type="checkbox" name="extra_5000a" value="1"><span class="opt-btn">Otevření a zavření falcované střechy</span></label>
        <label class="opt-wrap"><input type="checkbox" name="extra_5000b" value="1"><span class="opt-btn">Otevření a zavření PVC folie</span></label>
      </div>
    </div>

    <div id="ceiling-section" class="hidden type-section">
      <span class="field-label">Materiál — Strop</span>
      <div class="options">
        <label class="opt-wrap"><input type="radio" name="material_ceiling" value="thermofloc" onchange="calc()"><span class="opt-btn">Thermofloc</span></label>
        <label class="opt-wrap"><input type="radio" name="material_ceiling" value="supafil" onchange="calc()"><span class="opt-btn">SUPAFIL LOFT PRO</span></label>
        <label class="opt-wrap"><input type="radio" name="material_ceiling" value="strikana" onchange="calc()"><span class="opt-btn">Stříkaná izolace</span></label>
      </div>
      <span class="field-label">Plocha stropu (m²)</span>
      <input type="number" name="qty_m2_ceiling" id="qty_m2_ceiling" value="{zastavena_plocha}" min="1" step="1" oninput="calc()">
      <span class="field-label">Kostrukce pochozí plochy (m²)</span>
      <input type="number" name="qty_5100" id="qty_5100" min="0" step="1" placeholder="nezahrnout">
      <span class="field-label">Konstrukce revizní lávky (m)</span>
      <input type="number" name="qty_5101" id="qty_5101" min="0" step="1" placeholder="nezahrnout">
    </div>

    <div id="windows-section" class="hidden type-section">
      <span class="field-label">Počet oken</span>
      <input type="number" name="qty_windows" id="qty_windows" value="1" min="1" step="1" oninput="calc()">
    </div>

    <span class="field-label">Zbývající dotace (Kč)</span>
    <input type="number" id="remaining_grant_k" value="{remaining_grant_k}" min="0" step="1000" oninput="calc()" placeholder="bez omezení">

    <div id="preview" class="preview hidden">
      <div class="preview-row"><span>Cena bez slevy</span><span id="pv-base">—</span></div>
      <div class="preview-row hidden" id="pv-rate-row"><span id="pv-rate-label">Efektivní cena / m²</span><span id="pv-rate">—</span></div>
      <div class="preview-row hidden" id="pv-disc-row"><span>Sleva</span><span id="pv-disc">—</span></div>
      <div class="preview-row grant hidden" id="pv-grant-row"><span>Náklady pokryté dotací</span><span id="pv-grant">—</span></div>
      <div class="preview-row hidden" id="pv-client-row"><span>Náklady k uhrazení</span><span id="pv-client">—</span></div>
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

function getRemK()  {{ const v = parseFloat(document.getElementById('remaining_grant_k').value); return isNaN(v) ? null : v; }}
function hasGrant() {{ return document.getElementById('grant_enabled').checked; }}
function getSplit() {{ return document.querySelector('input[name=split]:checked')?.value; }}
function fmt(n)     {{ return new Intl.NumberFormat('cs-CZ').format(Math.round(n)) + ' K\u010d'; }}

function roofMinRate(qty) {{
  if (qty <= 50) return 1000;
  if (qty >= 100) return 750;
  return 1000 + (750 - 1000) / (100 - 50) * (qty - 50);
}}

function onTypesChange() {{
  const hasRoof = document.getElementById('chk_roof').checked;
  const hasCeil = document.getElementById('chk_ceiling').checked;
  const hasWin  = document.getElementById('chk_windows').checked;
  document.getElementById('roof-section').classList.toggle('hidden', !hasRoof);
  document.getElementById('ceiling-section').classList.toggle('hidden', !hasCeil);
  document.getElementById('windows-section').classList.toggle('hidden', !hasWin);
  document.getElementById('split-section').classList.toggle('hidden', !(hasRoof || hasCeil || hasWin));
  const winOnly = hasWin && !hasRoof && !hasCeil;
  document.querySelectorAll('#split-opts label').forEach(l => l.classList.toggle('hidden', winOnly));
  document.getElementById('split-note').textContent = winOnly ? 'Pro okna je vždy záloha 80 %, doplatek 20 %.' : '';
  calc();
}}

function calc() {{
  const hasRoof = document.getElementById('chk_roof').checked;
  const hasCeil = document.getElementById('chk_ceiling').checked;
  const hasWin  = document.getElementById('chk_windows').checked;
  if (!hasRoof && !hasCeil && !hasWin) {{ document.getElementById('preview').classList.add('hidden'); checkSubmit(); return; }}

  const qRoof = hasRoof ? (parseFloat(document.getElementById('qty_m2_roof').value)    || 0) : 0;
  const qCeil = hasCeil ? (parseFloat(document.getElementById('qty_m2_ceiling').value) || 0) : 0;
  const qWin  = hasWin  ? (parseFloat(document.getElementById('qty_windows').value)    || 0) : 0;

  const lRoof = LISTED.roof * qRoof, lCeil = LISTED.ceiling * qCeil, lWin = LISTED.windows * qWin;
  const lTotal = lRoof + lCeil + lWin;
  if (lTotal === 0) {{ document.getElementById('preview').classList.add('hidden'); checkSubmit(); return; }}

  const fRoof = GRANT_RATE.roof * qRoof, fCeil = GRANT_RATE.ceiling * qCeil, fWin = GRANT_RATE.windows * qWin;
  const fTot = fRoof + fCeil + fWin;

  const DOPRAVA = 250;
  let eRoof = 0, eCeil = 0, eWin = 0, grantReceived = 0, floorHit = false;
  if (!hasGrant()) {{
    eRoof = hasRoof ? Math.round(roofMinRate(qRoof) * qRoof) : 0;
    eCeil = hasCeil ? GRANT_RATE.ceiling * qCeil : 0;
    eWin  = hasWin  ? GRANT_RATE.windows * qWin  : 0;
    grantReceived = 0;
  }} else {{
    const remK = getRemK();
    grantReceived = remK !== null ? Math.min(fTot, remK) : fTot;
    if (fTot > 0) {{ eRoof = grantReceived * fRoof / fTot; eCeil = grantReceived * fCeil / fTot; eWin = grantReceived * fWin / fTot; }}
    if (hasRoof && qRoof > 0) {{
      const minR = Math.round(roofMinRate(qRoof) * qRoof);
      if (eRoof < minR) {{ eRoof = minR; floorHit = true; }}
    }}
    eRoof = Math.min(eRoof, lRoof); eCeil = Math.min(eCeil, lCeil); eWin = Math.min(eWin, lWin);
  }}

  const eTotal = eRoof + eCeil + eWin;
  const grantUsed = Math.min(grantReceived, eTotal);
  const clientPays = Math.max(DOPRAVA, eTotal + DOPRAVA - grantReceived);
  const dRoof  = lRoof  > 0 ? Math.max(0, (1 - eRoof / lRoof))  * 100 : 0;
  const dCeil  = lCeil  > 0 ? Math.max(0, (1 - eCeil / lCeil))  * 100 : 0;
  const dWin   = lWin   > 0 ? Math.max(0, (1 - eWin  / lWin))   * 100 : 0;

  document.getElementById('inp_elig_roof').value    = Math.round(eRoof);
  document.getElementById('inp_elig_ceiling').value = Math.round(eCeil);
  document.getElementById('inp_elig_windows').value = Math.round(eWin);
  document.getElementById('inp_disc_roof').value    = dRoof.toFixed(4);
  document.getElementById('inp_disc_ceiling').value = dCeil.toFixed(4);
  document.getElementById('inp_disc_windows').value = dWin.toFixed(4);
  document.getElementById('inp_grant_amount').value = Math.round(grantUsed);

  const dTotal = lTotal > 0 ? Math.max(0, (1 - eTotal / lTotal)) * 100 : 0;
  document.getElementById('pv-disc').textContent = dTotal.toFixed(1) + ' %';
  document.getElementById('pv-disc-row').classList.toggle('hidden', dTotal < 0.5);

  const grantOn = hasGrant();
  document.getElementById('pv-base').textContent  = fmt(lTotal);
  document.getElementById('pv-total').textContent = fmt(eTotal + DOPRAVA);
  document.getElementById('pv-grant-row').classList.toggle('hidden', !grantOn);
  document.getElementById('pv-client-row').classList.toggle('hidden', !grantOn);
  if (grantOn) {{
    document.getElementById('pv-grant').textContent  = fmt(grantReceived);
    document.getElementById('pv-client').textContent = fmt(clientPays);
  }}

  const rateEl = document.getElementById('pv-rate-row');
  const singleInsul = (hasRoof !== hasCeil) && !hasWin;
  if (singleInsul) {{
    const qty = hasRoof ? qRoof : qCeil, elig = hasRoof ? eRoof : eCeil;
    const rate = qty > 0 ? Math.round(elig / qty) : 0;
    let rateText = new Intl.NumberFormat('cs-CZ').format(rate) + ' K\u010d/m\u00b2';
    if (floorHit) {{ rateText += ' \u2014 minim\u00e1ln\u00ed cena'; rateEl.style.color = '#c8670a'; rateEl.style.fontWeight = '600'; }}
    else {{ rateEl.style.color = ''; rateEl.style.fontWeight = ''; }}
    document.getElementById('pv-rate-label').textContent = 'Efektivn\u00ed cena / m\u00b2';
    document.getElementById('pv-rate').textContent = rateText;
    rateEl.classList.remove('hidden');
  }} else {{ rateEl.classList.add('hidden'); }}

  const winOnly  = hasWin && !hasRoof && !hasCeil;
  const splitVal = winOnly ? '80-20' : (getSplit() || '');
  if (splitVal) {{
    const [a, b] = splitVal.split('-').map(Number);
    document.getElementById('pv-zaloha-label').textContent   = 'Z\u00e1loha (' + a + ' %)';
    document.getElementById('pv-doplatek-label').textContent = 'Doplatek (' + b + ' %)';
    document.getElementById('pv-zaloha').textContent         = fmt(Math.round((eTotal + DOPRAVA) * a / 100));
    document.getElementById('pv-doplatek').textContent       = fmt(Math.round((eTotal + DOPRAVA) * b / 100));
    document.getElementById('pv-zaloha-row').classList.remove('hidden');
    document.getElementById('pv-doplatek-row').classList.remove('hidden');
  }} else {{
    document.getElementById('pv-zaloha-row').classList.add('hidden');
    document.getElementById('pv-doplatek-row').classList.add('hidden');
  }}

  document.getElementById('preview').classList.remove('hidden');
  checkSubmit();
}}

function checkSubmit() {{
  const hasRoof = document.getElementById('chk_roof').checked;
  const hasCeil = document.getElementById('chk_ceiling').checked;
  const hasWin  = document.getElementById('chk_windows').checked;
  if (!hasRoof && !hasCeil && !hasWin) {{ document.getElementById('submitBtn').disabled = true; return; }}
  const matRoof = hasRoof ? document.querySelector('input[name=material_roof]:checked')?.value    : 'ok';
  const matCeil = hasCeil ? document.querySelector('input[name=material_ceiling]:checked')?.value : 'ok';
  const qRoof = hasRoof ? (parseFloat(document.getElementById('qty_m2_roof').value)    || 0) : 1;
  const qCeil = hasCeil ? (parseFloat(document.getElementById('qty_m2_ceiling').value) || 0) : 1;
  const qWin  = hasWin  ? (parseFloat(document.getElementById('qty_windows').value)    || 0) : 1;
  const winOnly = hasWin && !hasRoof && !hasCeil;
  const split = winOnly ? '80-20' : getSplit();
  const eTotal = parseFloat(document.getElementById('inp_elig_roof').value    || 0)
               + parseFloat(document.getElementById('inp_elig_ceiling').value || 0)
               + parseFloat(document.getElementById('inp_elig_windows').value || 0);
  document.getElementById('submitBtn').disabled = !(
    (!hasRoof || (matRoof && qRoof > 0)) &&
    (!hasCeil || (matCeil && qCeil > 0)) &&
    (!hasWin  || qWin > 0) && split && eTotal > 0
  );
}}

document.getElementById('mainForm').addEventListener('change', () => {{ calc(); checkSubmit(); }});
</script>
</body>
</html>"""


@app.post('/order-form', response_class=HTMLResponse)
def order_form_post(
    order_id: int = Form(...),
    key: str = Form(...),
    has_roof: str = Form(''),
    has_ceiling: str = Form(''),
    has_windows: str = Form(''),
    material_roof: str = Form(None),
    material_ceiling: str = Form(None),
    qty_m2_roof: str = Form(''),
    qty_m2_ceiling: str = Form(''),
    qty_windows: str = Form(''),
    eligible_roof: float = Form(0),
    eligible_ceiling: float = Form(0),
    eligible_windows: float = Form(0),
    discount_pct_roof: float = Form(0),
    discount_pct_ceiling: float = Form(0),
    discount_pct_windows: float = Form(0),
    grant_amount: float = Form(0),
    split: str = Form(None),
    extra_5000a: str = Form(''),
    extra_5000b: str = Form(''),
    qty_5100: str = Form(''),
    qty_5101: str = Form(''),
):
    if key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail='Unauthorized')

    uid, models = odoo_connect()

    def call(model, method, args, kw={}):
        return models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, model, method, args, kw)

    TAX_RATE = 1.12
    LISTED = {'roof': 2002, 'ceiling': 751, 'windows': 8000}
    REF_MAP = {'thermofloc': '3000', 'supafil': '3100', 'strikana': '3200'}

    active_types = []
    if has_roof:    active_types.append('roof')
    if has_ceiling: active_types.append('ceiling')
    if has_windows: active_types.append('windows')

    if not active_types:
        raise HTTPException(status_code=400, detail='Zadejte alespoň jeden typ práce')

    # Determine split percentages
    win_only = active_types == ['windows']
    if win_only:
        split_pct = (80, 20)
    elif split:
        a, b = split.split('-')
        split_pct = (int(a), int(b))
    else:
        split_pct = (60, 40)

    doprava_prods = call('product.product', 'search_read',
                         [[['default_code', '=', 'D']]],
                         {'fields': ['id'], 'limit': 1})
    doprava_price = random.randint(200, 300)

    order_lines = [(5, 0, 0)]

    COSMETIC_DISC = 3.0  # always show 3% discount; price_unit inflated to compensate

    if has_roof and material_roof:
        ref = REF_MAP[material_roof] + 'A'
        qty = float(qty_m2_roof or 0)
        prods = call('product.product', 'search_read',
                     [[['default_code', '=', ref]]], {'fields': ['id'], 'limit': 1})
        if not prods:
            raise HTTPException(status_code=400, detail=f'Produkt [{ref}] nenalezen v Odoo')
        unit_price_incl = (eligible_roof / qty) / (1 - COSMETIC_DISC / 100) if qty else 0
        order_lines.append((0, 0, {
            'product_id': prods[0]['id'],
            'product_uom_qty': qty,
            'price_unit': round(unit_price_incl / TAX_RATE, 2),
            'discount': COSMETIC_DISC,
        }))

    if has_ceiling and material_ceiling:
        ref = REF_MAP[material_ceiling] + 'B'
        qty = float(qty_m2_ceiling or 0)
        prods = call('product.product', 'search_read',
                     [[['default_code', '=', ref]]], {'fields': ['id'], 'limit': 1})
        if not prods:
            raise HTTPException(status_code=400, detail=f'Produkt [{ref}] nenalezen v Odoo')
        unit_price_incl = (eligible_ceiling / qty) / (1 - COSMETIC_DISC / 100) if qty else 0
        order_lines.append((0, 0, {
            'product_id': prods[0]['id'],
            'product_uom_qty': qty,
            'price_unit': round(unit_price_incl / TAX_RATE, 2),
            'discount': COSMETIC_DISC,
        }))

    if has_windows:
        qty = float(qty_windows or 0)
        prods = call('product.product', 'search_read',
                     [[['default_code', '=', '4000']]], {'fields': ['id'], 'limit': 1})
        if not prods:
            raise HTTPException(status_code=400, detail='Produkt [4000] nenalezen v Odoo')
        unit_price_incl = (eligible_windows / qty) / (1 - COSMETIC_DISC / 100) if qty else 0
        order_lines.append((0, 0, {
            'product_id': prods[0]['id'],
            'product_uom_qty': qty,
            'price_unit': round(unit_price_incl / TAX_RATE, 2),
            'discount': COSMETIC_DISC,
        }))

    if doprava_prods:
        order_lines.append((0, 0, {
            'product_id': doprava_prods[0]['id'],
            'product_uom_qty': 1,
            'price_unit': round(doprava_price / TAX_RATE, 2),
            'discount': 0,
        }))

    # Extra add-on products (no grant/discount involvement)
    extra_needed = []
    if has_roof and extra_5000a: extra_needed.append('5000A')
    if has_roof and extra_5000b: extra_needed.append('5000B')
    qty_5100_f = float(qty_5100 or 0)
    qty_5101_f = float(qty_5101 or 0)
    if has_ceiling and qty_5100_f > 0: extra_needed.append('5100')
    if has_ceiling and qty_5101_f > 0: extra_needed.append('5101')
    if extra_needed:
        extra_prods = call('product.product', 'search_read',
                           [[['default_code', 'in', extra_needed]]],
                           {'fields': ['id', 'default_code', 'lst_price'], 'limit': 10})
        extra_map = {p['default_code']: p for p in extra_prods}
        for code in ['5000A', '5000B']:
            if code in extra_map:
                order_lines.append((0, 0, {
                    'product_id': extra_map[code]['id'],
                    'product_uom_qty': 1,
                    'price_unit': extra_map[code].get('lst_price', 0),
                    'discount': 0,
                }))
        for code, qty_f in [('5100', qty_5100_f), ('5101', qty_5101_f)]:
            if code in extra_map:
                order_lines.append((0, 0, {
                    'product_id': extra_map[code]['id'],
                    'product_uom_qty': qty_f,
                    'price_unit': extra_map[code].get('lst_price', 0),
                    'discount': 0,
                }))

    total = eligible_roof + eligible_ceiling + eligible_windows + doprava_price
    zaloha   = round(total * split_pct[0] / 100)
    doplatek = round(total * split_pct[1] / 100)
    client_pays = round(total - grant_amount)

    call('sale.order', 'write', [[order_id], {
        'order_line': order_lines,
        'x_studio_zaloha_kc': zaloha,
        'x_studio_doplatek_kc': doplatek,
        'x_studio_vyse_dotace_kc': round(grant_amount),
        'x_studio_cena_po_odecteni_dotace': max(0, client_pays),
    }])

    # Generate contract PDF immediately after saving
    updated = call('sale.order', 'read', [[order_id]], {'fields': [
        'name', 'partner_id', 'amount_total', 'amount_untaxed', 'amount_tax', 'order_line',
        'x_studio_adresa_realizace', 'x_studio_popis_dila',
        'x_studio_zaloha_kc', 'x_studio_termin_zalohy_1',
        'x_studio_doplatek_kc', 'x_studio_termin_dokonceni_1',
        'x_studio_stavebni_pripravenost', 'x_studio_datum_podpisu_smlouvy',
        'x_studio_float_field_45q_1jsh2tmcd', 'x_studio_vyse_dotace_kc',
        'x_studio_cena_po_odecteni_dotace',
    ]})[0]
    partner = call('res.partner', 'read', [[updated['partner_id'][0]]], {'fields': [
        'name', 'street', 'zip', 'city', 'email', 'phone',
    ]})[0]
    lines = call('sale.order.line', 'read', [updated['order_line']], {'fields': [
        'product_id', 'name', 'product_uom_qty', 'product_uom_id',
        'price_unit', 'price_subtotal', 'discount', 'display_type', 'is_downpayment',
    ]})
    pdf_bytes = generate_contract(updated, partner, lines)
    filename = f"Smlouva_{updated['name']}.pdf"
    call('ir.attachment', 'create', [{
        'name': filename,
        'res_model': 'sale.order',
        'res_id': order_id,
        'type': 'binary',
        'datas': base64.b64encode(pdf_bytes).decode(),
        'mimetype': 'application/pdf',
    }])

    odoo_order_url = f'{ODOO_URL}/odoo/sales/{order_id}'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Objednávka vytvořena</title></head>
<body style="font-family:Arial,sans-serif;text-align:center;padding:60px;color:#333;background:#f9f9f9;">
  <div style="background:#fff;border-radius:8px;padding:40px;max-width:480px;margin:auto;box-shadow:0 2px 8px rgba(0,0,0,.1);">
    <div style="font-size:56px;margin-bottom:12px;">&#10003;</div>
    <h2 style="margin:0 0 12px;">Objednávka vytvořena</h2>
    <p style="color:#888;font-size:13px;">Přesměrování zpět do Odoo&hellip;</p>
  </div>
  <script>
    try {{
      if (window.opener) {{
        window.opener.location.href = '{odoo_order_url}';
        window.close();
      }} else {{
        window.location.href = '{odoo_order_url}';
      }}
    }} catch(e) {{
      window.location.href = '{odoo_order_url}';
    }}
  </script>
</body></html>"""

@app.get('/health')
def health():
    return {'status': 'ok'}
