"""O plano do perfil: o diretor (GPT via rt-planejar) lê os prints e decide a estratégia; o Qwen (rt-geral) escreve o volume.

1. leitura dos prints do perfil pelo modelo de visão (bio, seguidores, posts, temas, o que engaja);
2. diretor: raio-x + estratégia + pauta (lista de 30 ideias com gancho) + referências do nicho;
3. mão de obra: 3 bios, 5 roteiros de Reels, roteiros de Stories de venda, 3 carrosséis, texto do site.
Cada passo devolve JSON; se o diretor falhar, o modelo da casa faz o passo (nunca fica sem plano).
"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

import httpx

log = logging.getLogger("perfilai.analise")

GANCHOS = ["Ninguém está falando sobre isso", "Eu queria ter descoberto isso antes", "Pega o hábito de…", "Faça isso para…", "Aqui está a verdade",
           "É assim que…", "Isso pode te surpreender", "Você não precisa disso agora", "Talvez você não concorde com isso", "Acabei de descobrir isso"]

LER_PRINTS = """Estes são prints do perfil de Instagram @{arroba}. Leia o que estiver visível e responda SÓ com JSON:
{{"bio_atual": "", "seguidores": "número ou vazio", "seguindo": "", "publicacoes": "", "destaques": ["nomes dos destaques"],
  "posts_visiveis": [{{"tema": "", "formato": "reels|carrossel|foto", "sinal_de_engajamento": "visualizações/curtidas se aparecer"}}],
  "estetica": "cores e estilo visual em 1 frase", "observacoes": "o que chama atenção (bom e ruim) em 2 frases"}}"""

DIRETOR = """Você é estrategista de Instagram sênior e vai DIRIGIR o plano de conteúdo de um cliente. Seja específico ao nicho, prático e honesto.
Perfil: @{arroba}. Nicho: {nicho}. Objetivo: {objetivo}. Produto/serviço: {produto}.
Leitura dos prints (pode estar vazia se a pessoa não mandou): {leitura}

Ganchos que costumam funcionar (use como repertório, adaptando): {ganchos}

Responda SÓ com JSON:
{{"raio_x": {{"nota": 0-100, "resumo": "2 frases", "fortes": ["3 itens"], "fracos": ["3 itens"], "prioridades": ["as 3 mudanças que mais trazem resultado, em ordem"]}},
  "estrategia": {{"posicionamento": "1 frase de quem a pessoa é para quem", "pilares": ["4 pilares de conteúdo"], "frequencia": "ex.: 4 Reels + stories diários",
                 "formatos": ["formatos recomendados e por quê, 3 itens"]}},
  "ideias": [{{"formato": "reels|stories|carrossel|post", "gancho": "frase de abertura", "ideia": "1 frase", "pilar": ""}}],
  "referencias": [{{"perfil": "tipo de perfil grande do nicho (sem inventar @ que você não tem certeza que existe)", "o_que_fazem": "", "copiar": "", "evitar": ""}}],
  "briefing_mao_de_obra": "instruções detalhadas para o redator que vai escrever bios, roteiros, stories, carrosséis e a página de vendas: tom de voz, palavras do nicho, promessa central, provas, objeções a quebrar"}}
As ideias são exatamente 30, variadas entre os formatos. As referências são 3."""

REDATOR_BASE = """Você é redator de Instagram. Siga o briefing do diretor à risca. Português do Brasil, sem emoji em excesso, sem promessa de resultado garantido.
Perfil @{arroba}, nicho {nicho}, objetivo {objetivo}, produto {produto}.
Briefing do diretor: {briefing}
Posicionamento: {posicionamento}. Pilares: {pilares}.
Responda SÓ com JSON válido (aspas duplas, sem comentários), exatamente neste formato:
"""

PARTES = {
    "bios_stories": """{{"bios": ["3 bios de até 150 caracteres, com chamada no fim"],
  "stories_venda": [{{"nome": "", "sequencia": ["story 1: ...", "story 2: ...", "story 3: ..."]}}]}}
Stories de venda: 3 sequências (uma "procuro N pessoas com <problema>, digita EU", uma "recebi uma mensagem" com enquete e depoimento, uma de bastidores com oferta).""",
    "roteiros": """{{"roteiros": [{{"titulo": "", "gancho": "fala dos 3 primeiros segundos", "cenas": ["fala/ação cena a cena, 4 a 6 itens"], "texto_tela": "", "legenda": "", "hashtags": ["5"]}}]}}
Exatamente 5 roteiros de Reels de 20 a 40 segundos.""",
    "carrosseis_site": """{{"carrosseis": [{{"titulo": "título da capa (até 50 letras)", "laminas": ["texto de cada lâmina, até 140 letras, 5 a 7 lâminas"], "legenda": ""}}],
  "site": {{"titulo": "promessa principal", "subtitulo": "", "beneficios": ["4"], "prova": "frase de prova social genérica sem inventar números", "oferta": "", "chamada": "texto do botão",
           "faq": [{{"p": "", "r": ""}}]}}}}
