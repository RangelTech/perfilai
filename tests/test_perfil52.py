"""Spec 44 5.2: limites por contas/semana e 3 rodadas por conta, post do dia (1/dia, 7/semana), kit de marca em foto e vídeo, renda extra."""
import io
import json
import os
import subprocess

os.environ["PERFILAI_SEM_APP"] = "1"

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main, rt_midia
from app.main import Config, criar_app


@pytest.fixture()
def cli(tmp_path):
    cfg = Config(dados=str(tmp_path), dev=True, segredo_sessao="s", cakto_segredo="ck", admin_key="adm", demo_email="demo@rangeltech.net", demo_senha="Demo2026",
                 planos_por_produto={"p-start": "start", "p-pro": "pro", "p-turbo": "turbo"}, checkouts={"start": "https://pay/x"})
    return TestClient(criar_app(cfg, iniciar_fila=False))


def entrar(c, email="ana@exemplo.com"):
    cod = c.post("/api/entrar/codigo", json={"email": email}).json()["codigo_dev"]
    assert c.post("/api/entrar", json={"email": email, "codigo": cod}).status_code == 200


def assinar(c, email="ana@exemplo.com", produto="p-start"):
    assert c.post("/api/cakto", json={"secret": "ck", "event": "purchase_approved", "data": {"id": "x" + email + produto, "customer": {"email": email}, "product": {"id": produto}}}).status_code == 200


def pedir(c, arroba):
    return c.post("/api/planos", json={"arroba": arroba, "objetivo": "vender bolo no pote", "nicho": "confeitaria"})


def finalizar_todos(c):
    db = c.app.state.db
    r = {"ideias": [{"formato": "post", "gancho": f"Gancho {i}", "ideia": f"ideia {i}"} for i in range(10)], "raio_x": {}, "renda_extra": {"servico": "Gestão de perfil"}}
    db.exec("UPDATE planos SET estado='pronto', resultado=? WHERE estado IN ('fila','rodando')", (json.dumps(r),))


def test_limites_contas_por_semana_e_rodadas(cli):
    c = cli
    entrar(c); assinar(c)  # Start: 1 conta por semana
    j = c.get("/api/conta").json()
    assert j["limite_contas"] == 1 and j["rodadas_por_conta"] == 3
    for _ in range(3):
        assert pedir(c, "@doces.da.ana").status_code == 200
        finalizar_todos(c)
    r = pedir(c, "@doces.da.ana")
    assert r.status_code == 429 and "3 rodadas" in r.json()["detail"]
    r = pedir(c, "@outra.conta")
    assert r.status_code == 402 and "1 conta" in r.json()["detail"]
    j = c.get("/api/conta").json()
    assert j["contas_semana"] == 1 and j["rodadas"] == {"doces.da.ana": 3}


def test_pro_libera_tres_contas(cli):
    c = cli
    entrar(c, "p@x.com"); assinar(c, "p@x.com", "p-pro")
    for a in ("a1", "a2", "a3"):
        assert pedir(c, a).status_code == 200
        finalizar_todos(c)
    assert pedir(c, "a4").status_code == 402


def _png():
    b = io.BytesIO()
    Image.new("RGB", (1024, 1536), (40, 120, 200)).save(b, "PNG")
    return b.getvalue()


def test_post_do_dia_um_por_dia(cli, monkeypatch):
    c = cli
    entrar(c); assinar(c)
    pid = pedir(c, "doces.da.ana").json()["id"]
    finalizar_todos(c)
    monkeypatch.setattr(rt_midia, "imagem", lambda *a, **k: rt_midia.Resultado(_png(), "gpt", "ok"))
    r = c.post(f"/api/planos/{pid}/post")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["gancho"] == "Gancho 0" and p["url"].endswith(".png")
    img = Image.open(io.BytesIO(c.get(p["url"]).content))
    assert img.size == (1080, 1350)
    r2 = c.post(f"/api/planos/{pid}/post")
    assert r2.status_code == 429 and "hoje" in r2.json()["detail"]
    assert len(c.get("/api/posts").json()["posts"]) == 1
    assert c.get("/api/conta").json()["posts_semana"] == 1


def test_post_imagem_indisponivel_vira_503(cli, monkeypatch):
    c = cli
    entrar(c); assinar(c)
    pid = pedir(c, "doces.da.ana").json()["id"]
    finalizar_todos(c)

    def falha(*a, **k):
        raise rt_midia.ImagemIndisponivel("estúdio alternativo indisponível")
    monkeypatch.setattr(rt_midia, "imagem", falha)
    r = c.post(f"/api/planos/{pid}/post")
    assert r.status_code == 503 and "indisponível" in r.json()["detail"]


def test_kit_de_marca_foto_e_video(cli, tmp_path):
    c = cli
    entrar(c); assinar(c)
    b = io.BytesIO()
    Image.new("RGB", (800, 1000), (10, 200, 10)).save(b, "JPEG")
    r = c.post("/api/kit", content=b.getvalue(), headers={"x-arquivo": "foto.jpg", "x-arroba": "@doces.da.ana", "x-cor": "#ff0000"})
    assert r.status_code == 200, r.text
    img = Image.open(io.BytesIO(c.get(r.json()["url"]).content)).convert("RGB")
    assert img.getpixel((5, 995))[0] > 200 and img.getpixel((5, 995))[1] < 60  # faixa vermelha embaixo
    v = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=720x1280:d=2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(v)], check=True)
    r = c.post("/api/kit", content=v.read_bytes(), headers={"x-arquivo": "v.mp4", "x-arroba": "doces.da.ana", "x-cor": "#ff0000"})
    assert r.status_code == 200, r.text
    assert len(c.get(r.json()["url"]).content) > 1000
    assert len(c.get("/api/kit").json()["itens"]) == 2
    assert c.post("/api/kit", content=b"x" * 1000, headers={"x-arquivo": "a.exe", "x-arroba": "a"}).status_code == 422
