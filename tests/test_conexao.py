"""Conexão real da suíte (spec 44 3.3.3) com perfil-navegador falso: 2FA, aplicar a bio, sessão some ao aplicar e na virada da semana."""
from produtos_core.teste import entrar
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PERFILAI_SEM_APP"] = "1"

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import Config, criar_app  # noqa: E402
from app.pn import PN  # noqa: E402


class PNFalso:
    def __init__(self):
        self.aplicados, self.apagados = [], []

    def handler(self, req: httpx.Request) -> httpx.Response:
        p, b = req.url.path, (json.loads(req.content) if req.content else {})
        if p == "/logins":
            assert b["conta"].startswith("perfilai:") and b["rede"] == "instagram"
            return httpx.Response(200, json={"id": "L1", "passo": {"tipo": "codigo_2fa"}})
        if p == "/logins/L1/responder":
            return httpx.Response(200, json={"id": "L1", "passo": {"tipo": "conectado" if b["valor"] == "123456" else "codigo_2fa"}})
        if p.endswith("/aplicar"):
            self.aplicados.append(b)
            return httpx.Response(200, json={k: "ok" for k in b})
        if p.endswith("/perfil"):
            return httpx.Response(200, json={"usuario": "loja", "bio": "bio velha", "seguidores": 900})
        if req.method == "DELETE":
            self.apagados.append(p)
            return httpx.Response(200, json={"apagada": True})
        return httpx.Response(404, json={"detail": "?"})


@pytest.fixture
def amb(tmp_path):
    f = PNFalso()
    cfg = Config(dados=str(tmp_path), dev=True, segredo_sessao="s", cakto_segredo="ck", demo_email="demo@rangeltech.net", demo_senha="Demo2026")
    app = criar_app(cfg, iniciar_fila=False, pn=PN("http://pn", "tk", transport=httpx.MockTransport(f.handler)))
    c = TestClient(app)
    entrar(c, "demo@rangeltech.net")
    return c, f, app


def plano_pronto(app):
    u = app.state.db.um("SELECT id FROM usuarios WHERE email='demo@rangeltech.net'")
    app.state.db.exec("INSERT INTO planos(id,usuario,entrada,estado,etapa,progresso,resultado,criado) VALUES(?,?,?,?,?,?,?,?)",
                      ("p1", u["id"], json.dumps({"arroba": "loja", "marca": "insta"}), "pronto", "", 1, json.dumps({"bios": ["Bio nova 1", "Bio nova 2"]}), time.time()))


def conectar(c):
    r = c.post("/api/conexao", json={"aceite": True, "usuario": "loja", "senha": "x"}).json()
    assert r["passo"]["tipo"] == "codigo_2fa"
    assert c.post("/api/conexao/login", json={"valor": "1"}).json()["passo"]["tipo"] == "codigo_2fa"
    assert c.post("/api/conexao/login", json={"valor": "123456"}).json()["estado"] == "conectada"


def test_conectar_aplicar_e_sessao_some(amb):
    c, f, app = amb
    plano_pronto(app)
    assert c.post("/api/planos/p1/aplicar", json={"bio": 0}).status_code == 409
    conectar(c)
    assert c.post("/api/conexao/perfil").json()["bio"] == "bio velha"
    r = c.post("/api/planos/p1/aplicar", json={"bio": 1}).json()
    assert r["aplicado"] == {"bio": "Bio nova 2"} and r["resultado"] == {"bio": "ok"}
    assert f.apagados and c.get("/api/conexao").json()["estado"] == "aplicada"
    assert c.post("/api/conexao", json={"aceite": True, "usuario": "loja", "senha": "x"}).status_code == 429  # próxima semana


def test_semana_vira_apaga_sessao(amb):
    c, f, app = amb
    conectar(c)
    app.state.db.exec("UPDATE conexoes SET semana=?", (time.time() - 10 * 86400,))
    assert c.get("/api/conexao").json()["estado"] == "expirou"
    assert f.apagados


def test_aceite_obrigatorio_e_nada_para_aplicar(amb):
    c, _, app = amb
    plano_pronto(app)
    assert c.post("/api/conexao", json={"usuario": "a", "senha": "b"}).status_code == 422
    conectar(c)
    assert c.post("/api/planos/p1/aplicar", json={}).status_code == 422
