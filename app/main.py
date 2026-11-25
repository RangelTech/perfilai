"""Perfil AI: plano de Instagram com IA (raio-x, bio, 30 ideias, roteiros, stories de venda, carrosséis e site de vendas). API + páginas."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid

import httpx
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app import senha_rotas
from produtos_core import acesso, armazenamento
from app import analise, auth, mailer, marcas, midia_perfil, pecas, rt_midia
from app.db import Banco, agora
from app import admin  # painel /admin e prompts editáveis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("perfilai")
ESTATICO = Path(__file__).resolve().parent.parent / "static"
COOKIE = "perfilai_s"
PLANOS = {  # spec 44 5.2: limite por CONTAS por semana; cada conta até 3 rodadas na semana; 7 posts por semana (1 por dia)
    "start": {"nome": "Start", "preco": 19.90, "depois": 29.90, "contas_semana": 1,
              "itens": ["1 conta por semana (até 3 rodadas)", "Raio-x, bios, 30 ideias e roteiros", "7 posts prontos por semana (1 por dia)", "Kit de marca nas suas fotos e vídeos", "Como vender esse serviço como renda extra"]},
    "pro": {"nome": "Pro", "preco": 49.90, "depois": 59.90, "contas_semana": 3,
            "itens": ["3 contas por semana (até 3 rodadas cada)", "Tudo do Start", "Carrosséis, stories de venda e análise do nicho", "Site de vendas pronto"]},
    "turbo": {"nome": "Top", "preco": 97.00, "depois": 127.00, "contas_semana": 5,
              "itens": ["5 contas por semana (até 3 rodadas cada)", "Tudo do Pro", "Cortaí incluso (cortes e tela dividida)", "Fila prioritária"]},
}
RODADAS_POR_CONTA = 3
POSTS_SEMANA = 7


@dataclass
class Config:
    dados: str = "/data"
    base_url: str = "https://perfilai.rangeltech.net"
    llm_base: str = "https://qwen.rangeltech.net/v1"
    llm_key: str = ""
    llm_modelo: str = "rt-geral"          # mão de obra (Qwen)
    llm_planejador: str = "rt-planejar"   # diretor (GPT)
    llm_visao: str = "visao"              # lê os prints
    hermes_base: str = ""                 # redator pelo Hermes dos produtos (Lucas, 16/11); vazio = direto no llm_base
    hermes_key: str = ""
    segredo_sessao: str = "dev"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_senha: str = ""
    smtp_from: str = "Perfil AI <contato@rangeltech.net>"
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
    pn_url: str = "http://perfil-navegador:8000"   # conexão real com a rede (spec 44 3.3.3), sempre pelo proxy SP
    pn_token: str = ""

    def __post_init__(self):
        self.checkouts = self.checkouts or {}
        self.planos_por_produto = self.planos_por_produto or {}


def carregar() -> Config:
    e = os.environ.get
    return Config(dados=e("PERFILAI_DADOS", "/data"), base_url=e("PERFILAI_BASE_URL", "https://perfilai.rangeltech.net"),
                  llm_base=e("PERFILAI_LLM_BASE", "https://qwen.rangeltech.net/v1"), llm_key=e("PERFILAI_LLM_KEY", ""),
                  llm_modelo=e("PERFILAI_LLM_MODELO", "rt-geral"), llm_planejador=e("PERFILAI_LLM_PLANEJADOR", "rt-planejar"),
                  llm_visao=e("PERFILAI_LLM_VISAO", "visao"), hermes_base=e("PERFILAI_HERMES_BASE", "").rstrip("/"), hermes_key=e("PERFILAI_HERMES_KEY", ""), segredo_sessao=e("PERFILAI_SEGREDO_SESSAO", "dev"),
                  smtp_host=e("SMTP_HOST", ""), smtp_port=int(e("SMTP_PORT", "587") or 587), smtp_user=e("SMTP_USER", ""), smtp_senha=e("SMTP_PASSWORD", ""),
                  smtp_from=e("PERFILAI_SMTP_FROM", "Perfil AI <contato@rangeltech.net>"), cakto_segredo=e("PERFILAI_CAKTO_SEGREDO", ""),
                  dev=e("PERFILAI_DEV", "") == "1", checkouts=json.loads(e("PERFILAI_CHECKOUTS", "") or "{}"),
                  planos_por_produto=json.loads(e("PERFILAI_PLANOS_CAKTO", "") or "{}"), lancamento_ate=e("PERFILAI_LANCAMENTO_ATE", "2026-11-30"),
                  admin_key=e("PERFILAI_ADMIN_KEY", ""), demo_email=e("PERFILAI_DEMO_EMAIL", ""), demo_senha=e("PERFILAI_DEMO_SENHA", ""),
                  cortai_admin_key=e("PERFILAI_CORTAI_ADMIN_KEY", ""),
                  pn_url=e("PERFILAI_PN_URL", "http://perfil-navegador:8000"), pn_token=e("PERFILAI_PN_TOKEN", ""))


def ponte_cortai(cfg: Config, email: str, dias: int) -> bool:
    """Turbo do Perfil AI libera o Cortaí Pro no mesmo e-mail (dias=0 revoga). Falha não quebra o webhook."""
    if not cfg.cortai_admin_key:
        return False
    try:
        import httpx
        r = httpx.post(cfg.cortai_url + "/api/admin/cortesia", headers={"x-admin-key": cfg.cortai_admin_key}, json={"email": email, "plano": "pro", "dias": dias}, timeout=20)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        log.warning("ponte Cortaí falhou para %s", email)
        return False


_ESPELHOS: dict = {}


def espelho(cfg: Config) -> "armazenamento.Espelho":
    """Arquivos no MinIO (fonte oficial), disco em cfg.dados como cache (spec 57 §8.6)."""
    if cfg.dados not in _ESPELHOS:
        _ESPELHOS[cfg.dados] = armazenamento.Espelho(armazenamento.Armazenamento(pasta_local=os.path.join(cfg.dados, "arquivos")), cfg.dados)
    return _ESPELHOS[cfg.dados]


def pasta_plano(cfg: Config, pid: str) -> Path:
    return Path(cfg.dados) / "planos" / pid


def processar(db: Banco, cfg: Config, p: dict) -> None:
    pid = p["id"]
    entrada = json.loads(p["entrada"])
    pasta = pasta_plano(cfg, pid)

    def avisar(etapa: str, prog: float) -> None:
        db.exec("UPDATE planos SET etapa=?, progresso=? WHERE id=?", (etapa, round(prog, 3), pid))

    try:
        espelho(cfg).garantir_pasta(pasta)
        prints = [pasta / n for n in entrada.get("prints") or [] if (pasta / n).exists()]
        res = analise.plano(cfg, entrada, prints, avisar)
        avisar("Desenhando os carrosséis", 0.85)
        res["carrosseis_png"] = [pecas.carrossel(c, entrada.get("arroba", ""), entrada.get("cor", ""), pasta, i)
                                 for i, c in enumerate(res.get("carrosseis") or [], 1)]
        espelho(cfg).guardar_pasta(pasta)
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


def criar_app(cfg: Config | None = None, iniciar_fila: bool = True, pn=None) -> FastAPI:
    cfg = cfg or carregar()
    Path(cfg.dados).mkdir(parents=True, exist_ok=True)
    db = Banco(os.path.join(cfg.dados, "perfilai.db"))
    admin.preparar(db)
    app = FastAPI(title="Perfil AI", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cfg, app.state.db = cfg, db
    if pn is not None:
        app.state.pn = pn
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

    def marca_de(request: Request) -> dict:
        return marcas.por_host(request.headers.get("x-forwarded-host") or request.headers.get("host"))

    def assinatura(u: dict, marca: str) -> tuple[bool, str | None]:
        if marca == "insta":
            return auth.assinante(u), (u.get("plano") if auth.assinante(u) else None)
        a = db.um("SELECT * FROM assinaturas WHERE usuario=? AND marca=?", (u["id"], marca))
        if a and a["ativo_ate"] > agora():
            return True, a["plano"]
        return False, None

    def uso_semana(u: dict, marca: str = "insta") -> dict:
        ini = midia_perfil.inicio_semana(agora())
        linhas = db.todos("SELECT entrada FROM planos WHERE usuario=? AND criado>=? AND estado!='erro'", (u["id"], ini))
        por_conta: dict[str, int] = {}
        for l in linhas:
            e = json.loads(l["entrada"])
            if (e.get("marca") or "insta") != marca:
                continue
            a = (e.get("arroba") or "").lower()
            por_conta[a] = por_conta.get(a, 0) + 1
        posts = db.um("SELECT COUNT(*) n FROM posts WHERE usuario=? AND criado>=?", (u["id"], ini))["n"]
        return {"por_conta": por_conta, "posts": posts}

    def conta(u: dict, marca: str = "insta") -> dict:
        assin, plano_atual = assinatura(u, marca)
        pl = PLANOS.get(plano_atual or "start") if assin else None
        us = uso_semana(u, marca)
        limite = pl["contas_semana"] if pl else 0
        demo = eh_demo(u)
        return {"email": u["email"], "assinante": assin, "plano": plano_atual, "marca": marca,
                "contas_semana": len(us["por_conta"]), "limite_contas": 99 if demo else limite, "rodadas": us["por_conta"], "rodadas_por_conta": RODADAS_POR_CONTA,
                "posts_semana": us["posts"], "limite_posts": 99 if demo else POSTS_SEMANA,
                "restam": 99 if demo else (max(0, limite - len(us["por_conta"])) if assin else 0), "planos": planos_publicos(marca),
                "cortai": cfg.cortai_url + "/?entrar=1" if assin and plano_atual == "turbo" else None}

    def planos_publicos(marca: str = "insta") -> list[dict]:
        ck = lambda k: (cfg.checkouts.get(f"{marca}:{k}") or (cfg.checkouts.get(k) if marca == "insta" else "")) or ""  # noqa: E731
        return [{"codigo": k, **v, "checkout": ck(k), "lancamento_ate": cfg.lancamento_ate} for k, v in PLANOS.items()]

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

    acesso.registrar(app, db, enviar=lambda para, assunto, texto, html: mailer.enviar(cfg, para, assunto, texto, html),
                     login=_login, usuario=usuario, criar_usuario=lambda email: auth.usuario_por_email(db, email),
                     produto="Perfil AI", base_url=cfg.base_url, destino="/app", cor="#b46bff",
                     demo_email=lambda: cfg.demo_email, demo_senha=lambda: cfg.demo_senha, dev=cfg.dev)  # cadastro e login comuns (spec 57 §5A)
    armazenamento.registrar(app, espelho(cfg).arm)  # MinIO (spec 57 §8.6)

    @app.post("/api/sair")
    def sair(request: Request):
        auth.encerrar_sessao(db, cfg.segredo_sessao, request.cookies.get(COOKIE))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    @app.get("/api/planos-venda")
    def planos_venda(request: Request):
        return {"planos": planos_publicos(marca_de(request)["id"])}

    @app.get("/api/conta")
    def ver_conta(request: Request):
        return conta(usuario(request), marca_de(request)["id"])

    @app.post("/api/planos")
    async def novo_plano(request: Request):
        u = usuario(request)
        c = conta(u, marca_de(request)["id"])
        if not c["assinante"] and not eh_demo(u):
            raise HTTPException(402, "escolha um plano para começar")
        if db.um("SELECT COUNT(*) n FROM planos WHERE usuario=? AND estado IN ('fila','rodando')", (u["id"],))["n"] >= 1:
            raise HTTPException(429, "espere o plano atual ficar pronto")
        b = await request.json()
        mk = marca_de(request)
        if mk["rede"] in ("linkedin", "facebook"):
            arroba = re.sub(r"[^A-Za-z0-9_./:@-]", "", str(b.get("arroba") or "").strip())[:120]
        else:
            arroba = re.sub(r"[^A-Za-z0-9_.]", "", str(b.get("arroba") or "").strip().lstrip("@"))[:30]
        if not arroba:
            raise HTTPException(422, "informe o " + mk["campo_perfil"].lower())
        if not eh_demo(u):
            ja = c["rodadas"].get(arroba.lower(), 0)
            if ja == 0 and c["contas_semana"] >= c["limite_contas"]:
                raise HTTPException(402, f"você já analisou {c['contas_semana']} conta(s) esta semana, o limite do seu plano; na segunda-feira libera de novo, ou suba de plano")
            if ja >= RODADAS_POR_CONTA:
                raise HTTPException(429, f"essa conta já teve {RODADAS_POR_CONTA} rodadas esta semana; na segunda-feira libera de novo")
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
                espelho(cfg).apagar_pasta(pasta)
                raise HTTPException(413, "cada print pode ter até 6 MB")
            ext = "png" if m.group(1) == "png" else "jpg"
            (pasta / f"print{i}.{ext}").write_bytes(bruto)
            espelho(cfg).guardar(pasta / f"print{i}.{ext}")
            nomes.append(f"print{i}.{ext}")
        entrada = {"arroba": arroba, "objetivo": objetivo, "nicho": str(b.get("nicho") or "").strip()[:80],
                   "produto": str(b.get("produto") or "").strip()[:200], "cor": cor, "prints": nomes, "marca": mk["id"],
                   "curriculo_texto": str(b.get("curriculo_texto") or "").strip()[:12000]}
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
        f = espelho(cfg).garantir(pasta_plano(cfg, pid) / nome)
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
    # ------------------------------------------------------------ posts da semana (spec 44 5.2)
    def post_publico(x: dict) -> dict:
        return {"id": x["id"], "dia": x["dia"], "arroba": x["arroba"], "gancho": x["gancho"], "legenda": x["legenda"], "url": f"/api/posts/{x['id']}.png"}

    @app.get("/api/posts")
    def meus_posts(request: Request):
        u = usuario(request)
        return {"posts": [post_publico(x) for x in db.todos("SELECT * FROM posts WHERE usuario=? ORDER BY criado DESC LIMIT 60", (u["id"],))]}

    @app.get("/api/posts/{nome}")
    def post_arquivo(nome: str, request: Request):
        u = usuario(request)
        pid = nome.removesuffix(".png")
        x = db.um("SELECT * FROM posts WHERE id=? AND usuario=?", (pid, u["id"]))
        if not x or not re.fullmatch(r"[0-9a-f]{16}", pid):
            raise HTTPException(404, "post não encontrado")
        return FileResponse(espelho(cfg).garantir(Path(cfg.dados) / "posts" / x["arquivo"]), media_type="image/png", filename=f"post-{x['dia']}.png")

    @app.post("/api/planos/{pid}/post")
    def gerar_post(pid: str, request: Request):
        """Post do dia: 1 por dia e 7 por semana. Imagem pelo GPT (regra 5.0), gancho e @ por cima."""
        u = usuario(request)
        p = db.um("SELECT * FROM planos WHERE id=? AND usuario=?", (pid, u["id"]))
        if not p or p["estado"] != "pronto":
            raise HTTPException(404, "plano não encontrado ou ainda não ficou pronto")
        c = conta(u, marca_de(request)["id"])
        if not c["assinante"] and not eh_demo(u):
            raise HTTPException(402, "escolha um plano para gerar posts")
        dia = midia_perfil.hoje(agora())
        if not eh_demo(u):
            if db.um("SELECT COUNT(*) n FROM posts WHERE usuario=? AND dia=?", (u["id"], dia))["n"] >= 1:
                raise HTTPException(429, "o post de hoje já saiu; amanhã tem outro")
            if c["posts_semana"] >= POSTS_SEMANA:
                raise HTTPException(429, f"você já gerou os {POSTS_SEMANA} posts desta semana; na segunda-feira libera de novo")
        r = json.loads(p["resultado"])
        ent = json.loads(p["entrada"])
        usados = {x["gancho"] for x in db.todos("SELECT gancho FROM posts WHERE plano=?", (pid,))}
        ideias = [i for i in r.get("ideias") or [] if i.get("gancho") and i["gancho"] not in usados]
        ideias.sort(key=lambda i: 0 if str(i.get("formato", "")).lower() in ("post", "carrossel") else 1)
        if not ideias:
            raise HTTPException(409, "as ideias deste plano acabaram; gere um plano novo para mais posts")
        idei = ideias[0]
        prompt = (f"Instagram feed post image for a {ent.get('nicho') or 'small business'} profile. Scene that illustrates: {idei.get('ideia') or idei['gancho']}. "
                  f"Professional photography or clean illustration, brand color {ent.get('cor') or '#b46bff'} as accent, empty space at the bottom for text, no text, no watermark.")
        try:
            res = rt_midia.imagem(prompt, cfg.llm_base, cfg.llm_key, "1024x1536")
        except rt_midia.ImagemIndisponivel as e:
            raise HTTPException(503, str(e))
        png = midia_perfil.montar_post(res.dados, idei["gancho"], ent.get("arroba") or "", ent.get("cor") or "#b46bff")
        novo = uuid.uuid4().hex[:16]
        pasta = Path(cfg.dados) / "posts"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"{novo}.png").write_bytes(png)
        espelho(cfg).guardar(pasta / f"{novo}.png")
        tags = " ".join("#" + re.sub(r"\W", "", w_) for w_ in (ent.get("nicho") or "").split()[:3] if re.sub(r"\W", "", w_))
        legenda = (str(idei.get("ideia") or "") + ("\n\n" + tags if tags else "")).strip()
        db.exec("INSERT INTO posts(id,usuario,plano,arroba,dia,gancho,legenda,arquivo,rota,criado) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (novo, u["id"], pid, ent.get("arroba"), dia, idei["gancho"], legenda, f"{novo}.png", res.rota, agora()))
        log.info("post %s rota=%s", novo, res.rota)
        return post_publico(db.um("SELECT * FROM posts WHERE id=?", (novo,)))

    # ------------------------------------------------------------ imagens do perfil: foto, capa, ícones (spec 44 3.3.4)
    IMAGENS_SEMANA = 3

    def limite_imagem(u: dict, tipo: str) -> None:
        if eh_demo(u):
            return
        ini = midia_perfil.inicio_semana(agora())
        if db.um("SELECT COUNT(*) n FROM imagens WHERE usuario=? AND tipo=? AND criado>=?", (u["id"], tipo, ini))["n"] >= IMAGENS_SEMANA:
            raise HTTPException(429, f"você já gerou {IMAGENS_SEMANA} desta semana; na segunda-feira libera de novo")

    def guardar_imagens(u: dict, tipo: str, pngs: list[bytes], rota: str) -> dict:
        novo = uuid.uuid4().hex[:16]
        pasta = Path(cfg.dados) / "imagens"
        pasta.mkdir(parents=True, exist_ok=True)
        nomes = []
        for i, b in enumerate(pngs, 1):
            n = f"{novo}_{i}.png"
            (pasta / n).write_bytes(b)
            espelho(cfg).guardar(pasta / n)
            nomes.append(n)
        db.exec("INSERT INTO imagens(id,usuario,tipo,arquivos,rota,criado) VALUES(?,?,?,?,?,?)", (novo, u["id"], tipo, json.dumps(nomes), rota, agora()))
        return {"id": novo, "tipo": tipo, "urls": [f"/api/imagens/{n}" for n in nomes]}

    def exigir_assinante(u: dict, request: Request) -> None:
        if not conta(u, marca_de(request)["id"])["assinante"] and not eh_demo(u):
            raise HTTPException(402, "escolha um plano para gerar imagens")

    @app.get("/api/imagens")
    def minhas_imagens(request: Request):
        u = usuario(request)
        return {"itens": [{"id": x["id"], "tipo": x["tipo"], "urls": [f"/api/imagens/{n}" for n in json.loads(x["arquivos"])]}
                          for x in db.todos("SELECT * FROM imagens WHERE usuario=? ORDER BY criado DESC LIMIT 30", (u["id"],))]}

    @app.get("/api/imagens/{nome}")
    def imagem_arquivo(nome: str, request: Request):
        u = usuario(request)
        if not re.fullmatch(r"[0-9a-f]{16}_\d+\.png", nome):
            raise HTTPException(404, "imagem não encontrada")
        x = db.um("SELECT 1 FROM imagens WHERE usuario=? AND id=?", (u["id"], nome.split("_")[0]))
        if not x:
            raise HTTPException(404, "imagem não encontrada")
        return FileResponse(espelho(cfg).garantir(Path(cfg.dados) / "imagens" / nome), media_type="image/png", filename=nome)

    @app.post("/api/imagens/foto")
    async def gerar_foto(request: Request):
        """Corpo cru: a foto atual da pessoa. A IA melhora luz, fundo e enquadramento mantendo o rosto (edição de imagem do GPT)."""
        u = usuario(request)
        exigir_assinante(u, request)
        limite_imagem(u, "foto")
        bruto = await request.body()
        if len(bruto) < 1000 or len(bruto) > 12 * 1024 * 1024:
            raise HTTPException(422, "mande uma foto (JPG ou PNG) de até 12 MB")
        cor = request.headers.get("x-cor") or "#b46bff"
        try:
            from PIL import Image
            ref = io.BytesIO()
            Image.open(io.BytesIO(bruto)).convert("RGB").save(ref, "PNG")
        except Exception:  # noqa: BLE001
            raise HTTPException(422, "não consegui ler essa foto")
        prompt = ("Professional profile photo of the SAME person in the reference image: keep the face, identity, skin tone and hair exactly the same. "
                  f"Soft studio lighting, clean background in a soft tone of {cor}, sharp focus, head and shoulders, centered, friendly confident expression. No text.")
        try:
            r = rt_midia.imagem(prompt, cfg.llm_base, cfg.llm_key, "1024x1024", referencia=ref.getvalue(), classe="ok")
        except rt_midia.ImagemIndisponivel as e:
            raise HTTPException(503, str(e))
        return guardar_imagens(u, "foto", [midia_perfil.foto_perfil(r.dados)], r.rota)

    @app.post("/api/imagens/capa")
    async def gerar_capa(request: Request):
        u = usuario(request)
        exigir_assinante(u, request)
        mk = marca_de(request)
        if mk["rede"] not in midia_perfil.CAPAS:
            raise HTTPException(422, "capa existe no LinkedIn e no Facebook")
        limite_imagem(u, "capa")
        b = await request.json()
        frase = str(b.get("frase") or "").strip()[:90]
        cor = str(b.get("cor") or mk["cor"])
        nicho = str(b.get("nicho") or "").strip()[:80]
        prompt = (f"Wide abstract banner background for a {mk['rede_nome']} profile cover of a professional in {nicho or 'business'}. "
                  f"Elegant gradient with {cor} as main color, subtle geometric shapes, lots of empty space, modern and clean. No text, no people, no logos.")
        try:
            r = rt_midia.imagem(prompt, cfg.llm_base, cfg.llm_key, "1536x1024", classe="ok")
        except rt_midia.ImagemIndisponivel as e:
            raise HTTPException(503, str(e))
        return guardar_imagens(u, "capa", [midia_perfil.capa(r.dados, mk["rede"], frase, cor)], r.rota)

    @app.post("/api/imagens/icones")
    async def gerar_icones(request: Request):
        """Ícones de destaque do Instagram: uma imagem com 6 ícones em grade 3x2, recortada em 6 capas 1080x1080."""
        u = usuario(request)
        exigir_assinante(u, request)
        limite_imagem(u, "icones")
        b = await request.json()
        temas = [str(t).strip()[:24] for t in (b.get("temas") or []) if str(t).strip()][:6]
        if len(temas) < 2:
            raise HTTPException(422, "diga pelo menos 2 destaques (ex.: Cardápio, Clientes, Dúvidas)")
        while len(temas) < 6:
            temas.append(temas[len(temas) % 2])
        cor = str(b.get("cor") or "#b46bff")
        prompt = ("A 3x2 grid of six minimalist line icons for Instagram story highlight covers, each icon centered in its own equal cell, "
                  f"same thin line style, white icons on a plain {cor} background, generous spacing, no text. Icons, left to right, top to bottom: "
                  + ", ".join(temas) + ".")
        try:
            r = rt_midia.imagem(prompt, cfg.llm_base, cfg.llm_key, "1536x1024", classe="ok")
        except rt_midia.ImagemIndisponivel as e:
            raise HTTPException(503, str(e))
        pngs = midia_perfil.fatiar_icones(r.dados, 3, 2, cor)
        if len(pngs) < 2:
            raise HTTPException(502, "os ícones não saíram bem desta vez; tente de novo")
        return {**guardar_imagens(u, "icones", pngs, r.rota), "temas": temas[:len(pngs)]}

    # ------------------------------------------------------------ kit de marca em foto/vídeo do cliente (sem edição)
    @app.get("/api/kit")
    def meus_kits(request: Request):
        u = usuario(request)
        return {"itens": [{"id": x["id"], "tipo": x["tipo"], "url": f"/api/kit/{x['arquivo']}"} for x in db.todos("SELECT * FROM kits WHERE usuario=? ORDER BY criado DESC LIMIT 30", (u["id"],))]}

    @app.get("/api/kit/{nome}")
    def kit_arquivo(nome: str, request: Request):
        u = usuario(request)
        x = db.um("SELECT * FROM kits WHERE arquivo=? AND usuario=?", (nome, u["id"]))
        if not x:
            raise HTTPException(404, "arquivo não encontrado")
        return FileResponse(espelho(cfg).garantir(Path(cfg.dados) / "kit" / nome), filename=f"com-marca-{nome}")

    @app.post("/api/kit")
    async def novo_kit(request: Request):
        """Corpo cru (foto ou vídeo até 2 min / 200 MB), nome no cabeçalho x-arquivo, @ e cor em x-arroba / x-cor."""
        u = usuario(request)
        c = conta(u, marca_de(request)["id"])
        if not c["assinante"] and not eh_demo(u):
            raise HTTPException(402, "escolha um plano para usar o kit de marca")
        nome = request.headers.get("x-arquivo") or "foto.jpg"
        ext = ("." + nome.rsplit(".", 1)[-1].lower()) if "." in nome else ".jpg"
        foto = ext in (".jpg", ".jpeg", ".png", ".webp")
        if not foto and ext not in (".mp4", ".mov", ".webm", ".m4v"):
            raise HTTPException(422, "mande uma foto (JPG, PNG) ou um vídeo (MP4, MOV)")
        arroba = re.sub(r"[^A-Za-z0-9_.]", "", (request.headers.get("x-arroba") or "").lstrip("@"))[:30]
        if not arroba:
            raise HTTPException(422, "informe o @ que vai aparecer")
        cor = request.headers.get("x-cor") or "#b46bff"
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", cor):
            cor = "#b46bff"
        pasta = Path(cfg.dados) / "kit"
        pasta.mkdir(parents=True, exist_ok=True)
        novo = uuid.uuid4().hex[:16]
        tmp = pasta / f"{novo}_in{ext}"
        total = 0
        with open(tmp, "wb") as f:
            async for parte in request.stream():
                total += len(parte)
                if total > 200 * 1024 * 1024:
                    f.close()
                    tmp.unlink(missing_ok=True)
                    raise HTTPException(413, "o arquivo passa de 200 MB")
                f.write(parte)
        if total < 500:
            tmp.unlink(missing_ok=True)
            raise HTTPException(422, "o arquivo chegou vazio")
        try:
            if foto:
                saida = f"{novo}.jpg"
                midia_perfil.kit_foto(tmp, pasta / saida, arroba, cor)
            else:
                dur = midia_perfil.duracao(tmp)
                if dur <= 0 or dur > midia_perfil.MAX_VIDEO_S:
                    raise HTTPException(422, "o vídeo pode ter até 2 minutos")
                saida = f"{novo}.mp4"
                midia_perfil.kit_video(tmp, pasta / saida, arroba, cor)
        finally:
            tmp.unlink(missing_ok=True)
        espelho(cfg).guardar(pasta / saida)
        db.exec("INSERT INTO kits(id,usuario,arquivo,tipo,criado) VALUES(?,?,?,?,?)", (novo, u["id"], saida, "foto" if foto else "video", agora()))
        return {"id": novo, "tipo": "foto" if foto else "video", "url": f"/api/kit/{saida}"}

    # ------------------------------------------------ conexão real (spec 44 3.3.3): sessão vale na semana e some ao aplicar
    from app.pn import PN, PNErro
    pn = app.state.pn if hasattr(app.state, "pn") else PN(cfg.pn_url, cfg.pn_token)

    def chave_pn(u: dict, marca: str) -> str:
        return f"perfilai:{u['id']}:{marca}"

    def conexao(u: dict, marca: str) -> dict | None:
        c = db.um("SELECT * FROM conexoes WHERE usuario=? AND marca=?", (u["id"], marca))
        if c and c["estado"] in ("conectada", "conectando") and c["semana"] < midia_perfil.inicio_semana(agora()):
            try:
                pn.apagar(chave_pn(u, marca))
            except PNErro:
                pass
            db.exec("UPDATE conexoes SET estado='expirou', login_id=NULL WHERE usuario=? AND marca=?", (u["id"], marca))
            c = db.um("SELECT * FROM conexoes WHERE usuario=? AND marca=?", (u["id"], marca))
        return c

    def vista_conexao(u: dict, marca: str, r: dict | None = None) -> dict:
        passo = (r or {}).get("passo") or {}
        if passo.get("tipo") == "conectado":
            db.exec("UPDATE conexoes SET estado='conectada', login_id=NULL WHERE usuario=? AND marca=?", (u["id"], marca))
        elif passo.get("tipo") == "erro":
            db.exec("UPDATE conexoes SET estado='desconectada', login_id=NULL WHERE usuario=? AND marca=?", (u["id"], marca))
        c = conexao(u, marca) or {"estado": "desconectada", "rotulo": "", "aplicada": None}
        return {"estado": c["estado"], "rotulo": c["rotulo"], "aplicada": c.get("aplicada"), "passo": passo or None}

    def erro_pn(e):
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, e.mensagem)

    @app.get("/api/conexao")
    def conexao_get(request: Request):
        u = usuario(request)
        return vista_conexao(u, marca_de(request)["id"])

    @app.post("/api/conexao")
    async def conexao_nova(request: Request):
        u = usuario(request)
        m = marca_de(request)
        b = await request.json()
        if not assinatura(u, m["id"])[0] and not eh_demo(u):
            raise HTTPException(402, "escolha um plano para conectar e aplicar")
        c = conexao(u, m["id"])
        if c and c["estado"] == "aplicada" and c["semana"] >= midia_perfil.inicio_semana(agora()):
            raise HTTPException(429, "você já aplicou as mudanças desta semana; a próxima rodada abre na segunda")
        if not b.get("aceite"):
            raise HTTPException(422, "aceite os termos para continuar")
        usuario_rede, senha = str(b.get("usuario") or "").strip()[:120], str(b.get("senha") or "")
        if m["rede"] != "tiktok" and (not usuario_rede or not senha):
            raise HTTPException(422, "informe usuário e senha")
        try:
            r = pn.login(m["rede"], chave_pn(u, m["id"]), usuario_rede, senha)
        except PNErro as e:
            erro_pn(e)
        del senha
        db.exec("INSERT INTO conexoes(usuario,marca,estado,login_id,semana,rotulo,criado) VALUES(?,?,?,?,?,?,?) ON CONFLICT(usuario,marca) DO UPDATE SET "
                "estado=excluded.estado, login_id=excluded.login_id, semana=excluded.semana, rotulo=excluded.rotulo, aplicada=NULL",
                (u["id"], m["id"], "conectando", r.get("id"), midia_perfil.inicio_semana(agora()), usuario_rede, agora()))
        return vista_conexao(u, m["id"], r)

    @app.get("/api/conexao/login")
    def conexao_status(request: Request):
        u = usuario(request)
        m = marca_de(request)["id"]
        c = conexao(u, m)
        if not c or not c["login_id"]:
            return vista_conexao(u, m)
        try:
            return vista_conexao(u, m, pn.login_status(c["login_id"]))
        except PNErro as e:
            erro_pn(e)

    @app.post("/api/conexao/login")
    async def conexao_responder(request: Request):
        u = usuario(request)
        m = marca_de(request)["id"]
        c = conexao(u, m)
        if not c or not c["login_id"]:
            raise HTTPException(409, "comece a conexão de novo")
        valor = str((await request.json()).get("valor") or "")[:200]
        try:
            return vista_conexao(u, m, pn.responder(c["login_id"], valor))
        except PNErro as e:
            erro_pn(e)

    @app.delete("/api/conexao")
    def conexao_apagar(request: Request):
        u = usuario(request)
        m = marca_de(request)["id"]
        try:
            pn.apagar(chave_pn(u, m))
        except PNErro:
            pass
        db.exec("UPDATE conexoes SET estado='desconectada', login_id=NULL WHERE usuario=? AND marca=?", (u["id"], m))
        return {"ok": True}

    @app.post("/api/conexao/perfil")
    def conexao_perfil(request: Request):
        """Lê o perfil real (nome, bio, link, números) pela sessão conectada."""
        u = usuario(request)
        m = marca_de(request)["id"]
        c = conexao(u, m)
        if not c or c["estado"] != "conectada":
            raise HTTPException(409, "conecte a conta primeiro")
        try:
            return pn.perfil(chave_pn(u, m))
        except PNErro as e:
            erro_pn(e)

    @app.post("/api/planos/{pid}/aplicar")
    async def aplicar_plano(pid: str, request: Request):
        """Aplica no perfil real o que a rede deixa mudar por fora do app (Instagram: nome, bio, link). Depois apaga a sessão."""
        u = usuario(request)
        m = marca_de(request)
        p = db.um("SELECT * FROM planos WHERE id=? AND usuario=?", (pid, u["id"]))
        if not p or p["estado"] != "pronto":
            raise HTTPException(404, "plano não encontrado")
        c = conexao(u, m["id"])
        if not c or c["estado"] != "conectada":
            raise HTTPException(409, "conecte a conta primeiro")
        b = await request.json()
        res = json.loads(p["resultado"])
        proposta = {}
        bios = res.get("bios") or []
        i = b.get("bio")
        if isinstance(i, int) and 0 <= i < len(bios):
            proposta["bio"] = str(bios[i])[: int(m.get("lim_bio") or 150)]
        for k in ("nome", "link"):
            if isinstance(b.get(k), str) and b[k].strip():
                proposta[k] = b[k].strip()[:200]
        if not proposta:
            raise HTTPException(422, "escolha o que aplicar")
        try:
            r = pn.aplicar(chave_pn(u, m["id"]), proposta)
        except PNErro as e:
            erro_pn(e)
        try:
            pn.apagar(chave_pn(u, m["id"]))
        except PNErro:
            pass
        db.exec("UPDATE conexoes SET estado='aplicada', aplicada=?, login_id=NULL WHERE usuario=? AND marca=?", (agora(), u["id"], m["id"]))
        return {"resultado": r, "aplicado": proposta}

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
            alvo = cfg.planos_por_produto.get(str((dados.get("product") or {}).get("id") or ""), "start")
            marca, _, plano = alvo.rpartition(":")
            marca = marca or "insta"
            if marca == "insta":
                db.exec("UPDATE usuarios SET plano=?, ativo_ate=?, pedido=? WHERE id=?", (plano, max(agora(), u["ativo_ate"]) + 32 * 86400, str(dados.get("id") or ""), u["id"]))
            else:
                atual = db.um("SELECT ativo_ate FROM assinaturas WHERE usuario=? AND marca=?", (u["id"], marca))
                ate = max(agora(), atual["ativo_ate"] if atual else 0) + 32 * 86400
                db.exec("INSERT INTO assinaturas(usuario,marca,plano,ativo_ate,pedido) VALUES(?,?,?,?,?) ON CONFLICT(usuario,marca) DO UPDATE SET plano=excluded.plano, "
                        "ativo_ate=excluded.ativo_ate, pedido=excluded.pedido", (u["id"], marca, plano, ate, str(dados.get("id") or "")))
            cortai = ponte_cortai(cfg, email, 32) if plano == "turbo" else None
            return {"ok": True, "liberado": email, "marca": marca, **({"cortai": cortai} if cortai is not None else {})}
        if evento in ("refund", "chargeback", "subscription_canceled", "subscription_cancelled"):
            alvo = cfg.planos_por_produto.get(str((dados.get("product") or {}).get("id") or ""), "")
            marca = alvo.rpartition(":")[0] or "insta"
            if marca == "insta":
                era_turbo = u.get("plano") == "turbo"
                db.exec("UPDATE usuarios SET ativo_ate=? WHERE id=?", (agora(), u["id"]))
            else:
                a_ = db.um("SELECT plano FROM assinaturas WHERE usuario=? AND marca=?", (u["id"], marca))
                era_turbo = bool(a_) and a_["plano"] == "turbo"
                db.exec("UPDATE assinaturas SET ativo_ate=? WHERE usuario=? AND marca=?", (agora(), u["id"], marca))
            if era_turbo:
                ponte_cortai(cfg, email, 0)
            return {"ok": True, "revogado": email, "marca": marca}
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
        return {"produto": "perfilai", "nome": "Perfil AI", "url": cfg.base_url, "assinantes": sum(r["n"] for r in ativos),
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

    def com_marca(arquivo: str, request: Request) -> HTMLResponse:
        m = marca_de(request)
        h = (ESTATICO / arquivo).read_text(encoding="utf-8")
        pub = marcas.publica(m)
        h = h.replace("{{MARCA_JSON}}", json.dumps(pub, ensure_ascii=False).replace("</", "<\\/"))
        for k in ("nome", "rede_nome", "cor", "cor2", "titulo_pagina", "promessa", "campo_perfil", "exemplo_perfil", "rotulo_bio"):
            h = h.replace("{{" + k.upper() + "}}", str(pub[k]))
        return HTMLResponse(h)

    @app.get("/api/marca")
    def marca_atual(request: Request):
        return marcas.publica(marca_de(request))

    @app.get("/")
    def inicio(request: Request):
        return com_marca("index.html", request)

    @app.get("/app")
    def painel(request: Request):
        if not usuario(request, obrigatorio=False):
            return RedirectResponse("/?entrar=1", status_code=303)
        return com_marca("app.html", request)

    @app.post("/api/curriculo")
    async def curriculo(request: Request):
        """PDF, DOCX, TXT ou áudio (gravação) -> texto do currículo. Corpo cru, nome em x-arquivo. Nada fica guardado."""
        usuario(request)
        nome = (request.headers.get("x-arquivo") or "curriculo.pdf").lower()
        ext = nome.rsplit(".", 1)[-1] if "." in nome else "pdf"
        bruto = await request.body()
        if len(bruto) > 15 * 1024 * 1024:
            raise HTTPException(413, "o arquivo passa de 15 MB")
        if len(bruto) < 50:
            raise HTTPException(422, "o arquivo chegou vazio")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / f"c.{ext}"
            f.write_bytes(bruto)
            try:
                if ext == "pdf":
                    from pypdf import PdfReader
                    texto = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(f)).pages[:12])
                elif ext == "docx":
                    import docx
                    texto = "\n".join(par.text for par in docx.Document(str(f)).paragraphs)
                elif ext in ("txt", "md"):
                    texto = bruto.decode("utf-8", "replace")
                elif ext in ("webm", "ogg", "mp3", "m4a", "wav", "mp4"):
                    with httpx.Client() as c:
                        r = c.post(cfg.llm_base + "/audio/transcriptions", headers={"Authorization": f"Bearer {cfg.llm_key}"},
                                   files={"file": (f.name, bruto, "application/octet-stream")}, data={"model": "whisper-1", "language": "pt"}, timeout=180)
                        r.raise_for_status()
                        texto = r.json().get("text") or ""
                else:
                    raise HTTPException(422, "mande PDF, DOCX, TXT ou um áudio")
            except HTTPException:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("curriculo: %s", e)
                raise HTTPException(422, "não consegui ler esse arquivo; tente outro formato ou cole o texto")
        texto = re.sub(r"[ \t]+", " ", texto).strip()
        if len(texto) < 30:
            raise HTTPException(422, "não achei texto nesse arquivo (PDF escaneado?); cole o texto ou grave um áudio contando a sua trajetória")
        return {"texto": texto[:12000], "caracteres": len(texto)}

    app.include_router(admin.rotas(db, cfg.segredo_sessao, """SELECT email, criado, plano, ativo_ate, (ativo_ate > strftime('%s','now')) ativo
        FROM usuarios ORDER BY criado DESC""", seguro=not cfg.dev))

    @app.get("/admin", response_class=HTMLResponse)
    def pagina_admin():
        return FileResponse(ESTATICO / "admin.html")

    app.mount("/s", StaticFiles(directory=ESTATICO), name="estatico")
    return app


app = criar_app() if os.environ.get("PERFILAI_SEM_APP") != "1" else None
