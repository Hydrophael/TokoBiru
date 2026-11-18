import os
import smtplib
import ssl
from email.message import EmailMessage
from html import escape as html_escape

from tokobiru.core.config import (
    BASE_DIR,
    RESET_CODE_MINUTES,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_TIMEOUT,
    SMTP_USER,
)


def send_email(to, subject, body, html=None, inline_images=None):
    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
        for cid, data in (inline_images or {}).items():
            message.get_payload()[1].add_related(data, "image", "png", cid=f"<{cid}>", disposition="inline")
    use_ssl = SMTP_PORT == 465
    context = ssl.create_default_context()
    if use_ssl:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT)
    with server:
        if not use_ssl:
            server.starttls(context=context)
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)


def reset_email_text(name, code):
    return (f"Halo {name},\n\n"
            f"Kode reset password TokoBiru Anda: {code}\n\n"
            f"Kode berlaku {RESET_CODE_MINUTES} menit dan hanya bisa dipakai sekali.\n"
            "Jangan bagikan kode ini kepada siapa pun, termasuk yang mengaku dari TokoBiru.\n"
            "Jika Anda tidak merasa memintanya, abaikan email ini; password Anda tidak berubah.\n")


EMAIL_LOGO_FILE = os.path.join(BASE_DIR, "static", "icons", "icon-192.png")


def load_email_logo():
    try:
        with open(EMAIL_LOGO_FILE, "rb") as f:
            return f.read()
    except OSError:
        return None


def reset_email_html(name, code, logo_cid=None):
    name = html_escape(name)
    mark = (f'<td style="padding-right:10px"><img src="cid:{logo_cid}" width="40" height="40" alt="" '
            'style="display:block;border:0;border-radius:11px"></td>') if logo_cid else ""
    brand = ('<table role="presentation" cellpadding="0" cellspacing="0"><tr>' + mark +
             '<td style="font-size:22px;font-weight:bold;color:#0c2342;letter-spacing:-0.5px">TokoBiru</td></tr></table>')
    return f"""<!DOCTYPE html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:24px 12px;background:#eef4fb;font-family:Arial,Helvetica,sans-serif;color:#0c2342">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden">
<tr><td style="border-top:4px solid #0b5fc4;padding:20px 28px 0">{brand}</td></tr>
<tr><td style="padding:28px">
<p style="margin:0 0 12px;font-size:16px;line-height:1.5">Halo {name},</p>
<p style="margin:0 0 16px;font-size:16px;line-height:1.5">Gunakan kode ini untuk membuat password baru:</p>
<p style="margin:0 0 8px;padding:16px;background:#e3eefc;border-radius:10px;text-align:center;font-size:32px;font-weight:bold;font-family:Consolas,Menlo,monospace;color:#0a4ea3"><span style="letter-spacing:6px;-webkit-user-select:all;user-select:all">{code}</span></p>
<p style="margin:0 0 20px;font-size:13px;line-height:1.5;color:#566f89;text-align:center">Ketuk dan tahan kode di atas, lalu pilih Salin. Atau salin dari sini: <span style="font-family:Consolas,Menlo,monospace;font-size:15px;color:#0c2342;-webkit-user-select:all;user-select:all">{code}</span></p>
<p style="margin:0 0 12px;font-size:14px;line-height:1.6">Kode berlaku {RESET_CODE_MINUTES} menit dan hanya bisa dipakai sekali. Jangan bagikan kode ini kepada siapa pun, termasuk yang mengaku dari TokoBiru.</p>
<p style="margin:0;font-size:14px;line-height:1.6;color:#566f89">Jika Anda tidak merasa memintanya, abaikan email ini; password Anda tidak berubah.</p>
</td></tr></table>
</td></tr></table>
</body></html>"""