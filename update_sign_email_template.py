"""
Patch Odoo Sign email templates:
  id=1289  sign_template_mail_request  — invitation email (intercepts link → SMS verify page)
  id=1291  sign_template_mail_completed — completion email (Czech body, no button)

Run after any Odoo SaaS update that resets these views:
    python update_sign_email_template.py
"""
RAILWAY_URL = 'https://lunastav-orders-production.up.railway.app'
import os, xmlrpc.client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'contract_service', '.env'))
URL, DB, USER, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_USER'], os.environ['ODOO_API_KEY']
uid = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common').authenticate(DB, USER, KEY, {})
m   = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
def call(model, method, args, kw=None):
    return m.execute_kw(DB, uid, KEY, model, method, args, kw or {})

NEW_ARCH = """\
<t t-name="sign.sign_template_mail_completed">
<table border="0" cellpadding="0" style="background-color: white; padding: 0px; border-collapse:separate; width: 100%;">
    <tr><td valign="top">
        <p>Dobrý den, <t t-out="recipient_name"/>,</p>
        <p>Děkujeme Vám za projevenou důvěru a za uzavření objednávky č.&nbsp;<strong><t t-out="record.reference"/></strong> s naší společností.</p>
        <p>V příloze Vám zasíláme podepsanou smlouvu o dílo. Naše dotační oddělení nyní zahájí přípravu veškeré dokumentace potřebné k podání žádosti o dotaci z programu Nová zelená úsporám Light. Po schválení dotace se s Vámi spojíme a domluvíme další postup.</p>
        <p>V případě jakýchkoliv dotazů se na nás neváhejte obrátit.</p>
        <p>
            <strong>Důležité kontakty:</strong><br/>
            Dotační oddělení: <a href="mailto:dotace@lunastav.cz" style="color:#428BCA;">dotace@lunastav.cz</a><br/>
            Realizační oddělení: <a href="mailto:realizace@lunastav.cz" style="color:#428BCA;">realizace@lunastav.cz</a><br/>
            Fakturační oddělení: <a href="mailto:faktury@lunastav.cz" style="color:#428BCA;">faktury@lunastav.cz</a>
        </p>
        <p>Děkujeme za Vaši důvěru a těšíme se na spolupráci.</p>
    </td></tr>
</table>
</t>"""

call('ir.ui.view', 'write', [[1291], {'arch_db': NEW_ARCH}])
print("Updated sign completion email template (id=1291).")

# ── Sign invitation email (id=1289) ───────────────────────────────────────────
# For P2 orders the sign link is replaced with our SMS verification page.
# t-att-href takes a plain Python expression (no {{ }} needed).
# t-attf-style uses {{ }} for QWeb interpolation (plain string, not f-string).
INVITE_ARCH = """\
<t t-name="sign.sign_template_mail_request">
<table border="0" cellpadding="0" style="background-color: white; padding: 0px; border-collapse:separate; width: 100%;">
    <tr><td valign="top">
        <p>Dobrý den, <t t-out="record.partner_id.name"/>,</p>
        <p>žádáme Vás o podpis smlouvy o dílo č. <strong><t t-out="record.sign_request_id.reference"/></strong>.</p>
        <p>Pro přístup k dokumentu klikněte na tlačítko níže.</p>
        <p style="color:#888;">Pokud jste smlouvu již podepsal(a), nemusíte provádět žádné další kroky.</p>
    </td></tr>
    <tr><td valign="top">
        <div style="margin:16px auto; text-align:center;">
            <a t-att-href="link" t-attf-style="padding: 8px 16px 8px 16px; border-radius: 3px; background-color: {{record.communication_company_id.email_secondary_color or '#875A7B'}}; text-align:center; text-decoration:none; color: {{record.communication_company_id.email_primary_color or '#FFFFFF'}};">
                Podepsat smlouvu
            </a>
        </div>
    </td></tr>
    <tr><td valign="top">
        <div style="opacity: 0.7; font-size: 13px;">
            <strong>Upozornění:</strong> Tento e-mail nepřeposílejte dalším osobám!<br/>
            Mohly by získat přístup k dokumentu a podepsat jej Vaším jménem.
        </div>
        <br/>
        <div style="opacity: 0.7;"><small>Pokud si nepřejete dostávat připomínky k tomuto dokumentu,
            <a t-att-href="link_cancel" style="color:#000; text-decoration:none; opacity:0.7;"><span style="text-decoration:underline;">klikněte zde</span> pro zrušení.</a></small>
        </div>
    </td></tr>
</table>
<br/>
<t t-out="user_signature"/>
</t>"""

call('ir.ui.view', 'write', [[1289], {'arch_db': INVITE_ARCH}])
print("Updated sign invitation email template (id=1289).")
