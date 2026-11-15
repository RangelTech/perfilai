"""Perfilaí: plano de Instagram com IA (raio-x, bio, 30 ideias, roteiros, stories de venda, carrosséis e site de vendas). API + páginas."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app import senha_rotas
from app import analise, auth, mailer, pecas
from app.db import Banco, agora

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("perfilai")
ESTATICO = Path(__file__).resolve().parent.parent / "static"
COOKIE = "perfilai_s"
PLANOS = {
    "start": {"nome": "Start", "preco": 19.90, "depois": 29.90, "planos_mes": 2,
              "itens": ["2 planos completos por mês", "Raio-x do perfil e 3 bios", "30 ideias com gancho e 5 roteiros", "Site de vendas pronto"]},
    "pro": {"nome": "Pro", "preco": 29.90, "depois": 39.90, "planos_mes": 6,
            "itens": ["6 planos por mês", "Tudo do Start", "3 carrosséis prontos para postar", "Stories de venda e análise do nicho"]},
    "turbo": {"nome": "Turbo", "preco": 59.90, "depois": 79.90, "planos_mes": 20,
              "itens": ["20 planos por mês (até 3 perfis)", "Tudo do Pro", "Fila prioritária", "Reels editados no Cortaí com a sua marca"]},
}


@dataclass
class Config:
    dados: str = "/data"
    base_url: str = "https://perfilai.rangeltech.net"
    llm_base: str = "https://qwen.rangeltech.net/v1"
    llm_key: str = ""
    llm_modelo: str = "rt-geral"          # mão de obra (Qwen)
    llm_planejador: str = "rt-planejar"   # diretor (GPT)
    llm_visao: str = "visao"              # lê os prints
    segredo_sessao: str = "dev"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_senha: str = ""
    smtp_from: str = "Perfilaí <contato@rangeltech.net>"
    cakto_segredo: str = ""
    dev: bool = False
    checkouts: dict = None
    planos_por_produto: dict = None
    lancamento_ate: str = "2026-11-30"
    admin_key: str = ""
    demo_email: str = ""
    demo_senha: str = ""
    cortai_url: str = "https://cortai.rangeltech.net"
    cortai_admin_key: str = ""            # ponte: Turbo inclui o Cortaí Pro com o mesmo e-mail

    def __post_init__(self):
        self.checkouts = self.checkouts or {}
        self.planos_por_produto = self.planos_por_produto or {}


def carregar() -> Config:
    e = os.environ.get
    return Config(dados=e("PERFILAI_DADOS", "/data"), base_url=e("PERFILAI_BASE_URL", "https://perfilai.rangeltech.net"),
                  llm_base=e("PERFILAI_LLM_BASE", "https://qwen.rangeltech.net/v1"), llm_key=e("PERFILAI_LLM_KEY", ""),
                  llm_modelo=e("PERFILAI_LLM_MODELO", "rt-geral"), llm_planejador=e("PERFILAI_LLM_PLANEJADOR", "rt-planejar"),
                  llm_visao=e("PERFILAI_LLM_VISAO", "visao"), segredo_sessao=e("PERFILAI_SEGREDO_SESSAO", "dev"),
                  smtp_host=e("SMTP_HOST", ""), smtp_port=int(e("SMTP_PORT", "587") or 587), smtp_user=e("SMTP_USER", ""), smtp_senha=e("SMTP_PASSWORD", ""),
                  smtp_from=e("PERFILAI_SMTP_FROM", "Perfilaí <contato@rangeltech.net>"), cakto_segredo=e("PERFILAI_CAKTO_SEGREDO", ""),
                  dev=e("PERFILAI_DEV", "") == "1", checkouts=json.loads(e("PERFILAI_CHECKOUTS", "") or "{}"),
                  planos_por_produto=json.loads(e("PERFILAI_PLANOS_CAKTO", "") or "{}"), lancamento_ate=e("PERFILAI_LANCAMENTO_ATE", "2026-11-30"),
                  admin_key=e("PERFILAI_ADMIN_KEY", ""), demo_email=e("PERFILAI_DEMO_EMAIL", ""), demo_senha=e("PERFILAI_DEMO_SENHA", ""),
                  cortai_admin_key=e("PERFILAI_CORTAI_ADMIN_KEY", ""))


def ponte_cortai(cfg: Config, email: str, dias: int) -> bool:
    """Turbo do Perfilaí libera o Cortaí Pro no mesmo e-mail (dias=0 revoga). Falha não quebra o webhook."""
    if not cfg.cortai_admin_key:
        return False
    try:
        import httpx
        r = httpx.post(cfg.cortai_url + "/api/admin/cortesia", headers={"x-admin-key": cfg.cortai_admin_key}, json={"email": email, "plano": "pro", "dias": dias}, timeout=20)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        log.warning("ponte Cortaí falhou para %s", email)
        return False


def pasta_plano(cfg: Config, pid: str) -> Path:
    return Path(cfg.dados) / "planos" / pid


def processar(db: Banco, cfg: Config, p: dict) -> None:
    pid = p["id"]
    entrada = json.loads(p["entrada"])
    pasta = pasta_plano(cfg, pid)

    def avisar(etapa: str, prog: float) -> None:
        db.exec("UPDATE planos SET etapa=?, progresso=? WHERE id=?", (etapa, round(prog, 3), pid))

    try:
        prints = [pasta / n for n in entrada.get("prints") or [] if (pasta / n).exists()]
        res = analise.plano(cfg, entrada, prints, avisar)
        avisar("Desenhando os carrosséis", 0.85)
        res["carrosseis_png"] = [pecas.carrossel(c, entrada.get("arroba", ""), entrada.get("cor", ""), pasta, i)
                                 for i, c in enumerate(res.get("carrosseis") or [], 1)]
        db.exec("UPDATE planos SET estado='pronto', etapa='Pronto', progresso=1, resultado=?, fim=? WHERE id=?",
                (json.dumps(res, ensure_ascii=False), agora(), pid))
        u = db.um("SELECT email FROM usuarios WHERE id=?", (p["usuario"],))
        if u:
            mailer.pronto(cfg, u["email"], entrada.get("arroba", ""))
    except Exception as e:  # noqa: BLE001
        log.exception("plano %s falhou", pid)
        db.exec("UPDATE planos SET estado='erro', etapa='Não deu certo', erro=?, fim=? WHERE id=?",
                ("Algo deu errado do nosso lado. Esse plano não conta no seu limite; tente de novo.", agora(), pid))


def _fila(db: Banco, cfg: Config, parar: threading.Event) -> None:
    db.exec("UPDATE planos SET estado='fila' WHERE estado='rodando'")
    while not parar.is_set():
        p = db.um("""SELECT p.* FROM planos p JOIN usuarios u ON u.id=p.usuario WHERE p.estado='fila'
                     ORDER BY CASE u.plano WHEN 'turbo' THEN 0 ELSE 1 END, p.criado LIMIT 1""")
        if not p:
            parar.wait(2)
            continue
        db.exec("UPDATE planos SET estado='rodando', etapa='Começando' WHERE id=?", (p["id"],))
        processar(db, cfg, p)


def criar_app(cfg: Config | None = None, iniciar_fila: bool = True) -> FastAPI:
    cfg = cfg or carregar()
    Path(cfg.dados).mkdir(parents=True, exist_ok=True)
    db = Banco(os.path.join(cfg.dados, "perfilai.db"))
    app = FastAPI(title="Perfilaí", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cfg, app.state.db = cfg, db
    if cfg.demo_email:
        u = auth.usuario_por_email(db, cfg.demo_email.lower())
        db.exec("UPDATE usuarios SET plano='turbo', ativo_ate=? WHERE id=?", (agora() + 3650 * 86400, u["id"]))
    if iniciar_fila:
        app.state.parar = threading.Event()
        threading.Thread(target=_fila, args=(db, cfg, app.state.parar), daemon=True, name="fila").start()

    def usuario(request: Request, obrigatorio=True):
        u = auth.usuario_da_sessao(db, cfg.segredo_sessao, request.cookies.get(COOKIE))
        if not u and obrigatorio:
            raise HTTPException(401, "entre na sua conta")
        return u

    def eh_demo(u: dict) -> bool:
        return bool(cfg.demo_email) and u["email"] == cfg.demo_email.lower()

    def conta(u: dict) -> dict:
        assin = auth.assinante(u)
        pl = PLANOS.get(u.get("plano") or "start") if assin else None
        ini = agora() - 30 * 86400
        usados = db.um("SELECT COUNT(*) n FROM planos WHERE usuario=? AND criado>? AND estado!='erro'", (u["id"], ini))["n"]
        limite = pl["planos_mes"] if pl else 0
        return {"email": u["email"], "assinante": assin, "plano": u.get("plano") if assin else None, "usados": usados, "limite": limite,
                "restam": max(0, limite - usados) if not eh_demo(u) else 99, "planos": planos_publicos(),
                "cortai": cfg.cortai_url + "/?entrar=1" if assin and u.get("plano") == "turbo" else None}

    def planos_publicos() -> list[dict]:
        return [{"codigo": k, **v, "checkout": cfg.checkouts.get(k) or "", "lancamento_ate": cfg.lancamento_ate} for k, v in PLANOS.items()]

    def publico(p: dict) -> dict:
        out = {k: p[k] for k in ("id", "estado", "etapa", "progresso", "erro", "criado", "fim")}
        out["entrada"] = {k: v for k, v in json.loads(p["entrada"]).items() if k != "prints"}
        if p.get("resultado"):
            r = json.loads(p["resultado"])
            r["carrosseis_png"] = [[f"/api/planos/{p['id']}/arquivo/{n}" for n in grupo] for grupo in r.get("carrosseis_png") or []]
            out["resultado"] = r
        if p["estado"] == "fila":
            out["posicao"] = db.um("SELECT COUNT(*) n FROM planos WHERE estado='fila' AND criado<?", (p["criado"],))["n"]
        return out

    @app.get("/health")
    def health():
        return {"ok": True}

    def _login(u: dict) -> JSONResponse:
        token = auth.criar_sessao(db, cfg.segredo_sessao, u["id"])
        resp = JSONResponse({"ok": True})
        resp.set_cookie(COOKIE, token, max_age=auth.SESSAO_S, httponly=True, secure=not cfg.dev, samesite="lax", path="/")
        return resp

    @app.post("/api/entrar/codigo")
    async def pedir_codigo(request: Request):
        b = await request.json()
        email = auth.normalizar_email(b.get("email"))
        if not email:
            raise HTTPException(422, "e-mail inválido")
        cod, motivo = auth.novo_codigo(db, cfg.segredo_sessao, email)
        if motivo == "espere":
            raise HTTPException(429, "acabamos de mandar um código; espere alguns segundos")
        enviado = mailer.codigo(cfg, email, cod)
        return {"ok": True, "enviado": enviado, **({"codigo_dev": cod} if cfg.dev else {})}

    @app.post("/api/entrar")
    async def entrar(request: Request):
        b = await request.json()
        email = auth.normalizar_email(b.get("email"))
        if not email:
            raise HTTPException(422, "e-mail inválido")
        r = auth.conferir_codigo(db, cfg.segredo_sessao, email, str(b.get("codigo") or ""))
        if r != "ok":
            raise HTTPException(400, {"invalido": "código errado", "expirado": "código vencido; peça outro", "tentativas": "muitas tentativas; peça outro código"}[r])
        return _login(auth.usuario_por_email(db, email))

    senha_rotas.registrar(app, db, cfg, mailer, _login, usuario)  # senha (padrão), código (opção), esqueci a senha

    @app.post("/api/sair")
    def sair(request: Request):
        auth.encerrar_sessao(db, cfg.segredo_sessao, request.cookies.get(COOKIE))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    @app.get("/api/planos-venda")
    def planos_venda():
        return {"planos": planos_publicos()}

    @app.get("/api/conta")
    def ver_conta(request: Request):
        return conta(usuario(request))

    @app.post("/api/planos")
    async def novo_plano(request: Request):
        u = usuario(request)
        c = conta(u)
        if c["restam"] <= 0:
            raise HTTPException(402, "escolha um plano para começar" if not c["assinante"] else "você usou os planos do mês; suba de plano para continuar")
        if db.um("SELECT COUNT(*) n FROM planos WHERE usuario=? AND estado IN ('fila','rodando')", (u["id"],))["n"] >= 1:
            raise HTTPException(429, "espere o plano atual ficar pronto")
        b = await request.json()
        arroba = re.sub(r"[^A-Za-z0-9_.]", "", str(b.get("arroba") or "").strip().lstrip("@"))[:30]
        if not arroba:
            raise HTTPException(422, "informe o @ do perfil")
        objetivo = str(b.get("objetivo") or "").strip()[:300]
        if len(objetivo) < 5:
            raise HTTPException(422, "conte em uma frase o que você quer com o Instagram (vender o quê, para quem)")
        cor = str(b.get("cor") or "#b46bff")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", cor):
            cor = "#b46bff"
        pid = uuid.uuid4().hex[:16]
        pasta = pasta_plano(cfg, pid)
        pasta.mkdir(parents=True, exist_ok=True)
        nomes = []
        for i, d in enumerate((b.get("prints") or [])[:3], 1):
            m = re.match(r"data:image/(png|jpe?g|webp);base64,(.+)", str(d), re.S)
            if not m:
                continue
            bruto = base64.b64decode(m.group(2))
            if len(bruto) > 6 * 1024 * 1024:
                shutil.rmtree(pasta, ignore_errors=True)
                raise HTTPException(413, "cada print pode ter até 6 MB")
            ext = "png" if m.group(1) == "png" else "jpg"
            (pasta / f"print{i}.{ext}").write_bytes(bruto)
            nomes.append(f"print{i}.{ext}")
        entrada = {"arroba": arroba, "objetivo": objetivo, "nicho": str(b.get("nicho") or "").strip()[:80],
                   "produto": str(b.get("produto") or "").strip()[:200], "cor": cor, "prints": nomes}
        db.exec("INSERT INTO planos(id,usuario,entrada,criado) VALUES(?,?,?,?)", (pid, u["id"], json.dumps(entrada, ensure_ascii=False), agora()))
        return publico(db.um("SELECT * FROM planos WHERE id=?", (pid,)))

    @app.get("/api/planos")
    def meus_planos(request: Request):
        u = usuario(request)
        return {"planos": [publico(p) for p in db.todos("SELECT * FROM planos WHERE usuario=? ORDER BY criado DESC LIMIT 30", (u["id"],))]}

    @app.get("/api/planos/{pid}")
    def um_plano(pid: str, request: Request):
        u = usuario(request)
        p = db.um("SELECT * FROM planos WHERE id=? AND usuario=?", (pid, u["id"]))
        if not p:
            raise HTTPException(404, "plano não encontrado")
        return publico(p)

    @app.get("/api/planos/{pid}/arquivo/{nome}")
    def arquivo(pid: str, nome: str, request: Request):
        u = usuario(request)
        if not db.um("SELECT 1 FROM planos WHERE id=? AND usuario=?", (pid, u["id"])) or not re.fullmatch(r"carrossel\d_\d{2}\.png", nome):
            raise HTTPException(404, "não encontrado")
        f = pasta_plano(cfg, pid) / nome
        if not f.exists():
            raise HTTPException(404, "não encontrado")
        return FileResponse(f, media_type="image/png")

    @app.get("/api/planos/{pid}/site.zip")
    def site(pid: str, request: Request, checkout: str = ""):
        u = usuario(request)
        p = db.um("SELECT * FROM planos WHERE id=? AND usuario=? AND estado='pronto'", (pid, u["id"]))
        if not p:
            raise HTTPException(404, "plano não encontrado")
        r = json.loads(p["resultado"])
        if checkout and not re.match(r"^https://[^\s\"'<>]+$", checkout):
            checkout = ""
        z = pecas.site_zip(r.get("site") or {}, r.get("perfil") or {}, json.loads(p["entrada"]).get("cor", ""), checkout)
        return Response(z, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="site-{r["perfil"].get("arroba", "perfil")}.zip"'})

    # ------------------------------------------------ Cakto
    @app.post("/api/cakto")
    async def cakto(request: Request):
        cru = await request.body()
        try:
            b = json.loads(cru)
        except ValueError:
            raise HTTPException(400, "json")
        if not cfg.cakto_segredo or not hmac.compare_digest(str(b.get("secret") or ""), cfg.cakto_segredo):
            raise HTTPException(401, "segredo")
        evento = str(b.get("event") or "")
        dados = b.get("data") or {}
        if isinstance(dados, list):
            dados = dados[0] if dados else {}
        eid = str(dados.get("id") or hashlib.sha256(cru).hexdigest()[:24]) + ":" + evento
        if db.um("SELECT 1 FROM eventos_cakto WHERE id=?", (eid,)):
            return {"ok": True, "repetido": True}
        db.exec("INSERT INTO eventos_cakto(id,recebido,corpo) VALUES(?,?,?)", (eid, agora(), cru.decode("utf-8", "replace")[:20000]))
        email = auth.normalizar_email((dados.get("customer") or {}).get("email"))
        if not email:
            return {"ok": True, "ignorado": "sem email"}
        u = auth.usuario_por_email(db, email)
        if evento in ("purchase_approved", "subscription_renewed", "subscription_created"):
            plano = cfg.planos_por_produto.get(str((dados.get("product") or {}).get("id") or ""), "start")
            db.exec("UPDATE usuarios SET plano=?, ativo_ate=?, pedido=? WHERE id=?", (plano, max(agora(), u["ativo_ate"]) + 32 * 86400, str(dados.get("id") or ""), u["id"]))
            cortai = ponte_cortai(cfg, email, 32) if plano == "turbo" else None
            return {"ok": True, "liberado": email, **({"cortai": cortai} if cortai is not None else {})}
        if evento in ("refund", "chargeback", "subscription_canceled", "subscription_cancelled"):
            db.exec("UPDATE usuarios SET ativo_ate=? WHERE id=?", (agora(), u["id"]))
            if u.get("plano") == "turbo":
                ponte_cortai(cfg, email, 0)
            return {"ok": True, "revogado": email}
        return {"ok": True, "ignorado": evento}

    # ------------------------------------------------ admin
    def exigir_admin(request: Request):
        chave = request.headers.get("x-admin-key") or ""
        if not cfg.admin_key or not hmac.compare_digest(chave, cfg.admin_key):
            raise HTTPException(401, "chave de admin")

    @app.get("/api/admin/resumo")
    def admin_resumo(request: Request):
        exigir_admin(request)
        ativos = db.todos("SELECT plano, COUNT(*) n FROM usuarios WHERE ativo_ate>? GROUP BY plano", (agora(),))
        return {"produto": "perfilai", "nome": "Perfilaí", "url": cfg.base_url, "assinantes": sum(r["n"] for r in ativos),
                "por_plano": {r["plano"]: r["n"] for r in ativos},
                "receita_mensal": round(sum(r["n"] * (PLANOS.get(r["plano"]) or PLANOS["start"])["preco"] for r in ativos), 2),
                "cadastros": db.um("SELECT COUNT(*) n FROM usuarios")["n"],
                "planos_7d": db.um("SELECT COUNT(*) n FROM planos WHERE criado>?", (agora() - 7 * 86400,))["n"], "planos": planos_publicos()}

    @app.get("/api/admin/assinantes")
    def admin_assinantes(request: Request):
        exigir_admin(request)
        linhas = db.todos("SELECT id, email, criado, plano, ativo_ate, pedido FROM usuarios ORDER BY ativo_ate DESC, criado DESC LIMIT 1000")
        for l in linhas:
            l["ativo"] = l["ativo_ate"] > agora()
        return {"assinantes": linhas}

    @app.get("/")
    def inicio():
        return FileResponse(ESTATICO / "index.html")

    @app.get("/app")
    def painel(request: Request):
        if not usuario(request, obrigatorio=False):
            return RedirectResponse("/?entrar=1", status_code=303)
        return FileResponse(ESTATICO / "app.html")

    app.mount("/s", StaticFiles(directory=ESTATICO), name="estatico")
    return app


app = criar_app() if os.environ.get("PERFILAI_SEM_APP") != "1" else None
