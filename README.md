# Perfilaí

Plano de Instagram com IA. A pessoa manda o @, o objetivo e prints do perfil; recebe raio-x, 3 bios, 30 ideias com gancho, 5 roteiros de Reels, stories de venda, 3 carrosséis em PNG e um site de vendas estático (.zip com passo a passo para GitHub Pages + Cakto).

- **Diretor:** `rt-planejar` (GPT) lê a leitura dos prints e decide estratégia, pauta e briefing.
- **Mão de obra:** `rt-geral` (Qwen) escreve bios, roteiros, stories, carrosséis e a página, seguindo o briefing.
- **Visão:** `visao` lê os prints do perfil. Não pedimos senha e não raspamos o Instagram (a leitura anônima é bloqueada).

Stack: FastAPI + SQLite (`/data`), front estático em `static/`, Pillow para os carrosséis. Login por código no e-mail; a conta de demonstração entra com senha. Assinatura pela Cakto (3 planos) com webhook em `/api/cakto`. Admin em `/api/admin/*` (cabeçalho `x-admin-key`).

```
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -q
```

Release: workflow `release.yml` (imagem + manifesto). Deploy: somente pelo `vps_rt_infra` (`deploy.yml service=perfilai`). Spec: `new_ragente/specs/43_INSTAGRAM_IA.md`.