Exatamente 3 carrosséis. FAQ com 4 perguntas.""",
    "renda_extra": """{{"renda_extra": {{"servico": "nome do serviço que a pessoa pode vender fazendo para outros o que este plano fez por ela",
  "para_quem": "tipo de cliente (ex.: pequenos negócios do mesmo nicho da cidade)", "preco_sugerido": "faixa em reais por mês ou por pacote",
  "entregaveis": ["4 a 6 itens do pacote"], "abordagem": ["3 mensagens curtas de abordagem por direct/WhatsApp"], "proposta": "texto curto de proposta comercial",
  "cuidados": ["2 a 3 cuidados: sem prometer seguidores ou vendas, contrato simples, aprovar antes de publicar"]}}}}
Seja realista: sem promessa de ganho garantido.""",
}


def _json(txt: str) -> dict:
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S)
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M)
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise ValueError("sem JSON")
    bruto = m.group(0)
    try:
        return json.loads(bruto)
    except ValueError:
        conserto = re.sub(r",\s*([}\]])", r"\1", bruto)  # vírgula sobrando antes de } ou ]
        return json.loads(conserto, strict=False)        # strict=False aceita quebra de linha dentro de texto


def _chat(cfg, cliente: httpx.Client, modelos: list[str], conteudo, max_tokens: int, temperatura: float = 0.6) -> dict:
    ultimo = None
    for modelo in [m for m in dict.fromkeys(m for m in modelos if m) for _ in (0, 1)]:
        try:
            r = cliente.post(cfg.llm_base + "/chat/completions", headers={"Authorization": f"Bearer {cfg.llm_key}"}, timeout=300,
                             json={"model": modelo, "temperature": temperatura, "max_tokens": max_tokens, "chat_template_kwargs": {"enable_thinking": False},
                                   "messages": [{"role": "user", "content": conteudo}]})
            r.raise_for_status()
            return _json(r.json()["choices"][0]["message"]["content"])
        except Exception as e:  # noqa: BLE001
            ultimo = e
            log.warning("modelo %s falhou: %s", modelo, e)
    raise RuntimeError(f"IA indisponível: {ultimo}")


def ler_prints(cfg, cliente: httpx.Client, arroba: str, prints: list[Path]) -> dict:
    if not prints:
        return {}
    partes = [{"type": "text", "text": LER_PRINTS.format(arroba=arroba)}]
    for p in prints[:3]:
        tipo = "png" if p.suffix.lower() == ".png" else "jpeg"
        partes.append({"type": "image_url", "image_url": {"url": f"data:image/{tipo};base64,{base64.b64encode(p.read_bytes()).decode()}"}})
    try:
        return _chat(cfg, cliente, [cfg.llm_visao], partes, 900, 0.2)
    except RuntimeError:
        return {}


def plano(cfg, entrada: dict, prints: list[Path], avisar) -> dict:
    a = {k: str(entrada.get(k) or "").strip() for k in ("arroba", "nicho", "objetivo", "produto")}
    with httpx.Client() as c:
        avisar("Lendo os prints do seu perfil", 0.1)
        leitura = ler_prints(cfg, c, a["arroba"], prints)
        avisar("O diretor está montando a estratégia", 0.3)
        d = _chat(cfg, c, [cfg.llm_planejador, cfg.llm_modelo], DIRETOR.format(**a, leitura=json.dumps(leitura, ensure_ascii=False)[:3000],
                                                                                ganchos="; ".join(GANCHOS)), 6000, 0.6)
        est = d.get("estrategia") or {}
        avisar("Escrevendo bios, roteiros, stories e carrosséis", 0.6)
        base = REDATOR_BASE.format(**a, briefing=str(d.get("briefing_mao_de_obra") or "")[:3000], posicionamento=est.get("posicionamento", ""),
                                   pilares=", ".join(est.get("pilares") or []))
        w: dict = {}
        for k, (nome, parte) in enumerate(PARTES.items()):
            avisar(["Escrevendo bios e stories de venda", "Escrevendo os roteiros de Reels", "Escrevendo carrosséis e o site", "Montando o plano de renda extra"][k], 0.55 + 0.08 * k)
            try:
                w.update(_chat(cfg, c, [cfg.llm_modelo, cfg.llm_planejador], base + parte.format(), 3500, 0.7))
            except RuntimeError as e:  # uma parte que falhou não derruba o plano inteiro
                log.warning("parte %s ficou de fora: %s", nome, e)
        if not (w.get("bios") or w.get("roteiros")):
            raise RuntimeError("redator não respondeu")
    ideias = [i for i in d.get("ideias") or [] if isinstance(i, dict) and i.get("gancho")][:30]
    return {"perfil": a, "leitura": leitura, "raio_x": d.get("raio_x") or {}, "estrategia": est, "ideias": ideias,
            "referencias": (d.get("referencias") or [])[:3], "bios": (w.get("bios") or [])[:3], "roteiros": (w.get("roteiros") or [])[:5],
            "stories_venda": (w.get("stories_venda") or [])[:3], "carrosseis": (w.get("carrosseis") or [])[:3], "site": w.get("site") or {},
            "renda_extra": w.get("renda_extra") or {}}
