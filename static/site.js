;(() => {
  const $ = (s) => document.querySelector(s)
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])

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
