"""Imagens do perfil (spec 44 3.3.4): foto profissional, capa por rede, ícones de destaque recortados de uma grade, limite semanal."""
import io
import os

os.environ["PERFILAI_SEM_APP"] = "1"

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import midia_perfil, rt_midia
from app.main import Config, criar_app


def png(w, h, grade=False):
    im = Image.new("RGB", (w, h), (120, 60, 200))
    if grade:
        d = ImageDraw.Draw(im)
        cw, ch = w // 3, h // 2
        for r in range(2):
            for c in range(3):
                d.ellipse((c * cw + cw // 3, r * ch + ch // 3, c * cw + 2 * cw // 3, r * ch + 2 * ch // 3), outline="white", width=12)
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


@pytest.fixture()
def app_(tmp_path, monkeypatch):
    cfg = Config(dados=str(tmp_path), dev=True, segredo_sessao="s", cakto_segredo="ck", planos_por_produto={"p": "start", "pl": "linkedin:start"})
    chamadas = []

    def falso(prompt, base, key, tamanho="1024x1024", referencia=None, classe=None, modelo_classif="rt-geral"):
        chamadas.append((prompt, tamanho, bool(referencia)))
        w, h = map(int, tamanho.split("x"))
        return rt_midia.Resultado(png(w, h, grade="grid" in prompt), "gpt", "ok")
    monkeypatch.setattr(rt_midia, "imagem", falso)
    a = criar_app(cfg, iniciar_fila=False)
    a.state.chamadas = chamadas
    return a


def cli(a, host="insta-ai.rangeltech.net", email="ana@exemplo.com", produto="p"):
    c = TestClient(a, base_url=f"https://{host}")
    cod = c.post("/api/entrar/codigo", json={"email": email}).json()["codigo_dev"]
    c.post("/api/entrar", json={"email": email, "codigo": cod})
    c.post("/api/cakto", json={"secret": "ck", "event": "purchase_approved", "data": {"id": email + produto, "customer": {"email": email}, "product": {"id": produto}}})
    return c


def test_foto_profissional_usa_a_foto_de_referencia(app_):
    c = cli(app_)
    r = c.post("/api/imagens/foto", content=png(800, 1000), headers={"x-cor": "#ff0000"})
    assert r.status_code == 200, r.text
    assert app_.state.chamadas[-1][2] is True  # mandou a foto como referência (edição)
    im = Image.open(io.BytesIO(c.get(r.json()["urls"][0]).content))
    assert im.size == (1080, 1080)


def test_capa_so_no_linkedin_e_facebook_e_no_tamanho_certo(app_):
    c = cli(app_)
    assert c.post("/api/imagens/capa", json={"frase": "x"}).status_code == 422  # Insta AI não tem capa
    lk = cli(app_, "linkdn-ai.rangeltech.net", "l@x.com", "pl")
    r = lk.post("/api/imagens/capa", json={"frase": "Dados que viram decisão", "nicho": "dados"})
    assert r.status_code == 200, r.text
    assert Image.open(io.BytesIO(lk.get(r.json()["urls"][0]).content)).size == (1584, 396)


def test_icones_recortados_e_limite_semanal(app_):
    c = cli(app_)
    assert c.post("/api/imagens/icones", json={"temas": ["Só um"]}).status_code == 422
    r = c.post("/api/imagens/icones", json={"temas": ["Cardápio", "Clientes", "Entrega", "Dúvidas"], "cor": "#ff8800"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["urls"]) == 6 and len(j["temas"]) == 6
    assert all(Image.open(io.BytesIO(c.get(u).content)).size == (1080, 1080) for u in j["urls"])
    c.post("/api/imagens/icones", json={"temas": ["a", "b"]})
    c.post("/api/imagens/icones", json={"temas": ["a", "b"]})
    r = c.post("/api/imagens/icones", json={"temas": ["a", "b"]})
    assert r.status_code == 429
    assert len(c.get("/api/imagens").json()["itens"]) == 3


def test_fatiar_ignora_celula_vazia():
    im = Image.new("RGB", (900, 600), (10, 10, 10))
    d = ImageDraw.Draw(im)
    d.ellipse((100, 100, 200, 200), outline="white", width=10)  # só a 1ª célula tem ícone
    b = io.BytesIO(); im.save(b, "PNG")
    assert len(midia_perfil.fatiar_icones(b.getvalue())) == 1
