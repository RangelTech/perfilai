"""Perfilaí: login, limite do plano, pedido com print, processamento (IA simulada), carrosséis PNG, site .zip, Cakto, admin."""
import base64
import io
import json
import os
import zipfile

os.environ["PERFILAI_SEM_APP"] = "1"

import pytest
from fastapi.testclient import TestClient

from app import analise, main
from app.main import Config, criar_app

PRINT = "data:image/png;base64," + base64.b64encode(
    bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4a00000000049454e44ae426082")).decode()

FALSO = {"perfil": {"arroba": "doces.da.ana"}, "leitura": {}, "raio_x": {"nota": 64, "resumo": "ok", "fortes": ["a"], "fracos": ["b"], "prioridades": ["c"]},
         "estrategia": {"posicionamento": "p", "pilares": ["x"]}, "ideias": [{"formato": "reels", "gancho": "Ninguém fala disso", "ideia": "i"}] * 30,
         "referencias": [], "bios": ["bio 1", "bio 2", "bio 3"], "roteiros": [], "stories_venda": [],
         "carrosseis": [{"titulo": "3 erros no brigadeiro", "laminas": ["Erro 1: fogo alto demais", "Erro 2: panela fina", "Erro 3: tirar cedo"], "legenda": "salva"}],
         "site": {"titulo": "Bolo no pote que vende", "subtitulo": "s", "beneficios": ["b1"], "faq": [{"p": "q", "r": "r"}], "chamada": "Quero"}}


@pytest.fixture()
def cli(tmp_path):
    cfg = Config(dados=str(tmp_path), dev=True, segredo_sessao="s", cakto_segredo="ck", admin_key="adm", demo_email="demo@rangeltech.net", demo_senha="Demo2026",
                 planos_por_produto={"p-pro": "pro", "p-turbo": "turbo"}, checkouts={"start": "https://pay/x"})
    app = criar_app(cfg, iniciar_fila=False)
    return TestClient(app), app


def entrar(c, email="ana@exemplo.com"):
    cod = c.post("/api/entrar/codigo", json={"email": email}).json()["codigo_dev"]
    assert c.post("/api/entrar", json={"email": email, "codigo": cod}).status_code == 200


def assinar(c, email="ana@exemplo.com", produto="p-pro"):
    assert c.post("/api/cakto", json={"secret": "ck", "event": "purchase_approved", "data": {"id": "x" + email, "customer": {"email": email}, "product": {"id": produto}}}).status_code == 200


def test_sem_plano_nao_gera(cli):
    c, _ = cli
    entrar(c)
    r = c.post("/api/planos", json={"arroba": "ana", "objetivo": "vender bolo no pote"})
    assert r.status_code == 402


def test_plano_completo_com_print(cli, monkeypatch):
    c, _ = cli
    app = c.app
    entrar(c); assinar(c)
    assert c.get("/api/conta").json()["limite_contas"] == 3
    r = c.post("/api/planos", json={"arroba": "@doces.da.ana", "objetivo": "vender bolo no pote", "nicho": "confeitaria", "cor": "#ff5fa2", "prints": [PRINT]})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert c.post("/api/planos", json={"arroba": "x", "objetivo": "outro plano"}).status_code == 429   # 1 por vez
    vistos = {}
    monkeypatch.setattr(analise, "plano", lambda cfg, entrada, prints, avisar: (vistos.update(n=len(prints), e=entrada), FALSO)[1])
    main.processar(app.state.db, app.state.cfg, app.state.db.um("SELECT * FROM planos WHERE id=?", (pid,)))
    assert vistos["n"] == 1 and vistos["e"]["arroba"] == "doces.da.ana"
    p = c.get(f"/api/planos/{pid}").json()
    assert p["estado"] == "pronto" and len(p["resultado"]["ideias"]) == 30
    lams = p["resultado"]["carrosseis_png"][0]
    assert len(lams) == 4 and c.get(lams[0]).headers["content-type"] == "image/png"
    z = c.get(f"/api/planos/{pid}/site.zip?checkout=https://pay.cakto.com.br/abc")
    assert z.status_code == 200
    with zipfile.ZipFile(io.BytesIO(z.content)) as f:
        html = f.read("index.html").decode()
        assert "Bolo no pote que vende" in html and "https://pay.cakto.com.br/abc" in html and "LEIA-ME.txt" in f.namelist()


def test_demo_entra_com_senha_e_e_turbo(cli):
    c, _ = cli
    assert c.post("/api/entrar/senha", json={"email": "demo@rangeltech.net", "senha": "errada"}).status_code == 400
    assert c.post("/api/entrar/senha", json={"email": "demo@rangeltech.net", "senha": "Demo2026"}).status_code == 200
    j = c.get("/api/conta").json()
    assert j["assinante"] and j["plano"] == "turbo"


def test_turbo_libera_cortai(cli, monkeypatch):
    c, _ = cli
    app = c.app
    chamadas = []
    monkeypatch.setattr(main, "ponte_cortai", lambda cfg, email, dias: chamadas.append((email, dias)) or True)
    r = c.post("/api/cakto", json={"secret": "ck", "event": "purchase_approved", "data": {"id": "t1", "customer": {"email": "t@x.com"}, "product": {"id": "p-turbo"}}})
    assert r.json().get("cortai") is True and chamadas == [("t@x.com", 32)]
    c.post("/api/cakto", json={"secret": "ck", "event": "refund", "data": {"id": "t1", "customer": {"email": "t@x.com"}, "product": {"id": "p-turbo"}}})
    assert chamadas[-1] == ("t@x.com", 0)


def test_admin_e_cakto(cli):
    c, _ = cli
    assert c.get("/api/admin/resumo").status_code == 401
    assert c.post("/api/cakto", json={"secret": "errado"}).status_code == 401
    assinar(c, "b@x.com")
    r = c.get("/api/admin/resumo", headers={"x-admin-key": "adm"}).json()
    assert r["produto"] == "perfilai" and r["assinantes"] >= 1


def test_analise_diretor_e_redator(monkeypatch):
    """Diretor (rt-planejar) monta estratégia e ideias; redator (rt-geral) escreve; o briefing do diretor chega ao redator."""
    chamadas = []

    def falso(cfg, cli_, modelos, conteudo, max_tokens, temperatura=0.6):
        chamadas.append((modelos[0], conteudo if isinstance(conteudo, str) else "img"))
        if modelos[0] == "rt-planejar":
            return {"raio_x": {"nota": 70}, "estrategia": {"posicionamento": "doceira", "pilares": ["receitas"]}, "ideias": [{"formato": "reels", "gancho": "g", "ideia": "i"}] * 31,
                    "referencias": [{}] * 4, "briefing_mao_de_obra": "TOM-CARINHOSO"}
        return {"bios": ["a", "b", "c", "d"], "roteiros": [{}] * 5, "stories_venda": [{}] * 3, "carrosseis": [{}] * 3, "site": {"titulo": "t"}}
    monkeypatch.setattr(analise, "_chat", falso)
    r = analise.plano(Config(), {"arroba": "ana", "objetivo": "vender"}, [], lambda e, p: None)
    assert [m for m, _ in chamadas] == ["rt-planejar", "rt-geral", "rt-geral", "rt-geral", "rt-geral"] and all("TOM-CARINHOSO" in x for _, x in chamadas[1:])
    assert len(r["ideias"]) == 30 and len(r["bios"]) == 3 and len(r["referencias"]) == 3


# ---------------------------------------------------------------- senha (padrão), código (opção), esqueci a senha
def test_senha_criar_entrar_trocar_e_esqueci(cli):
    from fastapi.testclient import TestClient
    c, _ = cli
    app = c.app
    em = "senha@exemplo.com"
    entrar(c, em)
    assert c.get("/api/senha").json()["tem_senha"] is False
    assert c.post("/api/senha", json={"senha": "curta"}).status_code == 422
    assert c.post("/api/senha", json={"senha": "boa-senha-1"}).status_code == 200
    assert c.get("/api/senha").json()["tem_senha"] is True
    # trocar exige a atual
    assert c.post("/api/senha", json={"senha": "outra-senha", "atual": "errada"}).status_code == 400
    assert c.post("/api/senha", json={"senha": "outra-senha", "atual": "boa-senha-1"}).status_code == 200
    # entrar com senha num cliente novo (sem cookie)
    n = TestClient(app)
    assert n.post("/api/entrar/senha", json={"email": em, "senha": "boa-senha-1"}).status_code == 400
    r = n.post("/api/entrar/senha", json={"email": em, "senha": "outra-senha"})
    assert r.status_code == 200 and n.get("/api/senha").status_code == 200
    # conta sem senha recebe dica de usar o código
    entrar(TestClient(app), "semsenha@exemplo.com")
    r = TestClient(app).post("/api/entrar/senha", json={"email": "semsenha@exemplo.com", "senha": "qualquer1"})
    assert r.status_code == 400 and "código" in r.json()["detail"]
    # esqueci a senha: código separado do login, troca a senha e já entra
    e = TestClient(app)
    j = e.post("/api/senha/esqueci", json={"email": em}).json()
    assert e.post("/api/senha/redefinir", json={"email": em, "codigo": "000000" if j["codigo_dev"] != "000000" else "111111", "senha": "nova-senha-9"}).status_code == 400
    j = None
    import app.auth as A
    A.REENVIO_MIN_S = 0
    j = e.post("/api/senha/esqueci", json={"email": em}).json()
    assert e.post("/api/senha/redefinir", json={"email": em, "codigo": j["codigo_dev"], "senha": "nova-senha-9"}).status_code == 200
    assert e.get("/api/senha").json()["tem_senha"] is True
    assert TestClient(app).post("/api/entrar/senha", json={"email": em, "senha": "nova-senha-9"}).status_code == 200
    # e-mail sem conta: mesma resposta, sem código
    assert "codigo_dev" not in e.post("/api/senha/esqueci", json={"email": "ninguem@exemplo.com"}).json()


def test_senha_bloqueia_depois_de_muitos_erros(cli):
    from app import senha_rotas
    c, _ = cli
    senha_rotas._erros.clear()
    for _ in range(senha_rotas.MAX_ERROS):
        c.post("/api/entrar/senha", json={"email": "forca@exemplo.com", "senha": "x"})
    assert c.post("/api/entrar/senha", json={"email": "forca@exemplo.com", "senha": "x"}).status_code == 429
    senha_rotas._erros.clear()
