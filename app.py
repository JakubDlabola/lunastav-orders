import base64
import io
import logging
import os
import random
import re
import time
import xmlrpc.client

from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from contract import generate_contract

load_dotenv()

ODOO_URL     = os.environ['ODOO_URL']
ODOO_DB      = os.environ['ODOO_DB']
ODOO_USER    = os.environ['ODOO_USER']
ODOO_API_KEY = os.environ['ODOO_API_KEY']
SERVICE_KEY  = os.environ['SERVICE_KEY']

app = FastAPI(title='LUNASTAV Order Service')

_SIGN_SIG_TYPE_ID        = 1                          # Signature field type id
_SIGN_COMPANY_PARTNER_ID = 3                          # Lukáš Najman (LUNASTAV signer)
_SIGN_COMPANY_EMAIL      = 'lukas.najman@lunastav.cz'
_SIGN_TEST_PARTNER_ID    = 889                        # Tomáš Najman — TEST ONLY, remove before go-live
_SIGN_TEST_EMAIL         = 'najm.tomas@gmail.com'    # TEST ONLY — remove before go-live

# SMS verification — disabled until SMS provider is configured
# _TWILIO_SID  = os.environ.get('TWILIO_ACCOUNT_SID', '')
# _TWILIO_AUTH = os.environ.get('TWILIO_AUTH_TOKEN', '')
# _TWILIO_FROM = os.environ.get('TWILIO_FROM', '')
# _RAILWAY_URL = 'https://lunastav-orders-production.up.railway.app'
# _sms_codes: dict = {}
# _SMS_TTL          = 600
# _SMS_MAX_ATTEMPTS = 5


def _get_or_create_role(call_fn, name):
    ids = call_fn('sign.item.role', 'search', [[['name', '=', name]]])
    return ids[0] if ids else call_fn('sign.item.role', 'create', [{'name': name}])


_SIGN_ANCHOR = '◆'  # placed invisibly at centre of each signing box in the DOCX


def _anchor_posY_on_page(page, label, fallback):
    """Find the ◆ anchor on a pypdf page and return Odoo posY (0=top, 1=bottom)."""
    page_height = float(page.mediabox.height)
    anchor_ys = []
    def visitor(text_chunk, cm, tm, fontDict, fontSize):
        if text_chunk and _SIGN_ANCHOR in text_chunk:
            anchor_ys.append(tm[5])  # Y from bottom in PDF points
    page.extract_text(visitor_text=visitor)
    if anchor_ys:
        anchor_posY = 1.0 - (anchor_ys[0] / page_height)
        posY = round(max(0.05, anchor_posY - 0.08), 3)
        logging.warning(f'SIGN_ANCHOR {label}: anchor_posY={anchor_posY:.4f} → posY={posY}')
        return posY
    logging.warning(f'SIGN_ANCHOR {label}: not found, using fallback={fallback}')
    return fallback


def _find_contract_sig_page_and_posY(reader):
    """Return (page_num_1based, posY) for the main contract signature table."""
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ''
        if ('ílohy' not in text and 'Prilohy' not in text) or 'Najman' not in text:
            continue
        return (i + 1, _anchor_posY_on_page(page, f'contract p={i+1}', 0.47))
    return (None, 0.47)


# ── SMS verification (disabled) ───────────────────────────────────────────────
# Uncomment when SMS provider is configured.
#
# def _normalize_phone(phone: str) -> str:
#     stripped = phone.strip()
#     digits = re.sub(r'[^\d]', '', stripped)
#     if stripped.startswith('+'): return '+' + digits
#     if digits.startswith('00'): return '+' + digits[2:]
#     if digits.startswith('0') and len(digits) == 10: return '+420' + digits[1:]
#     if len(digits) == 9: return '+420' + digits
#     return '+' + digits
#
# def _send_sms(to: str, body: str):
#     from twilio.rest import Client
#     Client(_TWILIO_SID, _TWILIO_AUTH).messages.create(from_=_TWILIO_FROM, to=to, body=body)
#
# def _verify_page(sign_id, partner_id, token, masked_phone, error=''): ...


