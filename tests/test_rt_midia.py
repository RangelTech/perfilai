"""Regra de imagem 5.0: GPT padrão, Runware quando o GPT recusa ou o pedido é nsfw, erro amigável sem estúdio."""
import base64

import pytest

from app import rt_midia

PNG = b"\x89PNG\r\n\x1a\nfake"


class Resp:
    def __init__(self, status=200, js=None, content=b"", text=""):
        self.status_code, self._js, self.content, self.text = status, js, content, text or str(js)

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


@pytest.fixture()
def rede(monkeypatch):
    chamadas = []
    estado = {"gpt": "ok", "estudio": "ok", "classe": "ok"}

    def post(url, **kw):
        chamadas.append(url)
        if url.endswith("/chat/completions"):
            return Resp(js={"choices": [{"message": {"content": estado["classe"]}}]})
        if url.endswith("/images/generations") or url.endswith("/images/edits"):
            if estado["gpt"] == "recusa":
                return Resp(400, js={"error": {"code": "content_policy_violation"}}, text='{"error":{"code":"content_policy_violation"}}')
            if estado["gpt"] == "falha":
                return Resp(500, js={}, text="boom")
            return Resp(js={"data": [{"b64_json": base64.b64encode(PNG).decode()}]})
        if url.endswith("/v1/estudio/gerar"):
            if estado["estudio"] == "off":
                return Resp(503, js={})
            return Resp(js={"id": "j1", "status": "done", "url": "https://cdn/x.png"})
        raise AssertionError(url)

    def get(url, **kw):
        chamadas.append(url)
        return Resp(content=PNG)

    monkeypatch.setattr(rt_midia.httpx, "post", post)
    monkeypatch.setattr(rt_midia.httpx, "get", get)
    return chamadas, estado


def test_normal_vai_pelo_gpt(rede):
    ch, _ = rede
    r = rt_midia.imagem("um gato astronauta", "https://q/v1", "k")
    assert r.rota == "gpt" and r.dados == PNG and not any("estudio" in c for c in ch)


def test_recusa_do_gpt_cai_no_runware(rede):
    ch, est = rede
    est["gpt"] = "recusa"
    r = rt_midia.imagem("cena forte", "https://q/v1", "k")
    assert r.rota == "runware" and "recusou" in r.motivo and any(c.endswith("/v1/estudio/gerar") for c in ch)


def test_nsfw_vai_direto_ao_runware(rede):
    ch, est = rede
    est["classe"] = "nsfw"
    r = rt_midia.imagem("pedido adulto qualquer", "https://q/v1", "k")
    assert r.rota == "runware" and r.classe == "nsfw" and not any("/images/" in c for c in ch)


def test_palavra_explicita_nem_consulta_o_classificador(rede):
    ch, _ = rede
    r = rt_midia.imagem("mulher nua na praia", "https://q/v1", "k")
    assert r.rota == "runware" and not any(c.endswith("/chat/completions") for c in ch)


def test_estudio_desligado_da_erro_amigavel(rede):
    _, est = rede
    est["gpt"], est["estudio"] = "recusa", "off"
    with pytest.raises(rt_midia.ImagemIndisponivel) as e:
        rt_midia.imagem("cena forte", "https://q/v1", "k")
    assert "indisponível" in str(e.value)


def test_falha_tecnica_do_gpt_nao_vai_ao_runware(rede):
    ch, est = rede
    est["gpt"] = "falha"
    with pytest.raises(rt_midia.ImagemIndisponivel):
        rt_midia.imagem("um gato", "https://q/v1", "k")
    assert not any("estudio" in c for c in ch)
