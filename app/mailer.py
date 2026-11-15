"""E-mail (código de acesso e corte pronto) pelo SMTP da Hostinger."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from typing import Any as Config

log = logging.getLogger("perfilai.mail")

MOLDE = """<!doctype html><html><body style="margin:0;background:#0b0b10;font-family:Arial,Helvetica,sans-serif;color:#f4f4f6">
<div style="max-width:520px;margin:0 auto;padding:32px 24px">
<div style="font-size:22px;font-weight:800;letter-spacing:-.5px;margin-bottom:24px">Perfil<span style="color:#c06bff">aí</span></div>
{corpo}
<p style="color:#8b8b98;font-size:12px;margin-top:32px">Perfilaí, um produto Rangel Tech. Se você não pediu este e-mail, ignore.</p>
</div></body></html>"""


def enviar(cfg: Config, para: str, assunto: str, texto: str, html: str) -> bool:
    if not cfg.smtp_host or not cfg.smtp_senha:
        log.warning("SMTP desligado; e-mail para %s nao enviado: %s", para, assunto)
        return False
    m = EmailMessage()
    m["From"] = cfg.smtp_from
    m["To"] = para
    m["Subject"] = assunto
    m.set_content(texto)
    m.add_alternative(MOLDE.format(corpo=html), subtype="html")
    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(cfg.smtp_user, cfg.smtp_senha)
            s.send_message(m)
        return True
    except Exception as e:  # noqa: BLE001
        log.error("falha no SMTP para %s: %s", para, e)
        return False


def codigo(cfg: Config, para: str, cod: str) -> bool:
    html = (f'<p style="font-size:16px">Seu código para entrar no Perfilaí:</p>'
            f'<div style="font-size:36px;font-weight:800;letter-spacing:8px;background:#17171f;border-radius:12px;padding:18px;text-align:center">{cod}</div>'
            f'<p style="color:#8b8b98">Vale por 15 minutos.</p>')
    return enviar(cfg, para, f"{cod} é o seu código do Perfilaí", f"Seu código para entrar no Perfilaí: {cod}\nVale por 15 minutos.", html)


def pronto(cfg: Config, para: str, arroba: str) -> bool:
    link = cfg.base_url + "/app"
    html = (f'<p style="font-size:16px">O plano do perfil <b>@{arroba}</b> está pronto: raio-x, bios, 30 ideias, roteiros, stories de venda, carrosséis e site.</p>'
            f'<p><a href="{link}" style="display:inline-block;background:#b46bff;color:#fff;text-decoration:none;font-weight:700;padding:12px 20px;border-radius:10px">Ver meu plano</a></p>')
    return enviar(cfg, para, f"O plano do @{arroba} está pronto", f"O plano do perfil @{arroba} está pronto: {link}", html)
