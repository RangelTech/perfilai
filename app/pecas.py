"""Peças prontas para baixar: carrosséis em PNG 1080x1350 (Pillow, cor da marca) e o site de vendas estático em .zip."""
from __future__ import annotations

import html
import io
import textwrap
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTE = Path(__file__).resolve().parent.parent / "static" / "fonts" / "Montserrat-ExtraBold.ttf"
W, H = 1080, 1350


def _hex(c: str) -> tuple[int, int, int]:
    c = (c or "#b46bff").lstrip("#")
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (180, 107, 255)


def _texto(d: ImageDraw.ImageDraw, txt: str, tam: int, largura: int, y: int, cor, max_linhas: int = 9) -> int:
    f = ImageFont.truetype(str(FONTE), tam)
    chars = max(8, int(largura / (tam * 0.58)))
    linhas = textwrap.wrap(txt, chars)[:max_linhas]
    for l in linhas:
        d.text((90, y), l, font=f, fill=cor)
        y += int(tam * 1.25)
    return y


def carrossel(c: dict, arroba: str, cor: str, pasta: Path, n: int) -> list[str]:
    pasta.mkdir(parents=True, exist_ok=True)
    rgb = _hex(cor)
    escuro = (12, 10, 18)
    nomes = []
    laminas = [str(c.get("titulo") or "")] + [str(x) for x in (c.get("laminas") or [])][:7]
    for i, txt in enumerate(laminas, 1):
        capa = i == 1
        img = Image.new("RGB", (W, H), rgb if capa else escuro)
        d = ImageDraw.Draw(img)
        fg = (255, 255, 255) if capa else (240, 240, 245)
        if not capa:
            d.rectangle([90, 120, 210, 132], fill=rgb)
        _texto(d, txt, 92 if capa else 60, W - 180, 300 if capa else 220, fg, 8 if capa else 12)
        pe = ImageFont.truetype(str(FONTE), 34)
        d.text((90, H - 120), f"@{arroba}" if arroba else "", font=pe, fill=fg if capa else rgb)
        d.text((W - 200, H - 120), f"{i}/{len(laminas)}" if not capa else "arraste →", font=pe, fill=fg)
        nome = f"carrossel{n}_{i:02d}.png"
        img.save(pasta / nome, optimize=True)
        nomes.append(nome)
    return nomes


def site_zip(s: dict, perfil: dict, cor: str, checkout: str = "") -> bytes:
    e = lambda x: html.escape(str(x or ""))
    ben = "".join(f"<li>{e(b)}</li>" for b in s.get("beneficios") or [])
    faq = "".join(f"<details><summary>{e(f.get('p'))}</summary><p>{e(f.get('r'))}</p></details>" for f in s.get("faq") or [] if isinstance(f, dict))
    link = e(checkout or "https://pay.cakto.com.br/SEU-LINK")
    pagina = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(s.get('titulo'))}</title><meta name="description" content="{e(s.get('subtitulo'))}">
<style>:root{{--c:{e(cor or '#b46bff')}}}*{{box-sizing:border-box}}body{{margin:0;font:17px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#15131a;background:#fbfaff}}
.w{{max-width:760px;margin:0 auto;padding:56px 20px}}h1{{font-size:clamp(32px,6vw,52px);line-height:1.1;margin:0 0 16px}}.sub{{font-size:20px;color:#55506a}}
.btn{{display:inline-block;background:var(--c);color:#fff;text-decoration:none;font-weight:800;padding:18px 32px;border-radius:14px;margin:24px 0}}
ul{{padding:0;list-style:none}}li{{padding:14px 0 14px 34px;border-bottom:1px solid #ebe8f3;position:relative}}li:before{{content:"✓";position:absolute;left:0;color:var(--c);font-weight:900}}
.prova{{background:#fff;border:1px solid #ebe8f3;border-radius:16px;padding:20px;margin:32px 0;font-style:italic}}details{{border-bottom:1px solid #ebe8f3;padding:14px 0}}
summary{{font-weight:700;cursor:pointer}}footer{{color:#8a85a0;font-size:14px;padding:32px 0}}</style></head><body><main class="w">
<p style="color:var(--c);font-weight:800">@{e(perfil.get('arroba'))}</p><h1>{e(s.get('titulo'))}</h1><p class="sub">{e(s.get('subtitulo'))}</p>
<a class="btn" href="{link}">{e(s.get('chamada') or 'Quero agora')}</a><ul>{ben}</ul><div class="prova">{e(s.get('prova'))}</div>
<h2>{e(s.get('oferta'))}</h2><a class="btn" href="{link}">{e(s.get('chamada') or 'Quero agora')}</a><h2>Perguntas frequentes</h2>{faq}
<footer>@{e(perfil.get('arroba'))} · Pagamento seguro pela Cakto</footer></main></body></html>"""
    leia = """COMO PUBLICAR SEU SITE (GRÁTIS, 10 MINUTOS)

1. Crie sua conta na Cakto (cakto.com.br) e cadastre seu produto. Copie o link do checkout.
2. Abra o index.html num editor de texto (Bloco de Notas serve) e troque https://pay.cakto.com.br/SEU-LINK pelo seu link (aparece 2 vezes).
3. Crie uma conta grátis no GitHub (github.com).
4. Clique em "New repository", dê o nome seu-usuario.github.io, marque Public e crie.
5. Clique em "uploading an existing file" e arraste o index.html. Clique em "Commit changes".
6. Em Settings > Pages, confirme Branch: main. Em 1 ou 2 minutos o site abre em https://seu-usuario.github.io
7. Coloque esse endereço na bio do Instagram.
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", pagina)
        z.writestr("LEIA-ME.txt", leia)
    return buf.getvalue()
