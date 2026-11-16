"""Suíte de perfil (spec 44 parte 3): marca pelo domínio, landing por marca, assinatura por marca, currículo do Linkdn AI."""
import io
import os

os.environ["PERFILAI_SEM_APP"] = "1"

import pytest
from fastapi.testclient import TestClient

from app import analise
from app.main import Config, criar_app

HOSTS = {"insta": "insta-ai.rangeltech.net", "face": "face-ai.rangeltech.net", "tiktok": "tittok-ai.rangeltech.net", "linkedin": "linkdn-ai.rangeltech.net"}


@pytest.fixture()
def app_(tmp_path):
    cfg = Config(dados=str(tmp_path), dev=True, segredo_sessao="s", cakto_segredo="ck", admin_key="adm",
                 planos_por_produto={"p-insta": "start", "p-lkd-pro": "linkedin:pro", "p-face-top": "face:turbo"}, checkouts={})
    return criar_app(cfg, iniciar_fila=False)


def cli(app_, marca):
    return TestClient(app_, base_url=f"https://{HOSTS[marca]}")


def entrar(c, email="ana@exemplo.com"):
    cod = c.post("/api/entrar/codigo", json={"email": email}).json()["codigo_dev"]
    assert c.post("/api/entrar", json={"email": email, "codigo": cod}).status_code == 200


def test_marca_pelo_dominio_e_landing(app_):
    for m, h in HOSTS.items():
        c = cli(app_, m)
        assert c.get("/api/marca").json()["id"] == m
        html = c.get("/").text
        assert "{{" not in html and "window.MARCA" in html
    assert "Perfil AI LinkedIn" in cli(app_, "linkedin").get("/").text
    assert "Perfil AI TikTok" in cli(app_, "tiktok").get("/").text
    assert TestClient(app_, base_url="https://perfilai.rangeltech.net").get("/api/marca").json()["id"] == "insta"


def test_assinatura_por_marca(app_):
    c = cli(app_, "linkedin")
    entrar(c)
    assert c.get("/api/conta").json()["assinante"] is False
    r = c.post("/api/cakto", json={"secret": "ck", "event": "purchase_approved", "data": {"id": "a1", "customer": {"email": "ana@exemplo.com"}, "product": {"id": "p-lkd-pro"}}})
    assert r.json()["marca"] == "linkedin"
    j = c.get("/api/conta").json()
    assert j["assinante"] is True and j["plano"] == "pro" and j["limite_contas"] == 3
    i = cli(app_, "insta")
    entrar(i)
    assert i.get("/api/conta").json()["assinante"] is False  # assinar o Linkdn AI não libera o Insta AI
    c.post("/api/cakto", json={"secret": "ck", "event": "refund", "data": {"id": "a1", "customer": {"email": "ana@exemplo.com"}, "product": {"id": "p-lkd-pro"}}})
    assert c.get("/api/conta").json()["assinante"] is False


def test_pedido_linkedin_aceita_url_e_curriculo(app_):
    c = cli(app_, "linkedin")
    entrar(c)
    c.post("/api/cakto", json={"secret": "ck", "event": "purchase_approved", "data": {"id": "a2", "customer": {"email": "ana@exemplo.com"}, "product": {"id": "p-lkd-pro"}}})
    r = c.post("/api/planos", json={"arroba": "https://www.linkedin.com/in/ana-lima", "objetivo": "conseguir vaga de dados", "curriculo_texto": "Analista na Empresa X 2020-2024"})
    assert r.status_code == 200, r.text
    import json
    e = json.loads(c.app.state.db.um("SELECT entrada FROM planos WHERE id=?", (r.json()["id"],))["entrada"])
    assert e["marca"] == "linkedin" and "linkedin.com/in/ana-lima" in e["arroba"] and e["curriculo_texto"].startswith("Analista")


def test_curriculo_txt_docx_pdf(app_, tmp_path):
    c = cli(app_, "linkedin")
    entrar(c)
    r = c.post("/api/curriculo", content="Fui analista de dados na Empresa X de 2020 a 2024, com SQL e Python.".encode(), headers={"x-arquivo": "cv.txt"})
    assert r.status_code == 200 and "Empresa X" in r.json()["texto"]
    import docx
    d = docx.Document()
    d.add_paragraph("Engenheira de dados na Empresa Y desde 2021, pipelines em Airflow e dbt.")
    b = io.BytesIO(); d.save(b)
    r = c.post("/api/curriculo", content=b.getvalue(), headers={"x-arquivo": "cv.docx"})
    assert r.status_code == 200 and "Airflow" in r.json()["texto"]
    from PIL import Image
    pdf = io.BytesIO(); Image.new("RGB", (200, 200), "white").save(pdf, "PDF")
    r = c.post("/api/curriculo", content=pdf.getvalue(), headers={"x-arquivo": "cv.pdf"})
    assert r.status_code == 422 and "escaneado" in r.json()["detail"]
    assert c.post("/api/curriculo", content=b"x" * 100, headers={"x-arquivo": "cv.exe"}).status_code == 422


def test_prompt_segue_a_rede(monkeypatch, tmp_path):
    vistos = []

    def falso(cfg, cliente, modelos, conteudo, max_tokens, temperatura=0.6):
        vistos.append(conteudo if isinstance(conteudo, str) else "")
        if "estrategista" in vistos[-1]:
            return {"raio_x": {}, "estrategia": {}, "ideias": [], "briefing_mao_de_obra": "b"}
        if "sobre" in vistos[-1] and "Experiências" in vistos[-1]:
            return {"sobre": ["s1"], "experiencias": [{"cargo": "Analista", "empresa": "X", "origem": "curriculo"}]}
        return {"bios": ["b1"], "roteiros": []}
    monkeypatch.setattr(analise, "_chat", falso)
    cfg = Config(dados=str(tmp_path))
    r = analise.plano(cfg, {"arroba": "linkedin.com/in/ana", "objetivo": "vaga", "marca": "linkedin", "curriculo_texto": "Analista na X"}, [], lambda *a: None)
    assert "LinkedIn" in vistos[0] and "220" in vistos[0] and "Analista na X" in vistos[0]
    assert r["linkedin"]["experiencias"][0]["origem"] == "curriculo" and r["marca"] == "linkedin"
    vistos.clear()
    analise.plano(cfg, {"arroba": "anadoces", "objetivo": "vender", "marca": "tiktok"}, [], lambda *a: None)
    assert "TikTok" in vistos[0] and any("80 caracteres" in v for v in vistos)
