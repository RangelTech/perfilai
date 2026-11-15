"""Mídia do produto de perfil (spec 44, 5.2): post do dia (imagem pela regra 5.0) e kit de marca em foto/vídeo do cliente (sem edição).

- Post do dia: 1 por dia, 7 por semana por conta. A imagem sai do GPT (rt_midia) a partir de uma ideia do plano;
  o texto (gancho) e o @ entram por cima com Pillow, no formato do feed (1080x1350).
- Kit de marca: foto -> faixa na cor da marca com o @ embaixo; vídeo (até 2 min) -> a mesma faixa entra deslizando (motion) com ffmpeg.
"""
from __future__ import annotations

import io
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTE = Path(__file__).resolve().parent.parent / "static" / "fonts" / "Montserrat-ExtraBold.ttf"
FUSO = timezone(timedelta(hours=-3))
FEED = (1080, 1350)
MAX_VIDEO_S = 125


def inicio_semana(agora_ts: float) -> float:
    """Segunda-feira 00:00 no horário de Brasília."""
    d = datetime.fromtimestamp(agora_ts, FUSO)
    seg = (d - timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return seg.timestamp()


def hoje(agora_ts: float) -> str:
    return datetime.fromtimestamp(agora_ts, FUSO).strftime("%Y-%m-%d")


def _rgb(cor: str) -> tuple[int, int, int]:
    c = (cor or "#b46bff").lstrip("#")
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (180, 107, 255)


def _quebrar(d: ImageDraw.ImageDraw, texto: str, f, largura: int) -> list[str]:
    linhas, atual = [], ""
    for p in texto.split():
        t = (atual + " " + p).strip()
        if atual and d.textlength(t, font=f) > largura:
            linhas.append(atual)
            atual = p
        else:
            atual = t
    if atual:
        linhas.append(atual)
    return linhas[:4]


def montar_post(imagem: bytes, gancho: str, arroba: str, cor: str) -> bytes:
    """Recorta a imagem para 1080x1350, escurece o pé, escreve o gancho e o @."""
    im = Image.open(io.BytesIO(imagem)).convert("RGB")
    w, h = im.size
    alvo = FEED[0] / FEED[1]
    if w / h > alvo:
        nw = int(h * alvo)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / alvo)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    im = im.resize(FEED, Image.LANCZOS)
    sombra = Image.new("L", FEED, 0)
    ds = ImageDraw.Draw(sombra)
    for y in range(FEED[1] // 2, FEED[1]):
        ds.line([(0, y), (FEED[0], y)], fill=int(210 * (y - FEED[1] / 2) / (FEED[1] / 2)))
    im = Image.composite(Image.new("RGB", FEED, (0, 0, 0)), im, sombra)
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(str(FONTE), 64)
    linhas = _quebrar(d, gancho.strip().strip('"“”'), f, FEED[0] - 160)
    y = FEED[1] - 170 - len(linhas) * 78
    for l in linhas:
        d.text((80, y), l, font=f, fill=(255, 255, 255))
        y += 78
    fa = ImageFont.truetype(str(FONTE), 34)
    rgb = _rgb(cor)
    d.rounded_rectangle((80, FEED[1] - 120, 80 + d.textlength("@" + arroba, font=fa) + 48, FEED[1] - 60), radius=28, fill=rgb)
    d.text((104, FEED[1] - 113), "@" + arroba, font=fa, fill=(255, 255, 255))
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def kit_foto(origem: Path, destino: Path, arroba: str, cor: str) -> None:
    im = Image.open(origem).convert("RGB")
    w, h = im.size
    faixa = max(70, h // 11)
    d = ImageDraw.Draw(im)
    d.rectangle((0, h - faixa, w, h), fill=_rgb(cor))
    f = ImageFont.truetype(str(FONTE), int(faixa * 0.42))
    t = "@" + arroba
    d.text(((w - d.textlength(t, font=f)) / 2, h - faixa + faixa * 0.27), t, font=f, fill=(255, 255, 255))
    im.save(destino, "JPEG", quality=92)


def duracao(arq: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(arq)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def kit_video(origem: Path, destino: Path, arroba: str, cor: str) -> None:
    """Faixa da marca entra deslizando de baixo no primeiro meio segundo e fica; @ centralizado. Sem cortar nada do vídeo."""
    c = (cor or "#b46bff").lstrip("#")
    fonte = str(FONTE).replace("\\", "/").replace(":", "\\:")
    texto = ("@" + arroba).replace(":", "\\:").replace("'", "")
    filtro = (f"drawbox=x=0:y='ih-ih/11*min(1,t/0.5)':w=iw:h=ih/11:color=0x{c}@1:t=fill,"
              f"drawtext=fontfile='{fonte}':text='{texto}':fontcolor=white:fontsize=h/26:x=(w-tw)/2:y='h-h/11*min(1,t/0.5)+h/11*0.3'")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(origem), "-vf", filtro, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(destino)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg kit: " + r.stderr[-300:])


# ----------------------------------------------------------------- imagens do perfil (spec 44 3.3.4)
CAPAS = {"linkedin": (1584, 396), "facebook": (1640, 624)}


def foto_perfil(dados: bytes) -> bytes:
    """Quadrado 1080x1080 centralizado (a rede corta em círculo)."""
    im = Image.open(io.BytesIO(dados)).convert("RGB")
    w, h = im.size
    lado = min(w, h)
    im = im.crop(((w - lado) // 2, (h - lado) // 2, (w - lado) // 2 + lado, (h - lado) // 2 + lado)).resize((1080, 1080), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def capa(dados: bytes, rede: str, frase: str, cor: str) -> bytes:
    """Recorta o fundo gerado para o tamanho da capa e escreve a frase de posicionamento à direita (a foto fica à esquerda)."""
    W, H = CAPAS.get(rede, CAPAS["linkedin"])
    im = Image.open(io.BytesIO(dados)).convert("RGB")
    w, h = im.size
    alvo = W / H
    if w / h > alvo:
        nw = int(h * alvo)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / alvo)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    im = im.resize((W, H), Image.LANCZOS)
    if frase:
        d = ImageDraw.Draw(im)
        f = ImageFont.truetype(str(FONTE), max(28, H // 7))
        linhas = _quebrar(d, frase, f, int(W * 0.5))[:2]
        alt = len(linhas) * int(H / 6)
        y = (H - alt) // 2
        x = int(W * 0.44)
        caixa_w = max(d.textlength(l, font=f) for l in linhas) + 48
        d.rounded_rectangle((x - 24, y - 18, x + caixa_w, y + alt + 12), radius=18, fill=(0, 0, 0))
        for l in linhas:
            d.text((x, y), l, font=f, fill=(255, 255, 255))
            y += int(H / 6)
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def fatiar_icones(dados: bytes, colunas: int = 3, linhas: int = 2, cor: str = "#b46bff") -> list[bytes]:
    """Uma imagem com todos os ícones em grade -> um PNG 1080x1080 por ícone, centralizado com margem para o corte redondo."""
    im = Image.open(io.BytesIO(dados)).convert("RGB")
    w, h = im.size
    cw, ch = w // colunas, h // linhas
    saida = []
    for r in range(linhas):
        for c in range(colunas):
            cel = im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
            lado = min(cel.size)
            cel = cel.crop(((cel.width - lado) // 2, (cel.height - lado) // 2, (cel.width - lado) // 2 + lado, (cel.height - lado) // 2 + lado))
            fundo = Image.new("RGB", (1080, 1080), _rgb(cor))
            cel = cel.resize((760, 760), Image.LANCZOS)
            fundo.paste(cel, (160, 160))
            px = list(cel.convert("L").resize((32, 32)).getdata())
            media = sum(px) / len(px)
            variacao = sum((x - media) ** 2 for x in px) / len(px)
            if variacao < 30:  # célula vazia/lisa: o recorte não pegou um ícone
                continue
            out = io.BytesIO()
            fundo.save(out, "PNG", optimize=True)
            saida.append(out.getvalue())
    return saida
