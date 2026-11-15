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
    $('#cota').innerHTML = conta.assinante ? (conta.limite_contas > 90 ? 'Demonstração' : `<b>${conta.contas_semana}/${conta.limite_contas}</b> contas · <b>${conta.posts_semana}/${conta.limite_posts}</b> posts na semana`) : 'Sem plano ativo'
    $('#sem-plano').hidden = conta.assinante
    if (conta.cortai) { $('#b-cortai').href = conta.cortai; $('#b-cortai').hidden = false }
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
      await api('/api/planos', { method: 'POST', body: JSON.stringify({ arroba: $('#arroba').value, nicho: $('#nicho').value, objetivo: $('#objetivo').value, produto: $('#produto').value, cor: $('#cor').value, prints, curriculo_texto: ($('#curriculo') || {}).value || '' }) })
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
  const MK = window.MARCA || { rede: 'instagram', rotulo_bio: 'Bio' }
  const ABAS = MK.rede === 'linkedin'
    ? [['raio', 'Raio-x'], ['bios', 'Títulos'], ['lkd', 'Perfil completo'], ['ideias', '30 ideias'], ['posts', 'Posts da semana'], ['renda', 'Renda extra']]
    : [['raio', 'Raio-x'], ['bios', MK.rotulo_bio + 's'], ['ideias', '30 ideias'], ['posts', 'Posts da semana'], ['roteiros', 'Roteiros'], ['stories', 'Stories'], ['carrosseis', 'Carrosséis'], ['site', 'Site'], ['nicho', 'Nicho'], ['renda', 'Renda extra']]
  function render(p, aba) {
    const r = p.resultado, rx = r.raio_x || {}, est = r.estrategia || {}
    const corpo = {
      raio: () => `<div class="rx"><div class="rx-n">${rx.nota ?? '–'}</div><p>${esc(rx.resumo)}</p></div>
        <div class="col2"><div class="bl"><strong>Pontos fortes</strong><ul>${(rx.fortes || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div><div class="bl"><strong>Pontos fracos</strong><ul>${(rx.fracos || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div></div>
        <div class="bl dest"><strong>As 3 mudanças que mais trazem resultado</strong><ol>${(rx.prioridades || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ol></div>
        <div class="bl"><strong>Estratégia</strong><p><b>Posicionamento:</b> ${esc(est.posicionamento)}</p><p><b>Pilares:</b> ${esc((est.pilares || []).join(' · '))}</p><p><b>Frequência:</b> ${esc(est.frequencia)}</p><ul>${(est.formatos || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>`,
      bios: () => (r.bios || []).map((b, i) => bloco((MK.rede === 'linkedin' ? 'Título ' : MK.rotulo_bio + ' ') + (i + 1), b)).join(''),
      lkd: () => { const L = r.linkedin || {}; return (L.sobre || []).length || (L.experiencias || []).length ? `
        ${(L.sobre || []).map((x, i) => bloco(['Sobre para vaga', 'Sobre para clientes', 'Sobre para autoridade'][i] || 'Sobre ' + (i + 1), x)).join('')}
        ${(L.experiencias || []).map((x) => bloco(`${x.cargo} · ${x.empresa}${x.periodo ? ' · ' + x.periodo : ''}${x.origem === 'curriculo' ? ' (do currículo)' : ''}`, x.descricao)).join('')}
        ${(L.competencias || []).length ? bloco('Competências (nesta ordem)', L.competencias.join(', ')) : ''}
        ${(L.palavras_chave || []).length ? bloco('Palavras que recrutadores buscam', L.palavras_chave.join(', ')) : ''}
        ${(L.faltando_no_linkedin || []).length ? `<div class="bl dest"><strong>Está no currículo e falta no LinkedIn</strong><ul>${L.faltando_no_linkedin.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
        <div class="bl"><strong>Onde colar cada parte (modo guiado)</strong><ol>
          <li>Título: <a href="https://www.linkedin.com/in/me/edit/intro/" target="_blank" rel="noopener">editar a introdução</a></li>
          <li>Sobre: <a href="https://www.linkedin.com/in/me/add-edit/SUMMARY/" target="_blank" rel="noopener">editar o Sobre</a></li>
          <li>Experiências: <a href="https://www.linkedin.com/in/me/details/experience/" target="_blank" rel="noopener">lista de experiências</a> (ou <a href="https://www.linkedin.com/in/me/add-edit/POSITION/" target="_blank" rel="noopener">adicionar cargo</a>)</li>
          <li>Competências: <a href="https://www.linkedin.com/in/me/details/skills/" target="_blank" rel="noopener">competências</a></li></ol></div>` : '<div class="vazio">Gere um plano novo com o seu currículo para ver o perfil completo.</div>' },
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
      posts: () => `<div class="bl dest"><strong>Post do dia</strong><p>Um post pronto por dia (7 por semana), com imagem, gancho e o seu @, a partir das ideias deste plano. Baixe e poste, ou leve para o agendador.</p>
        <button class="btn btn-pri" id="b-post" data-plano="${p.id}">Gerar o post de hoje</button><div class="msg" id="post-msg"></div></div><div class="posts-g" id="posts-g"><div class="vazio">Carregando…</div></div>`,
      renda: () => { const x = r.renda_extra || {}; return x.servico ? `<div class="bl dest"><strong>${esc(x.servico)}</strong><p><b>Para quem:</b> ${esc(x.para_quem)}</p><p><b>Preço sugerido:</b> ${esc(x.preco_sugerido)}</p></div>
        <div class="bl"><strong>O que entregar</strong><ul>${(x.entregaveis || []).map((y) => `<li>${esc(y)}</li>`).join('')}</ul></div>
        ${(x.abordagem || []).map((y, i) => bloco('Mensagem de abordagem ' + (i + 1), y)).join('')}
        ${x.proposta ? bloco('Proposta comercial', x.proposta) : ''}
        <div class="bl"><strong>Cuidados</strong><ul>${(x.cuidados || []).map((y) => `<li>${esc(y)}</li>`).join('')}</ul></div><small>Faça para outras pessoas o que este plano fez por você. Sem promessa de seguidores ou vendas.</small>` : '<div class="vazio">Este plano foi feito antes do plano de renda extra existir. Gere um plano novo para ver.</div>' },
      nicho: () => (r.referencias || []).map((x) => `<div class="bl"><strong>${esc(x.perfil)}</strong><p>${esc(x.o_que_fazem)}</p><p><b>Copiar:</b> ${esc(x.copiar)}</p><p><b>Evitar:</b> ${esc(x.evitar)}</p></div>`).join('') + '<small>Referências sugeridas pela IA a partir do nicho: confira os perfis antes de se basear neles.</small>',
    }[aba]()
    $('#folha-corpo').innerHTML = `<div class="pl-cab"><b>@${esc(p.entrada.arroba)}</b><span>${esc(p.entrada.objetivo)}</span></div>
      <div class="abas-p" role="tablist">${ABAS.map(([k, n]) => `<button class="${k === aba ? 'on' : ''}" data-aba="${k}" role="tab">${n}</button>`).join('')}</div><div class="conteudo">${corpo}</div>`
    if (aba === 'posts') carregarPosts()
    const ck = $('#ck')
    if (ck) ck.oninput = () => { $('#b-zip').href = `/api/planos/${p.id}/site.zip` + (ck.value ? '?checkout=' + encodeURIComponent(ck.value.trim()) : '') }
  }
  async function carregarPosts() {
    try {
      const j = await api('/api/posts')
      const g = $('#posts-g'); if (!g) return
      g.innerHTML = j.posts.length ? j.posts.map((x) => `<div class="post-i"><a href="${x.url}" download="post-${esc(x.dia)}.png"><img src="${x.url}" alt="Post de ${esc(x.dia)}" loading="lazy"></a>
        <div><small>${esc(x.dia.split('-').reverse().join('/'))} · @${esc(x.arroba)}</small><p>${esc(x.legenda)}</p><button class="copiar" data-copiar="${esc(x.legenda)}">Copiar legenda</button></div></div>`).join('') : '<div class="vazio">Nenhum post ainda. Gere o de hoje.</div>'
    } catch {}
  }
  document.addEventListener('click', async (e) => {
    const bp = e.target.closest('#b-post')
    if (bp) {
      bp.disabled = true; bp.textContent = 'Criando a imagem… (até 3 minutos)'
      const m = $('#post-msg')
      try { await api('/api/planos/' + bp.dataset.plano + '/post', { method: 'POST' }); m.textContent = 'Post de hoje pronto.'; m.className = 'msg ok'; carregarPosts(); carregarConta() }
      catch (err) { m.textContent = err.message; m.className = 'msg erro' } finally { bp.disabled = false; bp.textContent = 'Gerar o post de hoje' }
      return
    }
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

// Kit de marca nas fotos e vídeos do cliente (spec 44 5.2)
;(() => {
  const $ = (q) => document.querySelector(q)
  const inp = $('#kit-arq'); if (!inp) return
  const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
  async function listar() {
    try {
      const j = await (await fetch('/api/kit')).json()
      $('#kit-lista').innerHTML = (j.itens || []).map((x) => x.tipo === 'video' ? `<video src="${x.url}" controls playsinline preload="none"></video>` : `<a href="${x.url}" download><img src="${x.url}" alt="Foto com a marca" loading="lazy"></a>`).join('')
    } catch {}
  }
  inp.onchange = () => {
    const f = inp.files[0]; if (!f) return
    const ar = ($('#kit-arroba').value || $('#arroba').value || '').trim()
    const m = $('#kit-msg')
    if (!ar) { m.textContent = 'Digite o @ que vai aparecer.'; m.className = 'msg erro'; return }
    const x = new XMLHttpRequest(); x.open('POST', '/api/kit')
    x.setRequestHeader('x-arquivo', f.name); x.setRequestHeader('x-arroba', ar); x.setRequestHeader('x-cor', $('#kit-cor').value)
    m.textContent = 'Aplicando a sua marca…'; m.className = 'msg'
    x.onload = () => { let j = {}; try { j = JSON.parse(x.responseText) } catch {}
      if (x.status >= 400) { m.textContent = typeof j.detail === 'string' ? j.detail : 'Não deu certo.'; m.className = 'msg erro' } else { m.textContent = 'Pronto! Toque para baixar.'; m.className = 'msg ok'; listar() }
      inp.value = '' }
    x.send(f)
  }
  listar()
})()

// Linkdn AI: currículo por arquivo, texto ou áudio
;(() => {
  const M = window.MARCA || {}
  const box = document.getElementById('bloco-cv'); if (!box || M.rede !== 'linkedin') return
  box.hidden = false
  const info = document.getElementById('cv-info'), ta = document.getElementById('curriculo')
  async function enviar(blob, nome) {
    info.textContent = 'Lendo…'
    const r = await fetch('/api/curriculo', { method: 'POST', headers: { 'x-arquivo': nome }, body: blob })
    let j = {}; try { j = await r.json() } catch {}
    if (!r.ok) { info.textContent = typeof j.detail === 'string' ? j.detail : 'Não deu certo.'; return }
    ta.value = (ta.value ? ta.value + '\n\n' : '') + j.texto; info.textContent = 'Pronto: confira e corrija o texto antes de gerar.'
  }
  document.getElementById('arq-cv').onchange = (e) => { const f = e.target.files[0]; if (f) enviar(f, f.name) }
  let rec = null, partes = []
  document.getElementById('b-gravar').onclick = async (e) => {
    const b = e.currentTarget
    if (rec) { rec.stop(); return }
    try {
      const st = await navigator.mediaDevices.getUserMedia({ audio: true })
      rec = new MediaRecorder(st); partes = []
      rec.ondataavailable = (ev) => partes.push(ev.data)
      rec.onstop = () => { st.getTracks().forEach((t) => t.stop()); b.textContent = 'Gravar áudio'; const blob = new Blob(partes, { type: rec.mimeType }); rec = null; enviar(blob, 'fala.webm') }
      rec.start(); b.textContent = 'Parar e transcrever'; info.textContent = 'Gravando… conte cargos, empresas, datas e resultados (até 10 min).'
      setTimeout(() => rec && rec.state === 'recording' && rec.stop(), 600000)
    } catch { info.textContent = 'Não consegui usar o microfone.' }
  }
})()

// Imagens do perfil: foto, capa, ícones (spec 44 3.3.4)
;(() => {
  const $ = (q) => document.querySelector(q)
  const M = window.MARCA || { rede: 'instagram' }
  if (!$('#imagens')) return
  $('#card-capa').hidden = !(M.rede === 'linkedin' || M.rede === 'facebook')
  $('#card-icones').hidden = M.rede !== 'instagram'
  if (M.cor) $('#img-cor').value = M.cor
  const msg = (t, tipo = '') => { const m = $('#img-msg'); m.textContent = t; m.className = 'msg ' + tipo }
  async function listar() {
    try {
      const j = await (await fetch('/api/imagens')).json()
      $('#img-lista').innerHTML = (j.itens || []).flatMap((x) => x.urls.map((u) => `<a href="${u}" download><img src="${u}" alt="${x.tipo}" loading="lazy"></a>`)).join('')
    } catch {}
  }
  async function chamar(url, op, btn) {
    const txt = btn ? btn.textContent : ''
    if (btn) { btn.disabled = true; btn.textContent = 'Criando… (até 3 minutos)' }
    msg('A IA está criando a imagem…')
    try {
      const r = await fetch(url, op); let j = {}; try { j = await r.json() } catch {}
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Não deu certo.')
      msg('Pronto! Toque na imagem para baixar.', 'ok'); listar()
    } catch (e) { msg(e.message, 'erro') } finally { if (btn) { btn.disabled = false; btn.textContent = txt } }
  }
  $('#foto-arq').onchange = (e) => { const f = e.target.files[0]; if (!f) return; chamar('/api/imagens/foto', { method: 'POST', headers: { 'x-cor': $('#img-cor').value }, body: f }); e.target.value = '' }
  $('#b-capa').onclick = (e) => chamar('/api/imagens/capa', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ frase: $('#capa-frase').value, cor: $('#img-cor').value, nicho: ($('#nicho') || {}).value || '' }) }, e.currentTarget)
  $('#b-icones').onclick = (e) => chamar('/api/imagens/icones', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ temas: $('#icones-temas').value.split(','), cor: $('#img-cor').value }) }, e.currentTarget)
  listar()
})()
