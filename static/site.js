;(() => {
  const $ = (s) => document.querySelector(s)
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
  const modal = $('#m-entrar')
  let email = ''
  const msg = (t, tipo = 'erro') => { const m = $('#m-msg'); m.textContent = t || ''; m.className = 'msg ' + tipo }
  const passo = (q) => { ['#passo-email', '#passo-codigo', '#passo-senha'].forEach((p) => ($(p).hidden = p !== q)); msg('') }
  async function abrir() {
    try { const r = await fetch('/api/conta'); if (r.ok) return (location.href = '/app') } catch {}
    modal.hidden = false; passo('#passo-email'); setTimeout(() => $('#email').focus(), 50)
  }
  document.addEventListener('click', (e) => { if (e.target.closest('[data-entrar]')) abrir() })
  modal.addEventListener('click', (e) => { if (e.target === modal || e.target.closest('[data-fechar]')) modal.hidden = true })
  addEventListener('keydown', (e) => { if (e.key === 'Escape') modal.hidden = true })
  const post = async (url, corpo) => {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) })
    let j = {}
    try { j = await r.json() } catch {}
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Não deu certo. Tente de novo.')
    return j
  }
  $('#f-email').onsubmit = async (e) => {
    e.preventDefault(); const b = e.submitter; b.disabled = true; msg('')
    try {
      email = $('#email').value.trim()
      const j = await post('/api/entrar/codigo', { email })
      passo('#passo-codigo'); $('#cod-txt').textContent = `Mandamos 6 números para ${email}. Confira também o spam.`
      if (j.codigo_dev) $('#codigo').value = j.codigo_dev
      setTimeout(() => $('#codigo').focus(), 50)
    } catch (err) { msg(err.message) } finally { b.disabled = false }
  }
  $('#f-cod').onsubmit = async (e) => {
    e.preventDefault(); const b = e.submitter; b.disabled = true
    try { await post('/api/entrar', { email, codigo: $('#codigo').value }); msg('Tudo certo! Abrindo…', 'ok'); location.href = '/app' } catch (err) { msg(err.message) } finally { b.disabled = false }
  }
  $('#f-senha').onsubmit = async (e) => {
    e.preventDefault(); const b = e.submitter; b.disabled = true
    try { await post('/api/entrar/senha', { email: $('#d-email').value.trim(), senha: $('#d-senha').value }); location.href = '/app' } catch (err) { msg(err.message) } finally { b.disabled = false }
  }
  $('#link-senha').onclick = () => passo('#passo-senha')
  $('#voltar-email').onclick = () => passo('#passo-email')
  $('#voltar-email2').onclick = () => passo('#passo-email')
  if (new URLSearchParams(location.search).has('entrar')) abrir()

  const brl2 = (v) => 'R$ ' + Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  fetch('/api/planos-venda').then((r) => r.json()).then((j) => {
    const d = j.planos[0]?.lancamento_ate
    if (d) { const [, m, di] = d.split('-'); $('#lanc-data').textContent = `${di}/${m}` }
    $('#planos').innerHTML = j.planos.map((p, i) => `<div class="plano ${i === 1 ? 'destaque' : ''}">${i === 1 ? '<span class="selo">Mais escolhido</span>' : ''}
      <b class="pn">${esc(p.nome)}</b><div class="pv">${brl2(p.preco)}<small>/mês</small></div><div class="pv-de">Depois do lançamento: ${brl2(p.depois)}/mês</div>
      <ul class="lista">${p.itens.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
      ${p.checkout ? `<a class="btn ${i === 1 ? 'btn-pri' : 'btn-sec'} grande" href="${esc(p.checkout)}" target="_blank" rel="noopener">Assinar o ${esc(p.nome)}</a>` : `<button class="btn btn-sec grande" data-entrar>Quero o ${esc(p.nome)}</button>`}
      <span class="pl-nota">Use o mesmo e-mail para entrar depois</span></div>`).join('')
  }).catch(() => {})
})()
