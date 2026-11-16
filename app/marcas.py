"""As 4 marcas da suíte de perfil (spec 44, parte 3): um código, a marca vem do domínio. Trocar nome = editar aqui + DNS + Cakto."""
from __future__ import annotations

MARCAS = {
    "insta": {
        "id": "insta", "nome": "Perfil AI Insta", "rede": "instagram", "rede_nome": "Instagram", "cor": "#d946ef", "cor2": "#f97316",
        "hosts": ["insta-ai.rangeltech.net", "perfilai.rangeltech.net"], "url": "https://insta-ai.rangeltech.net",
        "campo_perfil": "@ do perfil", "exemplo_perfil": "@seuperfil",
        "titulo_pagina": "Perfil AI Insta: seu Instagram com cara de perfil que vende",
        "promessa": "Bio que vende, nome com palavra-chave, 7 posts prontos por semana, kit de marca nas suas fotos e um plano de conteúdo completo. Em minutos.",
        "regras": "Bio do Instagram: até 150 caracteres, com chamada no fim e no máximo 3 emojis. Nome: até 30 caracteres, com palavra-chave do nicho.",
        "lim_bio": 150, "rotulo_bio": "Bio",
    },
    "face": {
        "id": "face", "nome": "Perfil AI Face", "rede": "facebook", "rede_nome": "Facebook", "cor": "#2563eb", "cor2": "#06b6d4",
        "hosts": ["face-ai.rangeltech.net"], "url": "https://face-ai.rangeltech.net",
        "campo_perfil": "Link ou nome do perfil/página", "exemplo_perfil": "facebook.com/suapagina",
        "titulo_pagina": "Perfil AI Face: seu Facebook profissional, pronto para vender",
        "promessa": "Apresentação que gera confiança, nome certo, 7 posts prontos por semana e um plano de conteúdo para a sua página.",
        "regras": "Apresentação (bio) do Facebook: até 101 caracteres, direta e com o que a pessoa faz. Capa: 1640x624.",
        "lim_bio": 101, "rotulo_bio": "Apresentação",
    },
    "tiktok": {
        "id": "tiktok", "nome": "Perfil AI TikTok", "rede": "tiktok", "rede_nome": "TikTok", "cor": "#ec4899", "cor2": "#22d3ee",
        "hosts": ["tittok-ai.rangeltech.net"], "url": "https://tittok-ai.rangeltech.net",
        "campo_perfil": "@ do perfil", "exemplo_perfil": "@seuperfil",
        "titulo_pagina": "Perfil AI TikTok: um perfil que segura quem chega pelo For You",
        "promessa": "Descrição de 80 caracteres que converte, nome com palavra-chave, roteiros e as ideias de vídeo que o seu nicho mais assiste.",
        "regras": "Descrição do TikTok: até 80 caracteres. Nome: até 30 caracteres e só troca a cada 7 dias. Link na bio só para conta comercial ou com muitos seguidores.",
        "lim_bio": 80, "rotulo_bio": "Descrição",
    },
    "linkedin": {
        "id": "linkedin", "nome": "Perfil AI LinkedIn", "rede": "linkedin", "rede_nome": "LinkedIn", "cor": "#0e7490", "cor2": "#334155",
        "hosts": ["linkdn-ai.rangeltech.net"], "url": "https://linkdn-ai.rangeltech.net",
        "campo_perfil": "Link do seu LinkedIn", "exemplo_perfil": "linkedin.com/in/seu-nome",
        "titulo_pagina": "Perfil AI LinkedIn: o perfil que o recrutador encontra",
        "promessa": "Seu currículo vira um LinkedIn completo: título com palavras-chave, Sobre em 3 versões, experiências com resultado e o que falta no seu perfil.",
        "regras": "Título (headline) do LinkedIn: até 220 caracteres, com cargo, especialidade e palavras-chave de busca de recrutador. Sobre: até 2.600 caracteres. "
                  "Nunca invente cargo, empresa, data ou formação: só reescreva o que existe ou o que veio do currículo.",
        "lim_bio": 220, "rotulo_bio": "Título",
    },
}


def por_host(host: str | None) -> dict:
    h = (host or "").split(":")[0].lower()
    for m in MARCAS.values():
        if h in m["hosts"]:
            return m
    return MARCAS["insta"]


def publica(m: dict) -> dict:
    return {k: m[k] for k in ("id", "nome", "rede", "rede_nome", "cor", "cor2", "url", "campo_perfil", "exemplo_perfil", "titulo_pagina", "promessa", "rotulo_bio", "lim_bio")}