def _create_sign_request(call_fn, pdf_bytes, order_name, client_partner_id, client_email,
                         company_partner_id=None, company_email=None, salesperson_partner_id=None,
                         client_name=''):
    """Upload PDF to Odoo Sign and send signing request. Client signs first, LUNASTAV after."""
    company_partner_id = company_partner_id or _SIGN_COMPANY_PARTNER_ID
    company_email      = company_email      or _SIGN_COMPANY_EMAIL

    # Force Czech language so Odoo generates the completion certificate in Czech
    def call(model, method, args, kw=None):
        return call_fn(model, method, args, {'context': {'lang': 'cs_CZ'}, **(kw or {})})
    client_role_id  = _get_or_create_role(call_fn, 'Objednatel')
    company_role_id = _get_or_create_role(call_fn, 'Zhotovitel')

    try:
        from pypdf import PdfReader
        _reader = PdfReader(io.BytesIO(pdf_bytes))
        num_pages = len(_reader.pages)
    except Exception:
        _reader = None
        num_pages = len(re.findall(rb'/Type\s*/Page[^s]', pdf_bytes)) or 5
    last_page = num_pages

    if _reader:
        contract_sig_page, contract_sig_posY = _find_contract_sig_page_and_posY(_reader)
        tc_sig_posY = _anchor_posY_on_page(
            _reader.pages[last_page - 1], f'T&C p={last_page}', 0.73)
    else:
        contract_sig_page, contract_sig_posY = None, 0.47
        tc_sig_posY = 0.73

    doc_prefix = f'{client_name} - {order_name}' if client_name else order_name

    # 1. Upload PDF as an attachment
    att_id = call('ir.attachment', 'create', [{
        'name': f'{doc_prefix}.pdf',
        'type': 'binary',
        'datas': base64.b64encode(pdf_bytes).decode(),
        'mimetype': 'application/pdf',
    }])

    # 2. Create the sign template — name drives the signed-document filename
    template_id = call('sign.template', 'create', [{'name': doc_prefix}])

    # 3. Create sign.document linking the attachment to the template
    doc_id = call('sign.document', 'create', [{
        'template_id': template_id,
        'attachment_id': att_id,
        'name': f'{doc_prefix}.pdf',
        'num_pages': num_pages,
    }])

    # 4. Place signature fields on both signature pages:
    #    - Main contract page: Objednatel left (0.10), Zhotovitel right (0.55), mid-page
    #    - T&C last page: same columns, near bottom
    # If last_page is one past contract_sig_page, it's a blank overflow page — ignore it
    effective_last = (contract_sig_page
                      if contract_sig_page and last_page == contract_sig_page + 1
                      else last_page)
    sign_locations = []
    if contract_sig_page and contract_sig_page != effective_last:
        sign_locations.append((contract_sig_page, contract_sig_posY))
    sign_locations.append((effective_last, tc_sig_posY))

    for page_num, posY in sign_locations:
        for role_id, posX in [(client_role_id, 0.15), (company_role_id, 0.55)]:
            call('sign.item', 'create', [{
                'template_id': template_id,
                'document_id': doc_id,
                'type_id': _SIGN_SIG_TYPE_ID,
                'responsible_id': role_id,
                'page': page_num,
                'posX': posX, 'posY': posY, 'width': 0.30, 'height': 0.16,
            }])

    # 5. Create the signing request
    request_id = call('sign.request', 'create', [{
        'template_id': template_id,
        'reference': order_name,
        'subject': f'LUNASTAV - potvrzení SOD {order_name} pro {client_name}' if client_name else f'LUNASTAV - potvrzení SOD {order_name}',
        'send_channel': 'email',
        'request_item_ids': [
            (0, 0, {'role_id': client_role_id,  'partner_id': client_partner_id}),
            (0, 0, {'role_id': company_role_id, 'partner_id': company_partner_id}),
        ],
    }])

    # Subscribe the salesperson as a follower so they can see this request with Sign/User access
    if salesperson_partner_id:
        call_fn('sign.request', 'message_subscribe', [[request_id], [salesperson_partner_id]])

    # Build the direct client signing URL from the access_token on their item
    sign_url = None
    items = call_fn('sign.request.item', 'search_read',
                    [[('sign_request_id', '=', request_id), ('role_id', '=', client_role_id)]],
                    {'fields': ['access_token']})
    if items:
        sign_url = f'{ODOO_URL}/sign/document/{request_id}/{items[0]["access_token"]}'

    return request_id, sign_url


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
        'x_studio_zaloha_kc', 'x_studio_termin_zalohy_2',
        'x_studio_doplatek_kc', 'x_studio_termin_dokonceni_2',
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
def order_form_get(order_id: int = Query(...), key: str = Query(...), test: int = Query(0)):
    if key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail='Unauthorized')

    uid, models = odoo_connect()

    def call(model, method, args, kw={}):
        return models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, model, method, args, kw)

    orders = call('sale.order', 'read', [[order_id]], {'fields': ['name', 'partner_id', 'opportunity_id', 'user_id']})
    if not orders:
        raise HTTPException(status_code=404, detail=f'Objednávka {order_id} nenalezena')
    order = orders[0]

    partner_name = order['partner_id'][1] if order['partner_id'] else 'Neznámý zákazník'

    _p = call('res.partner', 'read', [[order['partner_id'][0]]], {'fields': ['name', 'email', 'phone', 'street', 'zip', 'city', 'x_studio_datum_narozeni']})[0] if order['partner_id'] else {}
    partner_email  = _p.get('email') or ''
    partner_phone  = _p.get('phone') or ''
    partner_street = _p.get('street') or ''
    partner_zip    = _p.get('zip') or ''
    partner_city   = _p.get('city') or ''
    _dob_raw       = _p.get('x_studio_datum_narozeni') or ''
    try:
        from datetime import date as _date
        _d = _date.fromisoformat(_dob_raw)
        partner_dob = f'{_d.day:02d}.{_d.month:02d}.{_d.year}'
    except Exception:
        partner_dob = ''

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
<html lang="cs">
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
    .type-section {{ padding-left: 14px; margin-top: 16px; border-left: 4px solid #c8a840; border-radius: 0 6px 6px 0; padding: 12px 14px; }}
    #roof-section    {{ border-left-color: #c8673a; background: rgba(200, 103, 58, 0.06); }}
    #ceiling-section {{ border-left-color: #3a7fc8; background: rgba(58, 127, 200, 0.06); }}
    #windows-section {{ border-left-color: #3aaa6e; background: rgba(58, 170, 110, 0.06); }}
    input[type=number] {{ width: 100%; padding: 9px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 15px; margin-top: 2px; }}
    .preview {{ background: #f9f9f9; border: 1px solid #eee; border-radius: 6px; padding: 16px 20px; margin-top: 20px; font-size: 14px; }}
    .preview-row {{ display: flex; justify-content: space-between; margin-bottom: 6px; }}
    .preview-row.grant {{ color: #2a7a3e; font-weight: 500; }}
    .preview-row.sub {{ font-size: 13px; color: #666; padding-left: 14px; margin-bottom: 2px; }}
    .preview-row.total {{ font-weight: bold; font-size: 15px; border-top: 1px solid #ddd; padding-top: 10px; margin-top: 6px; margin-bottom: 0; }}
    .split-note {{ font-size: 12px; color: #888; margin-top: 6px; }}
    button[type=submit] {{ width: 100%; margin-top: 28px; padding: 13px; font-size: 15px; background: #c8a840; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }}
    button[type=submit]:hover {{ background: #b5942e; }}
    button[type=submit]:disabled {{ background: #ccc; cursor: default; }}
    .hidden {{ display: none !important; }}
    .grant-info {{ font-size: 13px; color: #555; margin-top: 4px; }}
    input[type=text], input[type=email], input[type=tel], input[type=date] {{ width: 100%; padding: 9px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 15px; margin-top: 2px; }}
    .field-label-row {{ display: flex; align-items: center; justify-content: space-between; margin: 20px 0 8px; }}
    .field-label-row .field-label {{ margin: 0; }}
    .edit-toggle-btn {{ font-size: 12px; padding: 3px 10px; border: 1px solid #ccc; border-radius: 4px; background: #f5f5f5; color: #666; cursor: pointer; white-space: nowrap; }}
    .edit-toggle-btn.active {{ background: #fff8e1; border-color: #c8a840; color: #7a5c00; }}
    textarea[readonly], input[type=text][readonly] {{ background: #f9f9f9; color: #555; cursor: default; }}
  </style>
</head>
<body>
<div class="card">
  <h2>Nová objednávka</h2>
  <div class="subtitle">{partner_name} &middot; {order['name']}</div>
  {'<div style="background:#c00;color:#fff;font-size:12px;font-weight:bold;text-align:center;padding:4px 8px;border-radius:4px;margin-bottom:12px;">TEST REŽIM — podpis jde Tomáši Najmanovi</div>' if test else ''}

  <form method="post" action="/order-form" id="mainForm">
    <input type="hidden" name="order_id" value="{order_id}">
    <input type="hidden" name="key" value="{key}">
    <input type="hidden" name="test" value="{test}">
    <input type="hidden" name="eligible_roof"        id="inp_elig_roof"    value="0">
    <input type="hidden" name="eligible_ceiling"     id="inp_elig_ceiling" value="0">
    <input type="hidden" name="eligible_win_a"       id="inp_elig_win_a"   value="0">
    <input type="hidden" name="eligible_win_b"       id="inp_elig_win_b"   value="0">
    <input type="hidden" name="eligible_win_c"       id="inp_elig_win_c"   value="0">
    <input type="hidden" name="discount_pct_roof"    id="inp_disc_roof"    value="0">
    <input type="hidden" name="discount_pct_ceiling" id="inp_disc_ceiling" value="0">
    <input type="hidden" name="grant_amount"         id="inp_grant_amount" value="0">

    <span class="field-label">Kontakt</span>
    <div style="display:grid;gap:8px;margin-bottom:20px;">
      <div>
        <label style="font-size:12px;color:#888;">Jméno klienta</label>
        <input type="text" name="client_name" value="{partner_name}" placeholder="Jméno klienta" required>
      </div>
      <div>
        <label style="font-size:12px;color:#888;">Ulice</label>
        <input type="text" name="client_street" value="{partner_street}" placeholder="Ulice a číslo popisné">
      </div>
      <div style="display:grid;grid-template-columns:110px 1fr;gap:8px;">
        <div>
          <label style="font-size:12px;color:#888;">PSČ</label>
          <input type="text" name="client_zip" value="{partner_zip}" placeholder="PSČ">
        </div>
        <div>
          <label style="font-size:12px;color:#888;">Město</label>
          <input type="text" name="client_city" value="{partner_city}" placeholder="Město">
        </div>
      </div>
      <div>
        <label style="font-size:12px;color:#888;">E-mail klienta</label>
        <input type="email" name="client_email" value="{partner_email}" placeholder="E-mail klienta" required>
      </div>
      <div>
        <label style="font-size:12px;color:#888;">Telefon</label>
        <input type="tel" name="client_phone" id="client_phone" value="{partner_phone}" placeholder="Telefon klienta" required onchange="checkSubmit()">
      </div>
      <div>
        <label style="font-size:12px;color:#888;">Datum narození</label>
        <input type="text" name="client_dob" value="{partner_dob}" placeholder="DD.MM.RRRR">
      </div>
      <div style="margin-top:4px;">
        <div style="display:flex;align-items:center;gap:10px;">
          <input type="checkbox" id="addr_same" name="addr_same" value="1" checked
                 onchange="document.getElementById('addr-custom').classList.toggle('hidden',this.checked)"
                 style="width:18px;height:18px;cursor:pointer;accent-color:#c8a840;">
          <label for="addr_same" style="font-size:14px;cursor:pointer;">Adresa realizace se shoduje s adresou trvalého bydliště</label>
        </div>
        <div id="addr-custom" class="hidden" style="margin-top:8px;">
          <span class="field-label">Adresa realizace</span>
          <input type="text" name="adresa_realizace" id="adresa_realizace" placeholder="Ulice, PSČ Město">
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#f0f8f0;border:1px solid #c8e6c9;border-radius:6px;margin-top:6px;">
        <input type="checkbox" id="grant_enabled" checked onchange="calc()" style="width:18px;height:18px;cursor:pointer;accent-color:#2a7a3e;">
        <label for="grant_enabled" style="font-size:14px;cursor:pointer;font-weight:500;">Zákazník čerpá dotaci NZÚ</label>
      </div>
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
      <span class="field-label">Tloušťka izolace (cm)</span>
      <input type="number" name="thickness_roof" id="thickness_roof" min="1" step="1" placeholder="30" oninput="updatePopisDila()">
      <span class="field-label">Plocha střechy (m²)</span>
      <input type="number" name="qty_m2_roof" id="qty_m2_roof" value="{zastavena_plocha}" min="1" step="1" oninput="calc(); updatePopisDila()">
      <span class="field-label">Doplňkové práce</span>
      <div class="options">
        <label class="opt-wrap"><input type="checkbox" name="extra_5000a" value="1" onchange="selectExtra5000(this)"><span class="opt-btn">Otevření a zavření falcované střechy</span></label>
        <label class="opt-wrap"><input type="checkbox" name="extra_5000b" value="1" onchange="selectExtra5000(this)"><span class="opt-btn">Otevření a zavření PVC folie</span></label>
        <label class="opt-wrap"><input type="checkbox" name="extra_5000c" value="1" onchange="selectExtra5000(this)"><span class="opt-btn">Otevření a zavření lepenkové střechy</span></label>
      </div>
    </div>

    <div id="ceiling-section" class="hidden type-section">
      <span class="field-label">Materiál — Strop</span>
      <div class="options">
        <label class="opt-wrap"><input type="radio" name="material_ceiling" value="thermofloc" onchange="calc()"><span class="opt-btn">Thermofloc</span></label>
        <label class="opt-wrap"><input type="radio" name="material_ceiling" value="supafil" onchange="calc()"><span class="opt-btn">SUPAFIL LOFT PRO</span></label>
        <label class="opt-wrap"><input type="radio" name="material_ceiling" value="strikana" onchange="calc()"><span class="opt-btn">Stříkaná izolace</span></label>
      </div>
      <span class="field-label">Tloušťka izolace (cm)</span>
      <input type="number" name="thickness_ceiling" id="thickness_ceiling" min="1" step="1" value="25" oninput="updatePopisDila()">
      <span class="field-label">Plocha stropu (m²)</span>
      <input type="number" name="qty_m2_ceiling" id="qty_m2_ceiling" value="{zastavena_plocha}" min="1" step="1" oninput="calc(); updatePopisDila()">
      <span class="field-label">Kostrukce pochozí plochy (m²)</span>
      <input type="number" name="qty_5100" id="qty_5100" min="0" step="1" placeholder="nezahrnout" oninput="calc(); updatePopisDila()">
      <span class="field-label">Konstrukce revizní lávky (m)</span>
      <input type="number" name="qty_5101" id="qty_5101" min="0" step="1" placeholder="nezahrnout" oninput="calc(); updatePopisDila()">
    </div>

    <div id="windows-section" class="hidden type-section">
      <span class="field-label">Okno, nebarvené — 9 000 Kč / m²</span>
      <input type="number" name="qty_win_a" id="qty_win_a" min="0" step="0.1" placeholder="0 m²" oninput="onWinQtyChange()">
      <span class="field-label">Okno, jednostranná barva — 9 900 Kč / m²</span>
      <input type="number" name="qty_win_b" id="qty_win_b" min="0" step="0.1" placeholder="0 m²" oninput="onWinQtyChange()">
      <span class="field-label">Okno, oboustranná barva — 10 800 Kč / m²</span>
      <input type="number" name="qty_win_c" id="qty_win_c" min="0" step="0.1" placeholder="0 m²" oninput="onWinQtyChange()">
      <div style="margin-top:14px;display:flex;align-items:center;gap:10px;">
        <input type="checkbox" name="has_blinds" id="chk_blinds" value="1"
               onchange="onBlindsNetsChange('blinds')"
               style="width:18px;height:18px;cursor:pointer;accent-color:#3aaa6e;">
        <label for="chk_blinds" style="font-size:14px;cursor:pointer;">Žaluzie — 1 000 Kč / m²</label>
      </div>
      <div id="blinds-qty-section" class="hidden" style="margin-top:6px;">
        <span class="field-label">Žaluzie (m²)</span>
        <input type="number" name="qty_blinds" id="qty_blinds" min="0" step="0.1" placeholder="0 m²"
               oninput="document.getElementById('qty_blinds').dataset.userSet='1'; calc()">
      </div>
      <div style="margin-top:14px;display:flex;align-items:center;gap:10px;">
        <input type="checkbox" name="has_nets" id="chk_nets" value="1"
               onchange="onBlindsNetsChange('nets')"
               style="width:18px;height:18px;cursor:pointer;accent-color:#3aaa6e;">
        <label for="chk_nets" style="font-size:14px;cursor:pointer;">Síť proti hmyzu — 1 000 Kč / m²</label>
      </div>
      <div id="nets-qty-section" class="hidden" style="margin-top:6px;">
        <span class="field-label">Síť proti hmyzu (m²)</span>
        <input type="number" name="qty_nets" id="qty_nets" min="0" step="0.1" placeholder="0 m²"
               oninput="document.getElementById('qty_nets').dataset.userSet='1'; calc()">
      </div>
    </div>

    <span class="field-label">Zbývající dotace (Kč)</span>
    <input type="number" id="remaining_grant_k" value="{remaining_grant_k}" min="0" step="1000" oninput="calc()" placeholder="bez omezení">

    <div id="preview" class="preview hidden">
      <div class="preview-row"><span>Cena bez slevy</span><span id="pv-base">—</span></div>
      <div class="preview-row sub hidden" id="pv-windows-row"><span>z toho okna celkem</span><span id="pv-windows">—</span></div>
      <div class="preview-row hidden" id="pv-rate-roof-row"><span>Efektivní cena / m² — Střecha</span><span id="pv-rate-roof">—</span></div>
      <div class="preview-row hidden" id="pv-rate-ceil-row"><span>Efektivní cena / m² — Strop</span><span id="pv-rate-ceil">—</span></div>
      <div class="preview-row hidden" id="pv-disc-row"><span>Sleva</span><span id="pv-disc">—</span></div>
      <div class="preview-row grant hidden" id="pv-grant-row"><span>Náklady pokryté dotací</span><span id="pv-grant">—</span></div>
      <div class="preview-row hidden" id="pv-client-row"><span>Náklady k uhrazení</span><span id="pv-client">—</span></div>
      <div class="preview-row hidden" id="pv-pochozi-row"><span>Pochozí plocha / lávka</span><span id="pv-pochozi">—</span></div>
      <div class="preview-row total"><span>Celkem k úhradě</span><span id="pv-total">—</span></div>
      <div class="preview-row hidden" id="pv-zaloha-row"><span id="pv-zaloha-label">Záloha</span><span id="pv-zaloha">—</span></div>
      <div class="preview-row hidden" id="pv-doplatek-row"><span id="pv-doplatek-label">Doplatek</span><span id="pv-doplatek">—</span></div>
    </div>

    <div id="split-section" class="hidden">
      <span class="field-label">Záloha / doplatek</span>
      <div class="options" id="split-opts">
        <label class="opt-wrap hidden" id="split-80-20"><input type="radio" name="split" value="80-20" onchange="calc();updateTermin()"><span class="opt-btn">80 / 20</span></label>
        <label class="opt-wrap"><input type="radio" name="split" value="60-40" onchange="calc();updateTermin()"><span class="opt-btn">60 / 40</span></label>
        <label class="opt-wrap"><input type="radio" name="split" value="20-80" onchange="calc();updateTermin()"><span class="opt-btn">20 / 80</span></label>
        <label class="opt-wrap"><input type="radio" name="split" value="0-100" onchange="calc();updateTermin()"><span class="opt-btn">Bez zálohy</span></label>
      </div>
      <div class="split-note" id="split-note"></div>
    </div>

    <div id="termin-zalohy-section" class="hidden">
      <span class="field-label" style="margin-top:20px;">Záloha splatná do 14 dnů ode dne</span>
      <div class="options">
        <label class="opt-wrap"><input type="radio" name="termin_zalohy_2" value="podepsání objednávky" onchange="checkSubmit()"><span class="opt-btn">podepsání objednávky</span></label>
        <label class="opt-wrap"><input type="radio" name="termin_zalohy_2" value="obdržení dotace" onchange="checkSubmit()"><span class="opt-btn">obdržení dotace</span></label>
      </div>
    </div>

    <div id="termin-section" class="hidden">
      <div class="field-label-row" style="margin-top:20px;">
        <span class="field-label">Termín dokončení</span>
        <button type="button" id="edit-btn-termin_dokonceni" class="edit-toggle-btn" onclick="toggleManual('termin_dokonceni', updateTermin)" title="Upravit ručně">✎ Upravit</button>
      </div>
      <div class="options">
        <label class="opt-wrap"><input type="radio" name="termin_days" value="45" onchange="updateTermin()"><span class="opt-btn">45 dní</span></label>
        <label class="opt-wrap"><input type="radio" name="termin_days" value="90" onchange="updateTermin()"><span class="opt-btn">90 dní</span></label>
        <label class="opt-wrap"><input type="radio" name="termin_days" value="150" onchange="updateTermin()"><span class="opt-btn">150 dní</span></label>
      </div>
      <div id="termin-cond" class="hidden" style="margin-top:8px;">
        <div class="options">
          <label class="opt-wrap"><input type="radio" name="termin_cond" value="podpis" onchange="updateTermin()"><span class="opt-btn">od podpisu smlouvy</span></label>
          <label class="opt-wrap"><input type="radio" name="termin_cond" value="dotace" onchange="updateTermin()"><span class="opt-btn">od schválení dotace</span></label>
        </div>
      </div>
      <input type="text" name="termin_dokonceni" id="termin_dokonceni" readonly style="margin-top:8px; width:100%; padding:9px 12px; border:1px solid #ddd; border-radius:6px; font-size:14px;" placeholder="Termín bude sestaven po výběru výše">
    </div>

    <div style="margin-top:20px;border-top:1px solid #eee;padding-top:20px;">
      <div class="field-label-row">
        <span class="field-label">Popis díla</span>
        <button type="button" id="edit-btn-popis_dila" class="edit-toggle-btn" onclick="toggleManual('popis_dila', updatePopisDila)" title="Upravit ručně">✎ Upravit</button>
      </div>
      <textarea name="popis_dila" id="popis_dila" rows="5" readonly
                style="width:100%;padding:9px 12px;border:1px solid #ddd;border-radius:6px;font-size:14px;resize:vertical;font-family:inherit;"></textarea>
      <div id="stavebni-section" class="hidden">
        <div class="field-label-row" style="margin-top:20px;">
          <span class="field-label">Stavební připravenost</span>
          <button type="button" id="edit-btn-stavebni_pripravenost" class="edit-toggle-btn" onclick="toggleManual('stavebni_pripravenost', updateStavebni)" title="Upravit ručně">✎ Upravit</button>
        </div>
        <textarea name="stavebni_pripravenost" id="stavebni_pripravenost" rows="6" readonly
                  style="width:100%;padding:9px 12px;border:1px solid #ddd;border-radius:6px;font-size:14px;resize:vertical;font-family:inherit;"></textarea>
      </div>
    </div>


    <button type="submit" id="submitBtn" disabled>Vytvořit objednávku</button>
  </form>
</div>
<script>
const GRANT_RATE = {{roof: 2000, ceiling: 750, windows: 8000}};
const LISTED    = {{roof: 2002, ceiling: 751}};
const WIN_RATES = {{a: 9000, b: 9900, c: 10800}};

const _manualFields = new Set();
function toggleManual(fieldId, autoFn) {{
  const field = document.getElementById(fieldId);
  const btn   = document.getElementById('edit-btn-' + fieldId);
  if (_manualFields.has(fieldId)) {{
    if (!confirm('Va\u0161e \u00fapravy budou ztraceny a pole bude znovu vypln\u011bno automaticky. Pokra\u010dovat?')) return;
    _manualFields.delete(fieldId);
    field.readOnly = true;
    btn.classList.remove('active');
    btn.textContent = '\u270e Upravit';
    if (autoFn) autoFn();
  }} else {{
    _manualFields.add(fieldId);
    field.readOnly = false;
    btn.classList.add('active');
    btn.textContent = '\u21a9 Obnovit automatick\u00e9 vypl\u0148ov\u00e1n\u00ed';
    field.focus();
  }}
}}

const _STRIKANA_TEXT = 'Stavebn\u00ed prostor bude kv\u016fli zamezen\u00ed pr\u016fvanu uzav\u0159en a vytopen minim\u00e1ln\u011b na teplotu 17\u00b0C. M\u00edsta uvnit\u0159 stavebn\u00edho prostoru, jen\u017e nesm\u00ed b\u00fdt zne\u010di\u0161t\u011bna aplika\u010dn\u00ed chemi\u00ed, budou objednatelem zakryta, v p\u0159\u00edpad\u011b venkovn\u00ed aplikace objednatel proti p\u0159\u00edpadn\u00e9mu zne\u010di\u0161t\u011bn\u00ed zaji\u0161t\u00ed okol\u00ed v dosahu cca 100 m. Objednatel zaji\u0161t\u00ed, aby okolo kom\u00ednov\u00e9ho t\u011blesa byla neho\u0159lav\u00e1 vrstva v minim\u00e1ln\u00ed tlou\u0161\u0165ce 50 mm. S\u00e1drokartonov\u00e9 ro\u0161ty mus\u00ed b\u00fdt s ohledem na rezervu pro b\u011b\u017enou toleranci tlou\u0161\u0165ky PUR p\u011bny nav\u00fd\u0161eny o 3 cm. Objednatel mus\u00ed b\u011bhem pr\u016fb\u011bhu aplikace izolace zamezit vstupu nepovolan\u00fdch do stavebn\u00edch prostor\u016f.';
const _BASE_STAVEBNI = 'Stavební připravenost spočívá především ve vyklizení místa realizace.';

function selectExtra5000(el) {{
  if (el.checked) {{
    document.querySelectorAll('input[name=extra_5000a],input[name=extra_5000b],input[name=extra_5000c]').forEach(function(cb) {{
      if (cb !== el) cb.checked = false;
    }});
  }}
  updatePopisDila();
}}

function updateStavebni() {{
  if (_manualFields.has('stavebni_pripravenost')) return;
  const hasRoof = document.getElementById('chk_roof').checked;
  const hasCeil = document.getElementById('chk_ceiling').checked;
  const sec = document.getElementById('stavebni-section');
  sec.classList.toggle('hidden', !hasRoof && !hasCeil);
  if (!hasRoof && !hasCeil) return;
  const matRoof = hasRoof ? document.querySelector('input[name=material_roof]:checked')?.value : '';
  const matCeil = hasCeil ? document.querySelector('input[name=material_ceiling]:checked')?.value : '';
  const isStrikana = matRoof === 'strikana' || matCeil === 'strikana';
  document.getElementById('stavebni_pripravenost').value =
    _BASE_STAVEBNI + (isStrikana ? ' ' + _STRIKANA_TEXT : '');
}}

const MAT_NAME = {{thermofloc: 'Thermofloc', supafil: 'SUPAFIL LOFT PRO', strikana: 'Stříkaná izolace'}};

function updatePopisDila() {{
  if (_manualFields.has('popis_dila')) return;
  const hasRoof = document.getElementById('chk_roof').checked;
  const hasCeil = document.getElementById('chk_ceiling').checked;
  const hasWin  = document.getElementById('chk_windows').checked;
  if (!hasRoof && !hasCeil && !hasWin) return;

  // Title line
  const titleParts = [];
  if (hasRoof && hasCeil) titleParts.push('Zateplení střechy a stropu');
  else if (hasRoof) titleParts.push('Zateplení střechy');
  else if (hasCeil) titleParts.push('Zateplení stropu');
  if (hasWin) titleParts.push('výměna oken');
  let title = titleParts[0] || '';
  if (titleParts.length > 1) title += ' a ' + titleParts.slice(1).join(' a ');
  title = title.charAt(0).toUpperCase() + title.slice(1);

  const lines = [title];

  if (hasRoof) {{
    const mat  = document.querySelector('input[name=material_roof]:checked')?.value || '';
    const qty  = document.getElementById('qty_m2_roof').value || '';
    const tEl  = document.getElementById('thickness_roof');
    const t    = tEl.value || tEl.placeholder || '30';
    if (mat && qty) {{
      lines.push('Na ploše střechy o výměře ' + qty + ' m² bude zhotovitelem aplikována tepelná izolace ' + (MAT_NAME[mat] || mat) + ' o minimální tloušťce ' + t + ' cm.');
    }}
    const is5000A = document.querySelector('input[name=extra_5000a]')?.checked;
    const is5000B = document.querySelector('input[name=extra_5000b]')?.checked;
    const is5000C = document.querySelector('input[name=extra_5000c]')?.checked;
    if (is5000A || is5000B || is5000C) {{
      const krytina = is5000A ? 'falcovaný plech' : is5000B ? 'PVC folie' : 'lepenka';
      lines.push('Jedná se o plochou střechu. Střešní krytina je ' + krytina + '. Zhotovitel do dutiny vstoupí otvorem, který ve střešní krytině vytvoří a po realizaci opět zapraví.');
    }}
  }}

  if (hasCeil) {{
    const mat = document.querySelector('input[name=material_ceiling]:checked')?.value || '';
    const qty = document.getElementById('qty_m2_ceiling').value || '';
    const t   = document.getElementById('thickness_ceiling').value || '25';
    if (mat && qty) {{
      lines.push('Na ploše stropu o výměře ' + qty + ' m² bude zhotovitelem aplikována tepelná izolace ' + (MAT_NAME[mat] || mat) + ' o minimální tloušťce ' + t + ' cm.');
    }}
    const q5100 = parseFloat(document.getElementById('qty_5100').value) || 0;
    if (q5100 > 0) lines.push('Na ploše ' + q5100 + ' m² bude nad izolací zhotovena pochozí plocha.');
    const q5101 = parseFloat(document.getElementById('qty_5101').value) || 0;
    if (q5101 > 0) lines.push('Zhotovitel postaví revizní lávku o délce ' + q5101 + ' m.');
  }}

  const body = lines.slice(1).join(' ');
  document.getElementById('popis_dila').value = lines[0] + (body ? '\\n' + body : '');
}}

function getRemK()  {{ const v = parseFloat(document.getElementById('remaining_grant_k').value); return isNaN(v) ? null : v; }}
function hasGrant() {{ return document.getElementById('grant_enabled').checked; }}
function getSplit() {{ return document.querySelector('input[name=split]:checked')?.value; }}
function fmt(n)     {{ return new Intl.NumberFormat('cs-CZ').format(Math.round(n)) + ' K\u010d'; }}

function roofMinRate(qty) {{
  if (qty <= 50) return 1000;
  if (qty >= 100) return 750;
  return 1000 + (750 - 1000) / (100 - 50) * (qty - 50);
}}

function ceilMinRate(qty) {{
  if (qty <= 50) return 1000;
  if (qty >= 90) return 750;
  return 1000 + (750 - 1000) / (90 - 50) * (qty - 50);
}}

function onTypesChange() {{
  const hasRoof = document.getElementById('chk_roof').checked;
  const hasCeil = document.getElementById('chk_ceiling').checked;
  const hasWin  = document.getElementById('chk_windows').checked;
  document.getElementById('roof-section').classList.toggle('hidden', !hasRoof);
  document.getElementById('ceiling-section').classList.toggle('hidden', !hasCeil);
  document.getElementById('windows-section').classList.toggle('hidden', !hasWin);
  const anyType = hasRoof || hasCeil || hasWin;
  document.getElementById('split-section').classList.toggle('hidden', !anyType);
  document.getElementById('termin-zalohy-section').classList.toggle('hidden', !anyType);
  document.getElementById('termin-section').classList.toggle('hidden', !anyType);
  const winOnly = hasWin && !hasRoof && !hasCeil;
  document.getElementById('split-80-20').classList.toggle('hidden', !hasWin);
  document.querySelectorAll('#split-opts label:not(#split-80-20)').forEach(l => l.classList.toggle('hidden', winOnly));
  document.getElementById('split-note').textContent = winOnly ? 'Pro okna je vždy záloha 80 %, doplatek 20 %.' : '';
  calc();
  updateTermin();
  updateStavebni();
  updatePopisDila();
}}

function getSplitPct() {{
  const winOnly = document.getElementById('chk_windows').checked &&
                  !document.getElementById('chk_roof').checked &&
                  !document.getElementById('chk_ceiling').checked;
  if (winOnly) return 80;
  const r = document.querySelector('input[name=split]:checked');
  if (!r) return null;
  return parseInt(r.value.split('-')[0], 10);
}}

function updateTermin() {{
  if (_manualFields.has('termin_dokonceni')) return;
  const daysEl = document.querySelector('input[name=termin_days]:checked');
  const days   = daysEl ? daysEl.value : '';
  const pct    = getSplitPct();
  const hasZaloha = pct !== null && pct > 0;
  const condEl = document.getElementById('termin-cond');
  condEl.classList.toggle('hidden', hasZaloha || !days);
  let auto = '';
  if (days) {{
    if (hasZaloha) {{
      auto = 'do ' + days + ' dnů od obdržení zálohové platby ve výši ' + pct + ' % z celkové ceny';
    }} else {{
      const condEl2 = document.querySelector('input[name=termin_cond]:checked');
      if (condEl2) {{
        const cond = condEl2.value === 'dotace' ? 'schválení dotace' : 'podpisu smlouvy';
        auto = 'do ' + days + ' dnů od ' + cond;
      }}
    }}
  }}
  const field = document.getElementById('termin_dokonceni');
  if (auto) field.value = auto;
}}

function calc() {{
  const hasRoof = document.getElementById('chk_roof').checked;
  const hasCeil = document.getElementById('chk_ceiling').checked;
  const hasWin  = document.getElementById('chk_windows').checked;
  if (!hasRoof && !hasCeil && !hasWin) {{ document.getElementById('preview').classList.add('hidden'); checkSubmit(); return; }}

  const qRoof = hasRoof ? (parseFloat(document.getElementById('qty_m2_roof').value)    || 0) : 0;
  const qCeil = hasCeil ? (parseFloat(document.getElementById('qty_m2_ceiling').value) || 0) : 0;
  const qWinA = hasWin  ? (parseFloat(document.getElementById('qty_win_a').value)      || 0) : 0;
  const qWinB = hasWin  ? (parseFloat(document.getElementById('qty_win_b').value)      || 0) : 0;
  const qWinC = hasWin  ? (parseFloat(document.getElementById('qty_win_c').value)      || 0) : 0;
  const qWinTot = qWinA + qWinB + qWinC;

  const lRoof = LISTED.roof * qRoof, lCeil = LISTED.ceiling * qCeil;
  const lWinA = WIN_RATES.a * qWinA, lWinB = WIN_RATES.b * qWinB, lWinC = WIN_RATES.c * qWinC;
  const lWin = lWinA + lWinB + lWinC;
  const lTotal = lRoof + lCeil + lWin;
  if (lTotal === 0) {{ document.getElementById('preview').classList.add('hidden'); checkSubmit(); return; }}

  const fRoof = GRANT_RATE.roof * qRoof, fCeil = GRANT_RATE.ceiling * qCeil, fWin = GRANT_RATE.windows * qWinTot;
  const fTot = fRoof + fCeil + fWin;

  const hasBlinds = hasWin && document.getElementById('chk_blinds').checked;
  const hasNets   = hasWin && document.getElementById('chk_nets').checked;
  const qBlinds   = hasBlinds ? (parseFloat(document.getElementById('qty_blinds').value) || 0) : 0;
  const qNets     = hasNets   ? (parseFloat(document.getElementById('qty_nets').value)   || 0) : 0;
  const blindsCost = Math.round(1000 * qBlinds);
  const netsCost   = Math.round(1000 * qNets);

  const DOPRAVA = 250;
  let eRoof = 0, eCeil = 0, grantReceived = 0, floorHit = false, roofFloorHit = false, ceilFloorHit = false;
  if (!hasGrant()) {{
    eRoof = hasRoof ? Math.round(roofMinRate(qRoof) * qRoof) : 0;
    eCeil = hasCeil ? Math.round(ceilMinRate(qCeil) * qCeil) : 0;
    grantReceived = 0;
  }} else {{
    const remK = getRemK();
    grantReceived = remK !== null ? Math.min(fTot, remK) : fTot;
    if (fTot > 0) {{ eRoof = grantReceived * fRoof / fTot; eCeil = grantReceived * fCeil / fTot; }}
    if (hasRoof && qRoof > 0) {{
      const minR = Math.round(roofMinRate(qRoof) * qRoof);
      if (eRoof < minR) {{ eRoof = minR; floorHit = true; roofFloorHit = true; }}
    }}
    if (hasCeil && qCeil > 0) {{
      const minC = Math.round(ceilMinRate(qCeil) * qCeil);
      if (eCeil < minC) {{ eCeil = minC; floorHit = true; ceilFloorHit = true; }}
    }}
    const ceilFloor = hasCeil && qCeil > 0 ? Math.round(ceilMinRate(qCeil) * qCeil) : 0;
    eRoof = Math.min(eRoof, lRoof);
    eCeil = Math.min(eCeil, Math.max(lCeil, ceilFloor));
  }}

  // eWin = listed price always; grant reduces clientPays directly via grantReceived
  const eWin = lWin;
  const eTotal = eRoof + eCeil + eWin;
  const grantUsed = Math.min(grantReceived, eTotal);
  const clientPays = Math.max(DOPRAVA, eTotal + DOPRAVA - grantReceived);
  const dRoof  = lRoof > 0 ? Math.max(0, (1 - eRoof / lRoof)) * 100 : 0;
  const dCeil  = lCeil > 0 ? Math.max(0, (1 - eCeil / lCeil)) * 100 : 0;

  // Per-type grant per m² for windows (uniform across all m²)
  const grantPerM2Win = (hasGrant() && fTot > 0 && qWinTot > 0)
    ? grantReceived * fWin / (fTot * qWinTot)
    : 0;
  document.getElementById('inp_elig_roof').value    = Math.round(eRoof);
  document.getElementById('inp_elig_ceiling').value = Math.round(eCeil);
  document.getElementById('inp_elig_win_a').value   = Math.max(0, Math.round((WIN_RATES.a - grantPerM2Win) * qWinA));
  document.getElementById('inp_elig_win_b').value   = Math.max(0, Math.round((WIN_RATES.b - grantPerM2Win) * qWinB));
  document.getElementById('inp_elig_win_c').value   = Math.max(0, Math.round((WIN_RATES.c - grantPerM2Win) * qWinC));
  document.getElementById('inp_disc_roof').value    = dRoof.toFixed(4);
  document.getElementById('inp_disc_ceiling').value = dCeil.toFixed(4);
  document.getElementById('inp_grant_amount').value = Math.round(grantUsed);

  const q5100 = hasCeil ? (parseFloat(document.getElementById('qty_5100').value) || 0) : 0;
  const q5101 = hasCeil ? (parseFloat(document.getElementById('qty_5101').value) || 0) : 0;
  const pochoziEff = q5100 + q5101 * 0.625;
  const pochoziPrice = Math.round(pochoziEff * 750 * 0.88);
  document.getElementById('pv-pochozi').textContent = fmt(pochoziPrice);
  document.getElementById('pv-pochozi-row').classList.toggle('hidden', !hasCeil || (q5100 === 0 && q5101 === 0));

  const grandTotal = eTotal + DOPRAVA + pochoziPrice + blindsCost + netsCost;
  const dTotal = lTotal > 0 ? Math.max(0, (1 - eTotal / lTotal)) * 100 : 0;
  document.getElementById('pv-disc').textContent = dTotal.toFixed(1) + ' %';
  document.getElementById('pv-disc-row').classList.toggle('hidden', dTotal < 0.5);

  const grantOn = hasGrant();
  document.getElementById('pv-base').textContent  = fmt(lTotal + blindsCost + netsCost);
  document.getElementById('pv-windows').textContent = fmt(lWin + blindsCost + netsCost);
  document.getElementById('pv-windows-row').classList.toggle('hidden', !hasWin || lWin === 0);
  document.getElementById('pv-total').textContent = fmt(grandTotal);
  document.getElementById('pv-grant-row').classList.toggle('hidden', !grantOn);
  document.getElementById('pv-client-row').classList.toggle('hidden', !grantOn);
  if (grantOn) {{
    document.getElementById('pv-grant').textContent  = fmt(grantReceived);
    document.getElementById('pv-client').textContent = fmt(clientPays + pochoziPrice + blindsCost + netsCost);
  }}

  if (hasRoof && qRoof > 0) {{
    const el = document.getElementById('thickness_roof');
    if (!el.value) el.placeholder = (eRoof / qRoof) < 1500 ? '30' : '35';
  }}

  function showRate(rowId, valId, qty, elig, hit) {{
    const el = document.getElementById(rowId);
    if (qty > 0) {{
      const rate = Math.round(elig / qty);
      let txt = new Intl.NumberFormat('cs-CZ').format(rate) + ' K\u010d/m\u00b2';
      if (hit) {{ txt += ' \u2014 minim\u00e1ln\u00ed cena'; el.style.color = '#c8670a'; el.style.fontWeight = '600'; }}
      else {{ el.style.color = ''; el.style.fontWeight = ''; }}
      document.getElementById(valId).textContent = txt;
      el.classList.remove('hidden');
    }} else {{
      el.classList.add('hidden');
    }}
  }}
  showRate('pv-rate-roof-row', 'pv-rate-roof', hasRoof ? qRoof : 0, eRoof, roofFloorHit);
  showRate('pv-rate-ceil-row', 'pv-rate-ceil', hasCeil ? qCeil : 0, eCeil, ceilFloorHit);

  const winOnly  = hasWin && !hasRoof && !hasCeil;
  const splitVal = winOnly ? '80-20' : (getSplit() || '');
  const splitBase = grandTotal;
  if (splitVal) {{
    const [a, b] = splitVal.split('-').map(Number);
    document.getElementById('pv-zaloha-label').textContent   = 'Z\u00e1loha (' + a + ' %)';
    document.getElementById('pv-doplatek-label').textContent = 'Doplatek (' + b + ' %)';
    document.getElementById('pv-zaloha').textContent         = fmt(Math.round(splitBase * a / 100));
    document.getElementById('pv-doplatek').textContent       = fmt(Math.round(splitBase * b / 100));
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
  const qWinA = hasWin  ? (parseFloat(document.getElementById('qty_win_a').value) || 0) : 0;
  const qWinB = hasWin  ? (parseFloat(document.getElementById('qty_win_b').value) || 0) : 0;
  const qWinC = hasWin  ? (parseFloat(document.getElementById('qty_win_c').value) || 0) : 0;
  const qWinTot = qWinA + qWinB + qWinC;
  const winOnly = hasWin && !hasRoof && !hasCeil;
  const split = winOnly ? '80-20' : getSplit();
  const eTotal = parseFloat(document.getElementById('inp_elig_roof').value    || 0)
               + parseFloat(document.getElementById('inp_elig_ceiling').value || 0)
               + parseFloat(document.getElementById('inp_elig_win_a').value   || 0)
               + parseFloat(document.getElementById('inp_elig_win_b').value   || 0)
               + parseFloat(document.getElementById('inp_elig_win_c').value   || 0);
  const terminDays = document.querySelector('input[name=termin_days]:checked');
  const terminZalohy2 = document.querySelector('input[name=termin_zalohy_2]:checked');
  const clientPhone = (document.getElementById('client_phone')?.value || '').replace(/[\s\-().+]/g, '');
  const phoneOk = /^\d{{9,}}$/.test(clientPhone);
  document.getElementById('submitBtn').disabled = !(
    (!hasRoof || (matRoof && qRoof > 0)) &&
    (!hasCeil || (matCeil && qCeil > 0)) &&
    (!hasWin  || qWinTot > 0) && split && eTotal > 0 && terminDays && terminZalohy2 && phoneOk
  );
}}

function winTotalM2() {{
  return (parseFloat(document.getElementById('qty_win_a').value) || 0)
       + (parseFloat(document.getElementById('qty_win_b').value) || 0)
       + (parseFloat(document.getElementById('qty_win_c').value) || 0);
}}

function onWinQtyChange() {{
  const tot = winTotalM2();
  ['qty_blinds', 'qty_nets'].forEach(function(id) {{
    const el = document.getElementById(id);
    if (!el.dataset.userSet) el.value = tot || '';
  }});
  calc();
}}

function onBlindsNetsChange(which) {{
  const chkId   = which === 'blinds' ? 'chk_blinds'   : 'chk_nets';
  const secId   = which === 'blinds' ? 'blinds-qty-section' : 'nets-qty-section';
  const qtyId   = which === 'blinds' ? 'qty_blinds'   : 'qty_nets';
  const checked = document.getElementById(chkId).checked;
  document.getElementById(secId).classList.toggle('hidden', !checked);
  if (checked) {{
    const el = document.getElementById(qtyId);
    if (!el.dataset.userSet) el.value = winTotalM2() || '';
  }}
  calc();
}}

document.getElementById('mainForm').addEventListener('change', () => {{ calc(); checkSubmit(); updateStavebni(); updatePopisDila(); }});
</script>
</body>
</html>"""


@app.post('/order-form', response_class=HTMLResponse)
def order_form_post(
    order_id: int = Form(...),
    key: str = Form(...),
    test: int = Form(0),
    has_roof: str = Form(''),
    has_ceiling: str = Form(''),
    has_windows: str = Form(''),
    material_roof: str = Form(None),
    material_ceiling: str = Form(None),
    qty_m2_roof: str = Form(''),
    qty_m2_ceiling: str = Form(''),
    qty_win_a: str = Form(''),
    qty_win_b: str = Form(''),
    qty_win_c: str = Form(''),
    has_blinds: str = Form(''),
    qty_blinds: str = Form(''),
    has_nets: str = Form(''),
    qty_nets: str = Form(''),
    eligible_roof: float = Form(0),
    eligible_ceiling: float = Form(0),
    eligible_win_a: float = Form(0),
    eligible_win_b: float = Form(0),
    eligible_win_c: float = Form(0),
    discount_pct_roof: float = Form(0),
    discount_pct_ceiling: float = Form(0),
    grant_amount: float = Form(0),
    split: str = Form(None),
    extra_5000a: str = Form(''),
    extra_5000b: str = Form(''),
    extra_5000c: str = Form(''),
    qty_5100: str = Form(''),
    qty_5101: str = Form(''),
    addr_same: str = Form(''),
    adresa_realizace: str = Form(''),
    popis_dila: str = Form(''),
    thickness_roof: str = Form(''),
    thickness_ceiling: str = Form(''),
    termin_dokonceni: str = Form(''),
    termin_zalohy_2: str = Form(None),
    stavebni_pripravenost: str = Form(''),
    client_name: str = Form(''),
    client_street: str = Form(''),
    client_zip: str = Form(''),
    client_city: str = Form(''),
    client_email: str = Form(''),
    client_phone: str = Form(''),
    client_dob: str = Form(''),
):
    if key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail='Unauthorized')

    import traceback as _tb
    try:
        return _order_form_post_inner(
            order_id=order_id, key=key, test=test,
            has_roof=has_roof, has_ceiling=has_ceiling, has_windows=has_windows,
            material_roof=material_roof, material_ceiling=material_ceiling,
            qty_m2_roof=qty_m2_roof, qty_m2_ceiling=qty_m2_ceiling,
            qty_win_a=qty_win_a, qty_win_b=qty_win_b, qty_win_c=qty_win_c,
            has_blinds=has_blinds, qty_blinds=qty_blinds, has_nets=has_nets, qty_nets=qty_nets,
            eligible_roof=eligible_roof, eligible_ceiling=eligible_ceiling,
            eligible_win_a=eligible_win_a, eligible_win_b=eligible_win_b, eligible_win_c=eligible_win_c,
            discount_pct_roof=discount_pct_roof, discount_pct_ceiling=discount_pct_ceiling,
            grant_amount=grant_amount, split=split,
            extra_5000a=extra_5000a, extra_5000b=extra_5000b, extra_5000c=extra_5000c,
            qty_5100=qty_5100, qty_5101=qty_5101,
            addr_same=addr_same, adresa_realizace=adresa_realizace, popis_dila=popis_dila,
            thickness_roof=thickness_roof, thickness_ceiling=thickness_ceiling,
            termin_dokonceni=termin_dokonceni, termin_zalohy_2=termin_zalohy_2,
            stavebni_pripravenost=stavebni_pripravenost,
            client_name=client_name, client_street=client_street, client_zip=client_zip,
            client_city=client_city, client_email=client_email, client_phone=client_phone,
            client_dob=client_dob,
        )
    except HTTPException:
        raise
    except Exception:
        tb = _tb.format_exc()
        logging.error('order_form_post error:\n' + tb)
        import html as _html
        return HTMLResponse(status_code=500, content=f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Chyba</title></head>
<body style="font-family:monospace;padding:24px;background:#fff8f8;">
<h2 style="color:#c00;">Chyba při zpracování objednávky</h2>
<pre style="background:#f5f5f5;padding:16px;border-radius:6px;overflow:auto;font-size:13px;">{_html.escape(tb)}</pre>
</body></html>""")


def _order_form_post_inner(
    order_id, key, test,
    has_roof, has_ceiling, has_windows,
    material_roof, material_ceiling,
    qty_m2_roof, qty_m2_ceiling,
    qty_win_a, qty_win_b, qty_win_c,
    has_blinds, qty_blinds, has_nets, qty_nets,
    eligible_roof, eligible_ceiling,
    eligible_win_a, eligible_win_b, eligible_win_c,
    discount_pct_roof, discount_pct_ceiling,
    grant_amount, split,
    extra_5000a, extra_5000b, extra_5000c,
    qty_5100, qty_5101,
    addr_same, adresa_realizace, popis_dila,
    thickness_roof, thickness_ceiling,
    termin_dokonceni, termin_zalohy_2,
    stavebni_pripravenost,
    client_name, client_street, client_zip,
    client_city, client_email, client_phone,
    client_dob,
):
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

    def line_name_with_thickness(prod_name: str, t: str) -> str:
        if not t:
            return prod_name
        if re.search(r'\d+\s*cm', prod_name):
            return re.sub(r'\d+\s*cm', f'{t} cm', prod_name)
        return f'{prod_name} - tloušťka {t} cm'

    if has_roof and material_roof:
        ref = REF_MAP[material_roof] + 'A'
        qty = float(qty_m2_roof or 0)
        prods = call('product.product', 'search_read',
                     [[['default_code', '=', ref]]], {'fields': ['id', 'name'], 'limit': 1})
        if not prods:
            raise HTTPException(status_code=400, detail=f'Produkt [{ref}] nenalezen v Odoo')
        unit_price_incl = (eligible_roof / qty) / (1 - COSMETIC_DISC / 100) if qty else 0
        t_roof = (thickness_roof or '').strip()
        if not t_roof:
            rate = eligible_roof / qty if qty else 0
            t_roof = '30' if rate < 1500 else '35'
        order_lines.append((0, 0, {
            'product_id': prods[0]['id'],
            'name': line_name_with_thickness(prods[0].get('name', ''), t_roof),
            'product_uom_qty': qty,
            'price_unit': round(unit_price_incl / TAX_RATE, 2),
            'discount': COSMETIC_DISC,
        }))

    if has_ceiling and material_ceiling:
        ref = REF_MAP[material_ceiling] + 'B'
        qty = float(qty_m2_ceiling or 0)
        prods = call('product.product', 'search_read',
                     [[['default_code', '=', ref]]], {'fields': ['id', 'name'], 'limit': 1})
        if not prods:
            raise HTTPException(status_code=400, detail=f'Produkt [{ref}] nenalezen v Odoo')
        unit_price_incl = (eligible_ceiling / qty) / (1 - COSMETIC_DISC / 100) if qty else 0
        t_ceil = (thickness_ceiling or '').strip() or '25'
        order_lines.append((0, 0, {
            'product_id': prods[0]['id'],
            'name': line_name_with_thickness(prods[0].get('name', ''), t_ceil),
            'product_uom_qty': qty,
            'price_unit': round(unit_price_incl / TAX_RATE, 2),
            'discount': COSMETIC_DISC,
        }))

    if has_windows:
        win_prods = call('product.product', 'search_read',
                         [[['default_code', 'in', ['4000A', '4000B', '4000C']]]],
                         {'fields': ['id', 'default_code'], 'limit': 3})
        win_map = {p['default_code']: p for p in win_prods}
        WIN_LISTED = {'4000A': 9000, '4000B': 9900, '4000C': 10800}
        for code, qty_str in [
            ('4000A', qty_win_a),
            ('4000B', qty_win_b),
            ('4000C', qty_win_c),
        ]:
            qty = float(qty_str or 0)
            if qty > 0 and code in win_map:
                listed_rate = WIN_LISTED[code]
                order_lines.append((0, 0, {
                    'product_id': win_map[code]['id'],
                    'product_uom_qty': qty,
                    'price_unit': round(listed_rate / (1 - COSMETIC_DISC / 100) / TAX_RATE, 2),
                    'discount': COSMETIC_DISC,
                }))
        qty_blinds_f = float(qty_blinds or 0) if has_blinds else 0.0
        qty_nets_f   = float(qty_nets   or 0) if has_nets   else 0.0
        if qty_blinds_f > 0:
            bp = call('product.product', 'search_read',
                      [[['default_code', '=', '4001A']]], {'fields': ['id'], 'limit': 1})
            if bp:
                order_lines.append((0, 0, {
                    'product_id': bp[0]['id'],
                    'product_uom_qty': qty_blinds_f,
                    'price_unit': round(1000 / (1 - COSMETIC_DISC / 100) / TAX_RATE, 2),
                    'discount': COSMETIC_DISC,
                }))
        if qty_nets_f > 0:
            np_ = call('product.product', 'search_read',
                       [[['default_code', '=', '4001B']]], {'fields': ['id'], 'limit': 1})
            if np_:
                order_lines.append((0, 0, {
                    'product_id': np_[0]['id'],
                    'product_uom_qty': qty_nets_f,
                    'price_unit': round(1000 / (1 - COSMETIC_DISC / 100) / TAX_RATE, 2),
                    'discount': COSMETIC_DISC,
                }))

    if doprava_prods:
        order_lines.append((0, 0, {
            'product_id': doprava_prods[0]['id'],
            'product_uom_qty': 1,
            'price_unit': round(doprava_price / TAX_RATE, 2),
            'discount': 0,
        }))

    # Pochozí plocha / lávka pricing (ceiling add-ons)
    qty_5100_f = float(qty_5100 or 0)
    qty_5101_f = float(qty_5101 or 0)
    pochozi_eff_m2 = (qty_5100_f + qty_5101_f * 0.625) if has_ceiling else 0.0
    pochozi_total_incl = round(pochozi_eff_m2 * 750 * 0.88)

    # Extra add-on products (no grant/discount involvement)
    extra_needed = []
    if has_roof and extra_5000a: extra_needed.append('5000A')
    if has_roof and extra_5000b: extra_needed.append('5000B')
    if has_roof and extra_5000c: extra_needed.append('5000C')
    if has_ceiling and qty_5100_f > 0: extra_needed.append('5100')
    if has_ceiling and qty_5101_f > 0: extra_needed.append('5101')
    if extra_needed:
        extra_prods = call('product.product', 'search_read',
                           [[['default_code', 'in', extra_needed]]],
                           {'fields': ['id', 'default_code', 'lst_price'], 'limit': 10})
        extra_map = {p['default_code']: p for p in extra_prods}
        for code in ['5000A', '5000B', '5000C']:
            if code in extra_map:
                order_lines.append((0, 0, {
                    'product_id': extra_map[code]['id'],
                    'product_uom_qty': 1,
                    'price_unit': extra_map[code].get('lst_price', 0),
                    'discount': 0,
                }))
        for code, qty_f, conv in [('5100', qty_5100_f, 1.0), ('5101', qty_5101_f, 0.625)]:
            if code in extra_map and qty_f > 0:
                order_lines.append((0, 0, {
                    'product_id': extra_map[code]['id'],
                    'product_uom_qty': qty_f,
                    'price_unit': round(750 * conv / TAX_RATE, 2),
                    'discount': 12,
                }))

    blinds_cost = round(1000 * (float(qty_blinds or 0) if has_blinds else 0.0))
    nets_cost   = round(1000 * (float(qty_nets   or 0) if has_nets   else 0.0))
    total = eligible_roof + eligible_ceiling + eligible_win_a + eligible_win_b + eligible_win_c + blinds_cost + nets_cost + doprava_price + pochozi_total_incl
    zaloha   = round(total * split_pct[0] / 100)
    doplatek = round(total * split_pct[1] / 100)
    client_pays = round(total - grant_amount)

    addr_value = 'shodné s trvalou adresou' if addr_same else (adresa_realizace or '')
    insul_area = (float(qty_m2_roof or 0) if has_roof else 0) + (float(qty_m2_ceiling or 0) if has_ceiling else 0)

    # If the order was already confirmed (state='sale'), reset it to draft first so we can
    # replace its lines; confirmed orders reject the (5,0,0) line-deletion command.
    current_state = call('sale.order', 'read', [[order_id]], {'fields': ['state']})[0]['state']
    if current_state == 'sale':
        call('sale.order', 'action_cancel', [[order_id]])
        call('sale.order', 'action_draft', [[order_id]])

    call('sale.order', 'write', [[order_id], {
        'order_line': order_lines,
        'x_studio_zaloha_kc': zaloha,
        'x_studio_doplatek_kc': doplatek,
        'x_studio_vyse_dotace_kc': round(grant_amount),
        'x_studio_cena_po_odecteni_dotace': max(0, client_pays),
        'x_studio_float_field_45q_1jsh2tmcd': insul_area,
        'x_studio_adresa_realizace': addr_value,
        'x_studio_popis_dila': popis_dila or '',
        'x_studio_termin_dokonceni_2': termin_dokonceni or '',
        'x_studio_termin_zalohy_2': termin_zalohy_2 or '',
        'x_studio_stavebni_pripravenost': stavebni_pripravenost or '',
        'x_studio_datum_podpisu_smlouvy': date.today().isoformat(),
    }])

    # Generate contract PDF immediately after saving
    updated = call('sale.order', 'read', [[order_id]], {'fields': [
        'name', 'partner_id', 'amount_total', 'amount_untaxed', 'amount_tax', 'order_line',
        'x_studio_adresa_realizace', 'x_studio_popis_dila', 'user_id', 'opportunity_id',
        'x_studio_zaloha_kc', 'x_studio_termin_zalohy_2',
        'x_studio_doplatek_kc', 'x_studio_termin_dokonceni_2',
        'x_studio_stavebni_pripravenost', 'x_studio_datum_podpisu_smlouvy',
        'x_studio_float_field_45q_1jsh2tmcd', 'x_studio_vyse_dotace_kc',
        'x_studio_cena_po_odecteni_dotace',
    ]})[0]

    # Look up CRM lead fields for sign request annotation
    _crm_opportunity = ''
    _crm_tipar = ''
    _crm_obchodnik = ''
    if updated.get('opportunity_id'):
        _lead = call('crm.lead', 'read', [[updated['opportunity_id'][0]]],
                     {'fields': ['name', 'user_id', 'x_studio_tipar_3']})
        if _lead:
            _lead = _lead[0]
            _crm_opportunity = _lead.get('name') or ''
            _crm_obchodnik   = (_lead.get('user_id') or [None, ''])[1] or ''
            _crm_tipar       = (_lead.get('x_studio_tipar_3') or [None, ''])[1] or ''
    partner_id_val = updated['partner_id'][0]
    partner = call('res.partner', 'read', [[partner_id_val]], {'fields': [
        'name', 'street', 'zip', 'city', 'email', 'phone', 'x_studio_datum_narozeni',
    ]})[0]
    patch = {}
    if client_name:
        partner['name'] = client_name
    if client_street:
        partner['street'] = client_street
    if client_zip:
        partner['zip'] = client_zip
    if client_city:
        partner['city'] = client_city
    if client_email:
        patch['email'] = client_email
    if not partner.get('phone') and client_phone:
        patch['phone'] = client_phone
    if not partner.get('x_studio_datum_narozeni') and client_dob:
        try:
            parts = client_dob.strip().replace('/', '.').split('.')
            d, m, y = parts[0], parts[1], parts[2]
            patch['x_studio_datum_narozeni'] = f'{y}-{m.zfill(2)}-{d.zfill(2)}'
        except Exception:
            pass
    if patch:
        call('res.partner', 'write', [[partner_id_val], patch])
        partner.update(patch)
    if not partner.get('email') or '@' not in partner['email']:
        raise HTTPException(status_code=400, detail='E-mail klienta je povinný pro odeslání smlouvy k podpisu.')
    lines = call('sale.order.line', 'read', [updated['order_line']], {'fields': [
        'product_id', 'name', 'product_uom_qty', 'product_uom_id',
        'price_unit', 'price_subtotal', 'discount', 'display_type', 'is_downpayment',
    ]})
    pdf_bytes = generate_contract(updated, partner, lines)
    _client_name = partner.get('name', '')
    _doc_prefix = f'{_client_name} - {updated["name"]}' if _client_name else updated['name']
    filename = f"Smlouva_{_doc_prefix}.pdf"
    call('ir.attachment', 'create', [{
        'name': filename,
        'res_model': 'sale.order',
        'res_id': order_id,
        'type': 'binary',
        'datas': base64.b64encode(pdf_bytes).decode(),
        'mimetype': 'application/pdf',
    }])

    # Get salesperson's partner_id so they become a follower on the sign request
    salesperson_partner_id = None
    if updated.get('user_id'):
        sp_user = call('res.users', 'read', [[updated['user_id'][0]]], {'fields': ['partner_id']})
        if sp_user:
            salesperson_partner_id = sp_user[0]['partner_id'][0]

    sign_url = None
    sign_note = ''
    try:
        _req_id, sign_url = _create_sign_request(call, pdf_bytes, updated['name'],
                             partner_id_val, partner.get('email', ''),
                             company_partner_id=_SIGN_TEST_PARTNER_ID if test else _SIGN_COMPANY_PARTNER_ID,
                             company_email=_SIGN_TEST_EMAIL if test else _SIGN_COMPANY_EMAIL,
                             salesperson_partner_id=salesperson_partner_id,
                             client_name=partner.get('name', ''))
        if _crm_opportunity or _crm_tipar or _crm_obchodnik:
            call('sign.request', 'write', [[_req_id], {
                'x_crm_opportunity': _crm_opportunity,
                'x_crm_tipar':       _crm_tipar,
                'x_crm_obchodnik':   _crm_obchodnik,
            }])
        call('sale.order', 'write', [[order_id], {'state': 'sent'}])
        call('sale.order', 'message_post', [[order_id]], {
            'body': (
                'Smlouva odeslána k podpisu. '
                f'Čeká na podpis: {partner.get("name", "")} (Objednatel), '
                'Lukáš Najman, LUNASTAV CZ s.r.o. (Zhotovitel).'
            ),
            'message_type': 'comment',
            'subtype_xmlid': 'mail.mt_note',
        })
    except Exception as exc:
        import html as _html
        sign_note = f'<p style="color:#c55;font-size:13px;margin:8px 0 0;">Chyba p&#345;i odesílání k podpisu: {_html.escape(str(exc))}</p>'

    odoo_order_url = f'{ODOO_URL}/odoo/sales/{order_id}'

    sign_block = ''
    if sign_url:
        qr_html = ''
        try:
            import segno as _segno
            buf = io.BytesIO()
            _segno.make(sign_url, error='H').save(buf, kind='svg', scale=6, border=2)
            qr_svg = buf.getvalue().decode('utf-8')
            qr_html = f"""<p style="margin-top:28px;color:#888;font-size:13px;">nebo naskenujte QR kód telefonem:</p>
    <div style="display:inline-block;padding:12px;background:#fff;border:1px solid #e0e0e0;border-radius:8px;margin-top:4px;">
      {qr_svg}
    </div>"""
        except Exception:
            pass
        sign_block = f"""
    <a href="{sign_url}" target="_blank"
       style="display:inline-block;margin-top:20px;padding:13px 28px;background:#c8a840;color:#fff;
              text-decoration:none;border-radius:6px;font-size:15px;font-weight:bold;">Podepsat smlouvu</a>
    {qr_html}"""

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Objednávka vytvořena</title></head>
<body style="font-family:Arial,sans-serif;text-align:center;padding:60px;color:#333;background:#f9f9f9;">
  <div style="background:#fff;border-radius:8px;padding:40px;max-width:520px;margin:auto;box-shadow:0 2px 8px rgba(0,0,0,.1);">
    <div style="font-size:56px;margin-bottom:12px;">&#10003;</div>
    <h2 style="margin:0 0 8px;">Objednávka vytvořena</h2>
    <p style="color:#555;font-size:14px;margin:0;">{updated['name']}</p>
    {sign_note}
    {sign_block}
    <p style="margin-top:24px;"><a href="{odoo_order_url}" style="color:#aaa;font-size:13px;">Zpět do Odoo</a></p>
  </div>

</body></html>"""

# @app.get('/verify/{sign_id}/{partner_id}/{token}', response_class=HTMLResponse)
# def verify_get(sign_id: int, partner_id: int, token: str): ...
#
# @app.post('/verify/{sign_id}/{partner_id}/{token}', response_class=HTMLResponse)
# async def verify_post(sign_id: int, partner_id: int, token: str, code: str = Form(...)): ...


@app.get('/health')
def health():
    return {'status': 'ok'}

@app.get('/podpisano', response_class=HTMLResponse)
def sign_success():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dokument podepsán – LUNASTAV</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f5f5f5;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .card {
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.10);
    padding: 48px 40px;
    max-width: 480px;
    width: 100%;
    text-align: center;
  }
  .icon {
    width: 72px; height: 72px;
    background: #e8f5e9;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    margin: 0 auto 24px;
    font-size: 36px;
  }
  h1 { font-size: 1.6rem; color: #1a1a1a; margin-bottom: 12px; }
  p  { font-size: 1rem; color: #555; line-height: 1.6; margin-bottom: 8px; }
  .logo { margin-top: 36px; }
  .logo a { color: #c8a840; font-weight: 600; text-decoration: none; font-size: 1.05rem; }
  .logo a:hover { text-decoration: underline; }
  .divider { border: none; border-top: 1px solid #eee; margin: 32px 0; }
  .contact { font-size: 0.9rem; color: #888; }
  .contact a { color: #555; }
</style>
</head>
<body>
<div class="card">
  <div class="icon">&#10003;</div>
  <h1>Dokument byl úspěšně podepsán</h1>
  <p>Děkujeme! Podepsaný dokument obdržíte e-mailem.</p>
  <hr class="divider">
  <div class="logo">
    <a href="https://www.lunastav.cz/">www.lunastav.cz</a>
  </div>
</div>
</body>
</html>""")
