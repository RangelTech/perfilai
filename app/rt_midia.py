"""Regra de imagem de todos os produtos Rangel Tech (spec 44, 5.0). Arquivo idêntico em cada produto.

1. O harness classifica o pedido (Qwen, barato): ok | sensivel | nsfw.
2. ok/sensivel -> GPT de imagem (llm-access /images/generations, ou /images/edits com referência).
3. Recusa do GPT (política de conteúdo) ou pedido nsfw -> Runware pelo Estúdio do llm-access
   (POST /v1/estudio/gerar efeito "imagem-livre", resultado em GET /v1/estudio/jobs/{id}).
4. Estúdio desligado ou sem saldo -> erro amigável (ImagemIndisponivel), sem expor detalhes.
Cada chamada devolve também a rota usada e o motivo da troca, para o log.
"""
from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass

import httpx

RECUSA = re.compile(r"content[_ ]policy|safety|moderation|not allowed|violat|rejected|blocked|sensitive|inappropriate", re.I)
TAMANHOS_RUNWARE = {"1024x1024": (1024, 1024), "1024x1536": (832, 1216), "1536x1024": (1216, 832)}


class ImagemIndisponivel(RuntimeError):
    """Nenhuma rota conseguiu gerar (mensagem já é amigável)."""


@dataclass
class Resultado:
    dados: bytes
    rota: str          # "gpt" | "runware"
    classe: str        # "ok" | "sensivel" | "nsfw"
    motivo: str = ""   # por que trocou de rota


def _h(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def classificar(prompt: str, base: str, key: str, modelo: str = "rt-geral") -> str:
    """ok | sensivel | nsfw. Na dúvida (erro), 'ok' (o GPT recusa sozinho e caímos no Runware)."""
    if re.search(r"\b(nud[eo]s?|nuas?|pelad[ao]s?|sexo|sexual|porn|nsfw|er[oó]tic|genit|seios? (de fora|nus))\b", prompt, re.I):
        return "nsfw"
    try:
        r = httpx.post(base + "/chat/completions", headers=_h(key), timeout=40, json={
            "model": modelo, "temperature": 0, "max_tokens": 5,
            "messages": [{"role": "system", "content": "Classifique o pedido de imagem. Responda só uma palavra: ok, sensivel ou nsfw. "
                                                        "nsfw = nudez, sexo ou conteúdo adulto explícito. sensivel = violência, sangue, armas, "
                                                        "pessoas reais famosas, marcas. ok = o resto."},
                         {"role": "user", "content": prompt[:1500]}]})
        r.raise_for_status()
        t = (r.json()["choices"][0]["message"]["content"] or "").strip().lower()
        for c in ("nsfw", "sensivel", "ok"):
            if c in t:
                return c
    except Exception:  # noqa: BLE001
        pass
    return "ok"


def _gpt(prompt: str, tamanho: str, base: str, key: str, referencia: bytes | None) -> bytes:
    corpo = {"prompt": prompt, "size": tamanho}
    if referencia:  # o llm-access passa a foto ao GPT como referência (editar mantendo a pessoa)
        corpo["images"] = ["data:image/png;base64," + base64.b64encode(referencia).decode()]
    r = httpx.post(base + "/images/generations", headers=_h(key), timeout=300, json=corpo)
    if r.status_code >= 400:
        raise RuntimeError(f"gpt {r.status_code}: {r.text[:300]}")
    d = r.json()["data"][0]
    if d.get("b64_json"):
        return base64.b64decode(d["b64_json"])
    return httpx.get(d["url"], timeout=120).content


def _runware(prompt: str, tamanho: str, base: str, key: str, espera_s: int = 180) -> bytes:
    w, h = TAMANHOS_RUNWARE.get(tamanho, (1024, 1024))
    raiz = re.sub(r"/v1$", "", base)
    r = httpx.post(raiz + "/v1/estudio/gerar", headers=_h(key), timeout=60,
                   json={"efeito": "imagem-livre", "positivePrompt": prompt, "width": w, "height": h})
    if r.status_code == 503:
        raise ImagemIndisponivel("Essa imagem precisa do nosso estúdio alternativo, que está temporariamente indisponível. Tente outro pedido.")
    if r.status_code >= 400:
        raise ImagemIndisponivel("Não consegui gerar essa imagem agora. Tente de novo em alguns minutos.")
    job = r.json()
    fim = time.time() + espera_s
    while job.get("status") == "running" and time.time() < fim:
        time.sleep(3)
        job = httpx.get(raiz + f"/v1/estudio/jobs/{job['id']}", headers=_h(key), timeout=30).json()
    if job.get("status") != "done" or not job.get("url"):
        raise ImagemIndisponivel("Não consegui gerar essa imagem agora. Tente de novo em alguns minutos.")
    return httpx.get(job["url"], timeout=120).content


def imagem(prompt: str, base: str, key: str, tamanho: str = "1024x1024", referencia: bytes | None = None,
           classe: str | None = None, modelo_classif: str = "rt-geral") -> Resultado:
    """Gera a imagem pela regra 5.0. Levanta ImagemIndisponivel com mensagem pronta para o cliente."""
    base = base.rstrip("/")
    classe = classe or classificar(prompt, base, key, modelo_classif)
    if classe == "nsfw":
        return Resultado(_runware(prompt, tamanho, base, key), "runware", classe, "pedido nsfw")
    ultimo = ""
    for _ in range(2):
        try:
            return Resultado(_gpt(prompt, tamanho, base, key, referencia), "gpt", classe)
        except Exception as e:  # noqa: BLE001
            ultimo = str(e)
            if RECUSA.search(ultimo):
                return Resultado(_runware(prompt, tamanho, base, key), "runware", classe, "gpt recusou: " + ultimo[:120])
    raise ImagemIndisponivel("Não consegui gerar essa imagem agora. Tente de novo em alguns minutos.") from RuntimeError(ultimo)


def log_linha(r: Resultado, onde: str) -> str:
    return json.dumps({"onde": onde, "rota": r.rota, "classe": r.classe, "motivo": r.motivo, "bytes": len(r.dados)}, ensure_ascii=False)
