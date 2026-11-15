;(() => {
  const $ = (s) => document.querySelector(s)
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
  const msg = (t, tipo = 'erro') => { const m = $('#msg'); m.textContent = t || ''; m.className = 'msg ' + tipo }
  const toast = (t) => { const e = $('#toast'); e.textContent = t; e.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => (e.hidden = true), 2200) }
  async function api(url, op = {}) {
    const r = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...op })
    if (r.status === 401) { location.href = '/?entrar=1'; throw new Error('entre') }
    let j = {}
    try { j = await r.json() } catch {}
    if (!r.ok) { const e = new Error(typeof j.detail === 'string' ? j.detail : 'Não deu certo. Tente de novo.'); e.status = r.status; throw e }
    return j
  }
  let conta = null, prints = [], aberto = null
  async function carregarConta() {
    conta = await api('/api/conta')
    $('#cota').innerHTML = conta.assinante ? `<b>${conta.restam > 90 ? '∞' : conta.restam}</b> plano${conta.restam === 1 ? '' : 's'} restante${conta.restam === 1 ? '' : 's'}` : 'Sem plano ativo'
    $('#sem-plano').hidden = conta.assinante
  }
  // prints: lê como data URL e reduz para no máximo 1600 px
  function reduzir(arq) {
    return new Promise((ok, no) => {
      const img = new Image(), url = URL.createObjectURL(arq)
      img.onload = () => {
        const k = Math.min(1, 1600 / Math.max(img.width, img.height)), c = document.createElement('canvas')
        c.width = Math.round(img.width * k); c.height = Math.round(img.height * k); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height)
        URL.revokeObjectURL(url); ok(c.toDataURL('image/jpeg', 0.86))
      }
      img.onerror = no; img.src = url
    })
  }
  $('#prints').onchange = async () => {
    const fs = [...$('#prints').files].slice(0, 3)
    prints = await Promise.all(fs.map(reduzir))
    $('#previas').innerHTML = prints.map((p, i) => `<div class="pv"><img src="${p}" alt="Print ${i + 1}"><button type="button" data-tirar="${i}" aria-label="Tirar">×</button></div>`).join('')
  }
  $('#previas').onclick = (e) => { const b = e.target.closest('[data-tirar]'); if (!b) return; prints.splice(+b.dataset.tirar, 1); $('#previas').innerHTML = prints.map((p, i) => `<div class="pv"><img src="${p}" alt=""><button type="button" data-tirar="${i}">×</button></div>`).join('') }
  $('#f-plano').onsubmit = async (e) => {
    e.preventDefault(); const b = $('#b-gerar'); b.disabled = true; msg('')
    try {
      await api('/api/planos', { method: 'POST', body: JSON.stringify({ arroba: $('#arroba').value, nicho: $('#nicho').value, objetivo: $('#objetivo').value, produto: $('#produto').value, cor: $('#cor').value, prints }) })
      msg('Recebido! A IA já está montando o seu plano.', 'ok'); prints = []; $('#previas').innerHTML = ''; $('#prints').value = ''
      listar(); carregarConta()
    } catch (err) { msg(err.message) } finally { b.disabled = false }
  }
  let tm = null
  async function listar() {
    const { planos } = await api('/api/planos')
    const el = $('#planos')
    el.innerHTML = planos.length ? planos.map((p) => {
      const nome = '@' + esc(p.entrada.arroba)
      if (p.estado === 'pronto') { const rx = p.resultado.raio_x || {}; return `<button class="pl pronto" data-abrir="${p.id}"><div class="pl-n">${rx.nota ?? '–'}</div><div><b>${nome}</b><span>${esc(p.entrada.objetivo).slice(0, 90)}</span></div><span class="ver">Abrir plano →</span></button>` }
      if (p.estado === 'erro') return `<div class="pl erro"><div><b>${nome}</b><span>${esc(p.erro)}</span></div></div>`
      return `<div class="pl"><div class="giro"></div><div><b>${nome}</b><span>${esc(p.etapa || (p.posicao ? `Na fila (${p.posicao} na frente)` : 'Na fila'))}</span><div class="barra"><i style="width:${Math.round((p.progresso || 0.03) * 100)}%"></i></div></div></div>`
    }).join('') : '<div class="vazio">Nenhum plano ainda. Preencha acima e clique em Gerar meu plano.</div>'
    clearTimeout(tm)
    if (planos.some((p) => p.estado === 'fila' || p.estado === 'rodando')) tm = setTimeout(listar, 4000)
  }
  const bloco = (titulo, texto) => `<div class="bl"><div class="bl-t"><strong>${esc(titulo)}</strong><button class="copiar" data-copiar="${esc(texto)}">Copiar</button></div><p>${esc(texto).replace(/\n/g, '<br>')}</p></div>`
  const ABAS = [['raio', 'Raio-x'], ['bios', 'Bios'], ['ideias', '30 ideias'], ['roteiros', 'Roteiros'], ['stories', 'Stories'], ['carrosseis', 'Carrosséis'], ['site', 'Site'], ['nicho', 'Nicho']]
  function render(p, aba) {
    const r = p.resultado, rx = r.raio_x || {}, est = r.estrategia || {}
    const corpo = {
      raio: () => `<div class="rx"><div class="rx-n">${rx.nota ?? '–'}</div><p>${esc(rx.resumo)}</p></div>
        <div class="col2"><div class="bl"><strong>Pontos fortes</strong><ul>${(rx.fortes || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div><div class="bl"><strong>Pontos fracos</strong><ul>${(rx.fracos || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div></div>
        <div class="bl dest"><strong>As 3 mudanças que mais trazem resultado</strong><ol>${(rx.prioridades || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ol></div>
        <div class="bl"><strong>Estratégia</strong><p><b>Posicionamento:</b> ${esc(est.posicionamento)}</p><p><b>Pilares:</b> ${esc((est.pilares || []).join(' · '))}</p><p><b>Frequência:</b> ${esc(est.frequencia)}</p><ul>${(est.formatos || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>`,
      bios: () => (r.bios || []).map((b, i) => bloco('Bio ' + (i + 1), b)).join(''),
      ideias: () => `<div class="filtro">${['todas', 'reels', 'stories', 'carrossel', 'post'].map((f, i) => `<button class="${i === 0 ? 'on' : ''}" data-filtro="${f}">${f[0].toUpperCase() + f.slice(1)}</button>`).join('')}</div>
        <div class="ideias">${(r.ideias || []).map((x, i) => `<div class="id" data-f="${esc(x.formato)}"><span class="fmt">${esc(x.formato)}</span><b>“${esc(x.gancho)}”</b><p>${esc(x.ideia)}</p><button class="copiar" data-copiar="${esc(x.gancho + ' ' + x.ideia)}">Copiar</button></div>`).join('')}</div>`,
      roteiros: () => (r.roteiros || []).map((x) => `<div class="bl"><div class="bl-t"><strong>${esc(x.titulo)}</strong><button class="copiar" data-copiar="${esc([x.gancho, ...(x.cenas || []), x.legenda, (x.hashtags || []).join(' ')].join('\n'))}">Copiar</button></div>
        <p><b>Gancho:</b> ${esc(x.gancho)}</p><ol>${(x.cenas || []).map((c) => `<li>${esc(c)}</li>`).join('')}</ol><p><b>Texto na tela:</b> ${esc(x.texto_tela)}</p><p><b>Legenda:</b> ${esc(x.legenda)} <span class="tags">${esc((x.hashtags || []).join(' '))}</span></p></div>`).join(''),
      stories: () => (r.stories_venda || []).map((x) => bloco(x.nome || 'Sequência', (x.sequencia || []).join('\n'))).join(''),
      carrosseis: () => (r.carrosseis_png || []).map((g, i) => `<div class="bl"><div class="bl-t"><strong>${esc((r.carrosseis[i] || {}).titulo || 'Carrossel ' + (i + 1))}</strong><button class="copiar" data-copiar="${esc((r.carrosseis[i] || {}).legenda || '')}">Copiar legenda</button></div>
        <div class="carr">${g.map((u, k) => `<a href="${u}" download="carrossel${i + 1}_${k + 1}.png"><img src="${u}" alt="Lâmina ${k + 1}" loading="lazy"></a>`).join('')}</div><small>Toque em cada lâmina para baixar.</small></div>`).join(''),
      site: () => `<div class="bl"><strong>${esc(r.site.titulo)}</strong><p>${esc(r.site.subtitulo)}</p><ul>${(r.site.beneficios || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>
        <div class="bl dest"><strong>Baixar o site de vendas</strong><p>Cole o link do checkout da Cakto (se já tiver) e baixe o .zip com a página e o passo a passo para publicar grátis no GitHub.</p>
        <div class="linha"><input id="ck" type="url" placeholder="https://pay.cakto.com.br/…"><a class="btn btn-pri" id="b-zip" href="/api/planos/${p.id}/site.zip">Baixar site</a></div>
        <ol class="passo-a-passo"><li>Crie sua conta na <b>Cakto</b> e cadastre o produto; copie o link do checkout.</li><li>Crie uma conta grátis no <b>GitHub</b> e um repositório chamado <code>seu-usuario.github.io</code>.</li><li>Envie o <code>index.html</code> do .zip (Add file → Upload files) e confirme.</li><li>Em Settings → Pages, deixe a branch main. Em 2 minutos o site abre; coloque o endereço na bio.</li></ol></div>`,
      nicho: () => (r.referencias || []).map((x) => `<div class="bl"><strong>${esc(x.perfil)}</strong><p>${esc(x.o_que_fazem)}</p><p><b>Copiar:</b> ${esc(x.copiar)}</p><p><b>Evitar:</b> ${esc(x.evitar)}</p></div>`).join('') + '<small>Referências sugeridas pela IA a partir do nicho: confira os perfis antes de se basear neles.</small>',
    }[aba]()
    $('#folha-corpo').innerHTML = `<div class="pl-cab"><b>@${esc(p.entrada.arroba)}</b><span>${esc(p.entrada.objetivo)}</span></div>
      <div class="abas-p" role="tablist">${ABAS.map(([k, n]) => `<button class="${k === aba ? 'on' : ''}" data-aba="${k}" role="tab">${n}</button>`).join('')}</div><div class="conteudo">${corpo}</div>`
    const ck = $('#ck')
    if (ck) ck.oninput = () => { $('#b-zip').href = `/api/planos/${p.id}/site.zip` + (ck.value ? '?checkout=' + encodeURIComponent(ck.value.trim()) : '') }
  }
  document.addEventListener('click', async (e) => {
    const cp = e.target.closest('[data-copiar]')
    if (cp) { try { await navigator.clipboard.writeText(cp.dataset.copiar); toast('Copiado!') } catch {} return }
    const ab = e.target.closest('[data-abrir]')
    if (ab) { aberto = await api('/api/planos/' + ab.dataset.abrir); $('#folha').hidden = false; render(aberto, 'raio'); return }
    const t = e.target.closest('[data-aba]')
    if (t && aberto) { render(aberto, t.dataset.aba); $('.folha-c').scrollTop = 0; return }
    const f = e.target.closest('[data-filtro]')
    if (f) { document.querySelectorAll('[data-filtro]').forEach((b) => b.classList.toggle('on', b === f)); document.querySelectorAll('.id').forEach((x) => (x.hidden = f.dataset.filtro !== 'todas' && x.dataset.f !== f.dataset.filtro)); return }
    if (e.target.closest('[data-fechar]') || e.target.id === 'folha') $('#folha').hidden = true
  })
  addEventListener('keydown', (e) => { if (e.key === 'Escape') $('#folha').hidden = true })
  $('#sair').onclick = async () => { await fetch('/api/sair', { method: 'POST' }); location.href = '/' }
  carregarConta().then(listar).catch(() => {})
})()
