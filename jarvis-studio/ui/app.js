/* JARVIS Studio: tela. Todo o áudio fica no Python; aqui só desenha e manda comandos. */
'use strict'

const ALT = 112                     // altura da faixa em px (igual a --altura-faixa)
const $ = (id) => document.getElementById(id)

const S = {
  resumo: null,
  faixas: [],
  sel: null,                        // id da faixa selecionada
  zoom: 50,                         // px por segundo
  scroll: 0,                        // segundos na borda esquerda
  picos: {},                        // id -> {versao, passo, picos}
  est: null,
  sujo: true,
  catalogo: null,
  arrasto: null,
  reguaSel: null,
  medidores: {},
  estavaGravando: false,
}

// ------------------------------------------------------------------ chamadas
async function chamar(nome, ...args) {
  try {
    const r = await window.pywebview.api[nome](...args)
    if (r && r.erro) { aviso(r.erro, true); return null }
    return r
  } catch (e) {
    aviso(String(e), true)
    return null
  }
}

let tAviso = null
function aviso(msg, erro = false) {
  const el = $('aviso')
  el.textContent = msg
  el.classList.toggle('erro', erro)
  el.classList.remove('oculto')
  clearTimeout(tAviso)
  tAviso = setTimeout(() => el.classList.add('oculto'), erro ? 6000 : 3000)
}

// ------------------------------------------------------------------ utilitários
const sr = () => (S.resumo ? S.resumo.sr : 48000)
const amostraParaX = (a) => (a / sr() - S.scroll) * S.zoom
const xParaAmostra = (x) => Math.round((S.scroll + x / S.zoom) * sr())
const batidaAmostras = () => (60 / S.resumo.bpm) * sr()

function tempo(amostras) {
  const neg = amostras < 0
  const s = Math.abs(amostras) / sr()
  const m = Math.floor(s / 60)
  const r = (s - m * 60).toFixed(3).padStart(6, '0')
  return `${neg ? '-' : ''}${String(m).padStart(2, '0')}:${r}`
}

function compassoAtual(amostras) {
  const b = Math.floor(amostras / batidaAmostras())
  const c = S.resumo.compasso
  const comp = Math.floor(b / c)
  return `${comp + 1}.${((b % c) + c) % c + 1}`
}

function nivelPct(v) {
  if (!v || v <= 0) return 0
  return Math.max(0, Math.min(1, (20 * Math.log10(v) + 60) / 60)) * 100
}

function snap(a) {
  if (!$('b-grade').classList.contains('ligado')) return a
  const b = batidaAmostras()
  return Math.round(a / b) * b
}

const faixaSel = () => S.faixas.find((f) => f.id === S.sel)

// ------------------------------------------------------------------ atualizar tudo
async function atualizar() {
  const r = await chamar('resumo')
  if (!r) return
  S.resumo = r
  S.faixas = r.faixas
  if (!S.faixas.find((f) => f.id === S.sel)) S.sel = S.faixas[0]?.id ?? null
  for (const f of S.faixas) {
    if (f.duracao > 0 && S.picos[f.id]?.versao !== f.versao) {
      const p = await chamar('picos', f.id)
      if (p) S.picos[f.id] = p
    }
  }
  $('i-bpm').value = r.bpm
  $('i-compasso').value = r.compasso
  $('i-master').value = r.master_db
  $('b-metro').classList.toggle('ligado', r.metronomo)
  $('b-contagem').classList.toggle('ligado', r.contagem)
  $('b-loop').classList.toggle('ligado', r.loop)
  document.title = r.projeto ? `J.A.R.V.I.S STUDIO · ${r.projeto.split(/[\\/]/).pop()}` : 'J.A.R.V.I.S STUDIO'
  renderCabecalhos()
  renderFx()
  S.sujo = true
}

function trocarFaixa(info) {
  if (!info || !info.id) return
  const i = S.faixas.findIndex((f) => f.id === info.id)
  if (i >= 0) S.faixas[i] = info
}

// ------------------------------------------------------------------ cabeçalhos das faixas
const ICONE_FONE = '<svg viewBox="0 0 24 24"><path d="M12 3a9 9 0 0 0-9 9v7a2 2 0 0 0 2 2h2v-8H5v-1a7 7 0 0 1 14 0v1h-2v8h2a2 2 0 0 0 2-2v-7a9 9 0 0 0-9-9z"/></svg>'
const ICONE_REC = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"/></svg>'

function opcoesEntrada(n, atual) {
  const ops = []
  for (let i = 0; i < Math.max(n, 1); i++) ops.push([String(i), `Entrada ${i + 1}`])
  for (let i = 0; i + 1 < n; i += 2) ops.push([`${i},${i + 1}`, `Entradas ${i + 1}+${i + 2}`])
  const v = atual.join(',')
  return ops.map(([k, t]) => `<option value="${k}" ${k === v ? 'selected' : ''}>${t}</option>`).join('')
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
}

function renderCabecalhos() {
  const box = $('cabecalhos')
  const n = S.resumo?.n_entradas ?? 0
  box.innerHTML = S.faixas.map((f) => `
    <div class="cab ${f.id === S.sel ? 'selecionada' : ''}" data-id="${f.id}" style="--cor:${f.cor}">
      <div class="linha">
        <input class="nome" value="${esc(f.nome)}" spellcheck="false" data-campo="nome">
        <button class="btn tog seta" data-acao="cima" title="Subir">▲</button>
        <button class="btn tog seta" data-acao="baixo" title="Descer">▼</button>
        <button class="btn tog perigo" data-acao="apagar" title="Apagar faixa">✕</button>
      </div>
      <div class="linha">
        <button class="btn tog arm ${f.armada ? 'ligado' : ''}" data-acao="armada" title="Armar para gravar">${ICONE_REC}</button>
        <button class="btn tog ${f.monitor ? 'ligado' : ''}" data-acao="monitor" title="Ouvir a entrada (monitorar)">${ICONE_FONE}</button>
        <button class="btn tog mudo ${f.mudo ? 'ligado' : ''}" data-acao="mudo" title="Mudo">M</button>
        <button class="btn tog solo ${f.solo ? 'ligado' : ''}" data-acao="solo" title="Solo">S</button>
        <button class="btn tog fx ${f.efeitos.length ? 'tem' : ''}" data-acao="fx" title="Efeitos da faixa">FX ${f.efeitos.length || ''}</button>
        <select data-campo="entrada" title="Entrada da placa">${opcoesEntrada(n, f.entrada)}</select>
      </div>
      <div class="linha">
        <span class="rotulo" data-vol>${f.volume_db.toFixed(1)}</span>
        <input type="range" min="-60" max="12" step="0.5" value="${f.volume_db}" data-campo="volume_db" title="Volume (duplo clique zera)">
        <input type="range" class="pan" min="-1" max="1" step="0.05" value="${f.pan}" data-campo="pan" title="Pan (duplo clique centraliza)">
      </div>
      <div class="linha"><div class="medidor"><i data-medidor></i></div></div>
    </div>`).join('')
  if (!S.faixas.length) box.innerHTML = ''
  ajustarTamanho()
}

$('cabecalhos').addEventListener('mousedown', (e) => {
  const cab = e.target.closest('.cab')
  if (cab && cab.dataset.id !== S.sel) selecionar(cab.dataset.id)
})

$('cabecalhos').addEventListener('click', async (e) => {
  const b = e.target.closest('[data-acao]')
  if (!b) return
  const id = b.closest('.cab').dataset.id
  const f = S.faixas.find((x) => x.id === id)
  const acao = b.dataset.acao
  if (['armada', 'monitor', 'mudo', 'solo'].includes(acao)) {
    const r = await chamar('ajustar_faixa', id, acao, !f[acao])
    if (r) { trocarFaixa(r); b.classList.toggle('ligado', r[acao]) }
  } else if (acao === 'apagar') {
    if (f.duracao > 0 && !confirm(`Apagar a faixa "${f.nome}" e o que foi gravado nela?`)) return
    await chamar('remover_faixa', id)
    await atualizar()
  } else if (acao === 'cima' || acao === 'baixo') {
    await chamar('mover_faixa', id, acao === 'cima' ? -1 : 1)
    await atualizar()
  } else if (acao === 'fx') {
    e.stopPropagation()
    selecionar(id)
    abrirPainelFx()
    if (!f.efeitos.length) abrirMenuFx()
    else piscar($('painel-fx'))
  }
})

$('cabecalhos').addEventListener('input', (e) => {
  const el = e.target
  const campo = el.dataset.campo
  if (!campo || el.type !== 'range') return
  const id = el.closest('.cab').dataset.id
  const v = parseFloat(el.value)
  const f = S.faixas.find((x) => x.id === id)
  f[campo] = v
  if (campo === 'volume_db') el.closest('.cab').querySelector('[data-vol]').textContent = v.toFixed(1)
  chamar('ajustar_faixa', id, campo, v)
})

$('cabecalhos').addEventListener('dblclick', (e) => {
  const el = e.target
  if (el.type !== 'range') return
  el.value = 0
  el.dispatchEvent(new Event('input', { bubbles: true }))
})

$('cabecalhos').addEventListener('change', async (e) => {
  const el = e.target
  const campo = el.dataset.campo
  if (!campo || el.type === 'range') return
  const id = el.closest('.cab').dataset.id
  const valor = campo === 'entrada' ? el.value.split(',').map(Number) : el.value
  const r = await chamar('ajustar_faixa', id, campo, valor)
  if (r) { trocarFaixa(r); S.sujo = true; if (id === S.sel) renderFx() }
})

$('cabecalhos').addEventListener('keydown', (e) => {
  if (e.target.classList.contains('nome') && e.key === 'Enter') e.target.blur()
})

function selecionar(id) {
  S.sel = id
  document.querySelectorAll('.cab').forEach((c) => c.classList.toggle('selecionada', c.dataset.id === id))
  renderFx()
  S.sujo = true
}

// ------------------------------------------------------------------ painel de efeitos
function fmt(v, p) {
  const u = p.unidade
  if (u === 'Hz' && v >= 1000) return `${(v / 1000).toFixed(v >= 10000 ? 1 : 2)}k`
  if (u === 's') return `${(v * 1000).toFixed(0)}ms`
  const casas = p.passo >= 1 ? 0 : p.passo >= 0.1 ? 1 : 2
  return `${v.toFixed(casas)}${u === 'dB' ? 'dB' : u === 'ms' ? 'ms' : u === ':1' ? ':1' : ''}`
}

function renderFx() {
  const f = faixaSel()
  $('fx-faixa').textContent = f ? f.nome : '—'
  $('b-add-fx').disabled = !f
  const box = $('cadeia')
  if (!f) { box.innerHTML = '<div class="dica">Crie uma faixa para colocar efeitos.</div>'; return }
  if (!f.efeitos.length) {
    box.innerHTML = '<div class="dica">Nenhum efeito nesta faixa.<br>Clique em <b>+ Efeito</b> para colocar EQ, compressor, distorção, delay, reverb, um VST3 ou uma cadeia pronta.<br>O som passa pelos efeitos da esquerda para a direita.</div>'
    return
  }
  box.innerHTML = f.efeitos.map((ef) => `
    <div class="efeito ${ef.ativo ? '' : 'desligado'} ${ef.vst ? 'vst' : ''}" data-ef="${ef.id}">
      <div class="ef-topo">
        <button class="btn liga ${ef.ativo ? 'ligado' : ''}" data-acao="alternar" title="Liga/desliga">⏻</button>
        <span class="ef-nome" title="${esc(ef.nome)}">${esc(ef.nome)}</span>
        <button class="btn seta" data-acao="esq" title="Mover para antes">◀</button>
        <button class="btn seta" data-acao="dir" title="Mover para depois">▶</button>
        <button class="btn seta perigo" data-acao="remover" title="Tirar">✕</button>
      </div>
      <div class="ef-params">
        ${ef.vst ? '<button class="btn" data-acao="editor">Abrir janela do plugin</button><div class="dica" style="font-size:12px;color:var(--texto-3)">Os ajustes ficam salvos no projeto.</div>' : ''}
        ${ef.params.map((p) => `
          <label class="param"><span title="${esc(p.rotulo)}">${esc(p.rotulo)}</span>
            <input type="range" min="${p.min}" max="${p.max}" step="${p.passo}" value="${p.valor}" data-param="${p.nome}">
            <b>${fmt(p.valor, p)}</b></label>`).join('')}
      </div>
    </div>`).join('')
}

$('cadeia').addEventListener('click', async (e) => {
  const b = e.target.closest('[data-acao]')
  if (!b) return
  const f = faixaSel()
  const ef = b.closest('[data-ef]').dataset.ef
  const mapa = {
    alternar: () => chamar('alternar_efeito', f.id, ef),
    esq: () => chamar('mover_efeito', f.id, ef, -1),
    dir: () => chamar('mover_efeito', f.id, ef, 1),
    remover: () => chamar('remover_efeito', f.id, ef),
    editor: () => chamar('abrir_editor', f.id, ef),
  }
  const r = await mapa[b.dataset.acao]()
  if (r && r.id) { trocarFaixa(r); renderFx(); renderCabecalhos() }
})

$('cadeia').addEventListener('input', (e) => {
  const el = e.target
  if (!el.dataset.param) return
  const f = faixaSel()
  const efId = el.closest('[data-ef]').dataset.ef
  const ef = f.efeitos.find((x) => x.id === efId)
  const p = ef.params.find((x) => x.nome === el.dataset.param)
  p.valor = parseFloat(el.value)
  el.nextElementSibling.textContent = fmt(p.valor, p)
  chamar('ajustar_efeito', f.id, efId, p.nome, p.valor)
})

function abrirPainelFx() {
  $('painel-fx').classList.remove('fechado')
  $('b-fx-recolher').textContent = 'recolher'
  setTimeout(ajustarTamanho, 0)
}

function piscar(el) {
  el.classList.remove('piscar')
  void el.offsetWidth
  el.classList.add('piscar')
}

async function abrirMenuFx() {
  const f = faixaSel()
  if (!f) { aviso('Crie uma faixa primeiro (+ Faixa).', true); return }
  if (!S.catalogo) S.catalogo = await chamar('catalogo')
  if (!S.catalogo) return
  const m = $('menu-fx')
  const c = S.catalogo
  m.innerHTML = `
    <h4>Efeitos do JARVIS</h4>
    ${c.nativos.map((n) => `<button data-tipo="${n.tipo}">${esc(n.nome)}</button>`).join('')}
    <h4>Cadeias prontas (troca tudo)</h4>
    ${c.presets.map((p) => `<button data-preset="${esc(p)}">${esc(p)}</button>`).join('')}
    <h4>VST3 instalados</h4>
    ${c.vst3.length ? c.vst3.map((v) => `<button data-vst="${esc(v.caminho)}">${esc(v.nome)}</button>`).join('') : '<button disabled style="color:var(--texto-3)">nenhum na pasta padrão</button>'}
    <button data-vst="">Procurar arquivo .vst3…</button>`
  const r = $('b-add-fx').getBoundingClientRect()
  m.classList.remove('oculto')
  m.style.left = `${r.left}px`
  m.style.top = `${Math.max(10, r.top - m.offsetHeight - 6)}px`
}

$('b-add-fx').addEventListener('click', (e) => { e.stopPropagation(); abrirMenuFx() })
document.addEventListener('click', (e) => { if (!e.target.closest('#menu-fx')) $('menu-fx').classList.add('oculto') })

$('menu-fx').addEventListener('click', async (e) => {
  const b = e.target.closest('button')
  if (!b || b.disabled) return
  const f = faixaSel()
  $('menu-fx').classList.add('oculto')
  let r = null
  if (b.dataset.tipo) r = await chamar('adicionar_efeito', f.id, b.dataset.tipo)
  else if (b.dataset.preset) {
    if (f.efeitos.length && !confirm('A cadeia pronta substitui os efeitos atuais desta faixa. Continuar?')) return
    r = await chamar('aplicar_preset', f.id, b.dataset.preset)
  } else if ('vst' in b.dataset) {
    aviso('Carregando o plugin…')
    r = await chamar('adicionar_vst', f.id, b.dataset.vst || null)
  }
  if (r && r.id) { trocarFaixa(r); renderFx(); renderCabecalhos() }
})

$('b-fx-recolher').addEventListener('click', () => {
  const p = $('painel-fx')
  p.classList.toggle('fechado')
  $('b-fx-recolher').textContent = p.classList.contains('fechado') ? 'abrir' : 'recolher'
  setTimeout(ajustarTamanho, 0)
})

// ------------------------------------------------------------------ timeline (canvas)
const cvOndas = $('ondas')
const cvSobre = $('sobre')
const cvRegua = $('regua')

function prepararCanvas(cv, w, h) {
  const dpr = window.devicePixelRatio || 1
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr)
    cv.height = Math.round(h * dpr)
    cv.style.width = `${w}px`
    cv.style.height = `${h}px`
  }
  const c = cv.getContext('2d')
  c.setTransform(dpr, 0, 0, dpr, 0, 0)
  return c
}

function larguraPistas() { return $('pistas').clientWidth }

function ajustarTamanho() {
  const h = Math.max(S.faixas.length * ALT, 10)
  $('pistas').style.height = `${h}px`
  S.sujo = true
}
window.addEventListener('resize', ajustarTamanho)

function duracaoTotal() {
  return S.faixas.reduce((m, f) => Math.max(m, (f.inicio + f.duracao) / sr()), 0)
}

function atualizarRolagem() {
  const vis = larguraPistas() / S.zoom
  const max = Math.max(duracaoTotal() + 30, vis) - vis
  if (S.scroll > max) S.scroll = Math.max(0, max)
  $('i-rolagem').max = Math.max(1, Math.round(max * 100))
  $('i-rolagem').value = Math.round(S.scroll * 100)
}

$('i-rolagem').addEventListener('input', (e) => { S.scroll = e.target.value / 100; S.sujo = true })

function desenharGrade(c, w, h, forte = 'rgba(56,189,248,0.16)', fraca = 'rgba(56,189,248,0.05)') {
  if (!S.resumo) return
  const batS = 60 / S.resumo.bpm
  const compS = batS * S.resumo.compasso
  const pxBat = batS * S.zoom
  let passoComp = 1
  while (compS * passoComp * S.zoom < 40) passoComp *= 2
  const t0 = Math.floor(S.scroll / batS) * batS
  for (let t = t0; (t - S.scroll) * S.zoom < w; t += batS) {
    const x = Math.round((t - S.scroll) * S.zoom) + 0.5
    const nBat = Math.round(t / batS)
    const ehComp = nBat % S.resumo.compasso === 0
    if (ehComp && (nBat / S.resumo.compasso) % passoComp === 0) c.fillStyle = forte
    else if (pxBat >= 12 && !ehComp) c.fillStyle = fraca
    else if (ehComp && passoComp === 1) c.fillStyle = forte
    else continue
    c.fillRect(x, 0, 1, h)
  }
}

function desenharOndas() {
  const w = larguraPistas()
  const h = S.faixas.length * ALT
  const c = prepararCanvas(cvOndas, w, Math.max(h, 1))
  c.clearRect(0, 0, w, h)
  if (!S.resumo) return
  S.faixas.forEach((f, i) => {
    const y = i * ALT
    c.fillStyle = f.id === S.sel ? 'rgba(34,211,238,0.05)' : i % 2 ? 'rgba(255,255,255,0.012)' : 'transparent'
    c.fillRect(0, y, w, ALT)
    c.fillStyle = 'rgba(56,189,248,0.12)'
    c.fillRect(0, y + ALT - 1, w, 1)
  })
  desenharGrade(c, w, h)

  const r = S.resumo
  if (r.loop_fim > r.loop_ini) {
    const x0 = amostraParaX(r.loop_ini), x1 = amostraParaX(r.loop_fim)
    c.fillStyle = r.loop ? 'rgba(251,191,36,0.06)' : 'rgba(251,191,36,0.025)'
    c.fillRect(x0, 0, x1 - x0, h)
  }

  const amPorPx = sr() / S.zoom
  S.faixas.forEach((f, i) => {
    if (!f.duracao) return
    const y = i * ALT + 5
    const alt = ALT - 10
    const x0 = amostraParaX(f.inicio)
    const x1 = amostraParaX(f.inicio + f.duracao)
    if (x1 < 0 || x0 > w) return
    c.fillStyle = hexA(f.cor, 0.13)
    c.fillRect(x0, y, x1 - x0, alt)
    c.strokeStyle = hexA(f.cor, 0.7)
    c.lineWidth = 1
    c.strokeRect(Math.round(x0) + 0.5, y + 0.5, Math.round(x1 - x0) - 1, alt - 1)

    const p = S.picos[f.id]
    if (p && p.picos.length) {
      const meio = y + alt / 2
      const escala = (alt / 2 - 4) / 255
      c.fillStyle = hexA(f.cor, 0.85)
      const a = Math.max(0, Math.floor(x0)), b = Math.min(w, Math.ceil(x1))
      for (let x = a; x < b; x++) {
        const s0 = (S.scroll + x / S.zoom) * sr() - f.inicio
        const i0 = Math.max(0, Math.floor(s0 / p.passo))
        const i1 = Math.min(p.picos.length, Math.max(i0 + 1, Math.floor((s0 + amPorPx) / p.passo)))
        let v = 0
        for (let k = i0; k < i1; k++) if (p.picos[k] > v) v = p.picos[k]
        const hh = Math.max(0.5, v * escala)
        c.fillRect(x, meio - hh, 1, hh * 2)
      }
    }
    c.fillStyle = 'rgba(2,9,18,0.65)'
    const nomeW = Math.min(c.measureText(f.nome).width + 12, Math.max(0, x1 - Math.max(x0, 0)))
    c.fillRect(Math.max(x0, 0) + 1, y + 1, nomeW, 16)
    c.fillStyle = f.cor
    c.font = '600 12px Rajdhani, Segoe UI, sans-serif'
    c.save(); c.beginPath(); c.rect(Math.max(x0, 0), y, Math.max(0, x1 - Math.max(x0, 0)), alt); c.clip()
    c.fillText(f.nome, Math.max(x0, 0) + 6, y + 13)
    c.restore()
  })
}

function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

function desenharSobre() {
  const w = larguraPistas()
  const h = S.faixas.length * ALT
  const c = prepararCanvas(cvSobre, w, Math.max(h, 1))
  c.clearRect(0, 0, w, h)
  const e = S.est
  if (!e || !S.resumo) return
  if (e.gravando) {
    const x0 = amostraParaX(Math.max(e.rec_inicio, 0)), x1 = amostraParaX(e.pos)
    S.faixas.forEach((f, i) => {
      if (!f.armada || x1 <= x0) return
      c.fillStyle = 'rgba(255,59,92,0.22)'
      c.fillRect(x0, i * ALT + 5, x1 - x0, ALT - 10)
      c.fillStyle = 'rgba(255,59,92,0.9)'
      c.fillRect(x0, i * ALT + 5, x1 - x0, 2)
    })
  }
  const x = Math.round(amostraParaX(e.pos)) + 0.5
  c.fillStyle = e.gravando ? '#ff3b5c' : '#a5f3fc'
  c.shadowColor = c.fillStyle
  c.shadowBlur = 8
  c.fillRect(x - 0.5, 0, 1.5, h)
  c.shadowBlur = 0
}

function desenharRegua() {
  const wrap = $('regua-wrap')
  const w = wrap.clientWidth, h = wrap.clientHeight
  const c = prepararCanvas(cvRegua, w, h)
  c.clearRect(0, 0, w, h)
  if (!S.resumo) return
  const r = S.resumo
  let ini = r.loop_ini, fim = r.loop_fim
  if (S.reguaSel) { ini = Math.min(S.reguaSel.a, S.reguaSel.b); fim = Math.max(S.reguaSel.a, S.reguaSel.b) }
  if (fim > ini) {
    const x0 = amostraParaX(ini), x1 = amostraParaX(fim)
    c.fillStyle = r.loop || S.reguaSel ? 'rgba(251,191,36,0.35)' : 'rgba(251,191,36,0.12)'
    c.fillRect(x0, 0, x1 - x0, h)
  }
  const batS = 60 / r.bpm
  const compS = batS * r.compasso
  let passo = 1
  while (compS * passo * S.zoom < 50) passo *= 2
  c.font = '11px JetBrains Mono, Consolas, monospace'
  const n0 = Math.max(0, Math.floor(S.scroll / compS))
  for (let n = n0; (n * compS - S.scroll) * S.zoom < w; n++) {
    const x = Math.round((n * compS - S.scroll) * S.zoom) + 0.5
    if (n % passo === 0) {
      c.fillStyle = 'rgba(165,243,252,0.55)'
      c.fillRect(x, h - 12, 1, 12)
      c.fillStyle = 'rgba(134,182,202,0.9)'
      c.fillText(String(n + 1), x + 4, 12)
    } else if (compS * S.zoom >= 14) {
      c.fillStyle = 'rgba(56,189,248,0.3)'
      c.fillRect(x, h - 6, 1, 6)
    }
  }
  if (S.est) {
    const x = amostraParaX(S.est.pos)
    c.fillStyle = S.est.gravando ? '#ff3b5c' : '#a5f3fc'
    c.beginPath(); c.moveTo(x - 6, 0); c.lineTo(x + 6, 0); c.lineTo(x, 9); c.fill()
  }
}

// ------------------------------------------------------------------ mouse na timeline
cvSobre.addEventListener('mousedown', (e) => {
  if (!S.resumo || e.button !== 0) return
  const rect = cvSobre.getBoundingClientRect()
  const x = e.clientX - rect.left, y = e.clientY - rect.top
  const f = S.faixas[Math.floor(y / ALT)]
  if (!f) return
  if (f.id !== S.sel) selecionar(f.id)
  const a = xParaAmostra(x)
  const dentro = f.duracao > 0 && a >= f.inicio && a <= f.inicio + f.duracao
  S.arrasto = { f, x0: e.clientX, ini: f.inicio, mover: dentro, moveu: false, a }
})

window.addEventListener('mousemove', (e) => {
  const d = S.arrasto
  if (d) {
    const dx = e.clientX - d.x0
    if (Math.abs(dx) > 3) d.moveu = true
    if (d.mover && d.moveu && !S.est?.gravando) {
      d.f.inicio = Math.max(0, snap(Math.round(d.ini + (dx / S.zoom) * sr())))
      S.sujo = true
    }
  }
  const r = S.reguaSel
  if (r) {
    const rect = cvRegua.getBoundingClientRect()
    r.b = snap(Math.max(0, xParaAmostra(e.clientX - rect.left)))
    if (Math.abs(e.clientX - r.x0) > 4) r.moveu = true
  }
})

window.addEventListener('mouseup', async () => {
  const d = S.arrasto
  S.arrasto = null
  if (d) {
    if (d.mover && d.moveu && d.f.inicio !== d.ini) await chamar('ajustar_faixa', d.f.id, 'inicio', d.f.inicio)
    else if (!d.moveu) await chamar('ir_para', Math.max(0, d.a))
  }
  const r = S.reguaSel
  S.reguaSel = null
  if (r) {
    if (r.moveu && r.a !== r.b) {
      r.a = snap(r.a)
      await chamar('ajustar_global', 'loop_ini', Math.min(r.a, r.b))
      await chamar('ajustar_global', 'loop_fim', Math.max(r.a, r.b))
      await chamar('ajustar_global', 'loop', true)
      await atualizar()
    } else {
      await chamar('ir_para', Math.max(0, r.a))
    }
  }
})

cvRegua.addEventListener('mousedown', (e) => {
  if (!S.resumo || e.button !== 0) return
  const rect = cvRegua.getBoundingClientRect()
  const a = Math.max(0, xParaAmostra(e.clientX - rect.left))
  S.reguaSel = { a: snap(a), b: snap(a), x0: e.clientX, moveu: false }
  S.reguaSel.a = a
})

function zoomEm(fator, xMouse) {
  const t = S.scroll + xMouse / S.zoom
  S.zoom = Math.min(2000, Math.max(2, S.zoom * fator))
  S.scroll = Math.max(0, t - xMouse / S.zoom)
  S.sujo = true
}

for (const el of [cvSobre, cvRegua]) {
  el.addEventListener('wheel', (e) => {
    const rect = el.getBoundingClientRect()
    if (e.ctrlKey) {
      e.preventDefault()
      zoomEm(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX - rect.left)
    } else if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      e.preventDefault()
      S.scroll = Math.max(0, S.scroll + (e.shiftKey ? e.deltaY : e.deltaX) / S.zoom)
      S.sujo = true
    }
  }, { passive: false })
}
$('b-zoom-mais').addEventListener('click', () => zoomEm(1.5, 0))
$('b-zoom-menos').addEventListener('click', () => zoomEm(1 / 1.5, 0))

// ------------------------------------------------------------------ laço de estado e desenho
async function ciclo() {
  try {
    const e = await window.pywebview.api.estado()
    if (e && !e.erro) {
      S.est = e
      if (S.estavaGravando && !e.gravando) atualizar()
      S.estavaGravando = e.gravando
    }
  } catch (err) { /* janela fechando */ }
  setTimeout(ciclo, 33)
}

let erroMostrado = null
function quadro() {
  const e = S.est
  if (e && S.resumo) {
    $('relogio').textContent = tempo(e.pos)
    $('compasso-atual').textContent = compassoAtual(e.pos)
    $('b-play').classList.toggle('ligado', e.tocando && !e.gravando)
    $('b-rec').classList.toggle('ligado', e.gravando)
    const st = $('status')
    if (!e.aberto) st.innerHTML = '<span class="off">placa fechada</span><br>clique em ⚙ Áudio'
    else {
      const api = S.resumo.config?.api || ''
      const cpu = Math.round(e.cpu * 100)
      st.innerHTML = `${esc(api)} · ${S.resumo.sr / 1000}kHz · ${S.resumo.bloco}<br>` +
        `${S.resumo.latencia_ms} ms · <span class="${cpu > 70 ? 'ruim' : ''}">CPU ${cpu}%</span>` +
        (e.xruns ? ` · <span class="ruim" title="falhas de áudio (estalos)">${e.xruns} falhas</span>` : '')
    }
    if (e.erro && e.erro !== erroMostrado) { erroMostrado = e.erro; aviso(e.erro, true) }
    S.medidores.master = Math.max(e.master, (S.medidores.master || 0) * 0.86)
    $('m-master').style.height = `${nivelPct(S.medidores.master)}%`
    document.querySelectorAll('.cab').forEach((cab) => {
      const f = S.faixas.find((x) => x.id === cab.dataset.id)
      if (!f) return
      let v = e.medidores[f.id] || 0
      if (f.armada && e.entrada?.length) v = Math.max(v, ...f.entrada.map((c) => e.entrada[c] || 0))
      S.medidores[f.id] = Math.max(v, (S.medidores[f.id] || 0) * 0.86)
      cab.querySelector('[data-medidor]').style.width = `${nivelPct(S.medidores[f.id])}%`
    })
    // acompanha a agulha quando ela sai da tela
    if (e.tocando && !S.arrasto) {
      const x = amostraParaX(e.pos)
      const w = larguraPistas()
      if (x > w - 20 || x < 0) { S.scroll = Math.max(0, e.pos / sr() - (x < 0 ? 0.5 : 2)); S.sujo = true }
    }
  }
  if (S.sujo) { S.sujo = false; atualizarRolagem(); desenharOndas() }
  desenharSobre()
  desenharRegua()
  requestAnimationFrame(quadro)
}

// ------------------------------------------------------------------ barra de cima
async function alternarPlay() {
  if (S.est?.tocando) await chamar('pausar')
  else await chamar('tocar')
}

$('b-play').addEventListener('click', alternarPlay)
$('b-parar').addEventListener('click', () => chamar('parar'))
$('b-inicio').addEventListener('click', () => { chamar('ir_para', 0); S.scroll = 0; S.sujo = true })
$('b-rec').addEventListener('click', async () => {
  if (S.est?.gravando) await chamar('pausar')
  else await chamar('gravar')
})

async function alternarGlobal(campo, botao) {
  const v = !$(botao).classList.contains('ligado')
  const r = await chamar('ajustar_global', campo, v)
  if (r) { $(botao).classList.toggle('ligado', v); S.resumo[campo] = v; S.sujo = true }
}
$('b-metro').addEventListener('click', () => alternarGlobal('metronomo', 'b-metro'))
$('b-contagem').addEventListener('click', () => alternarGlobal('contagem', 'b-contagem'))
$('b-loop').addEventListener('click', () => {
  if (!(S.resumo.loop_fim > S.resumo.loop_ini) && !S.resumo.loop) aviso('Arraste na régua (em cima das faixas) para marcar o trecho do loop.')
  alternarGlobal('loop', 'b-loop')
})
$('b-grade').addEventListener('click', () => $('b-grade').classList.toggle('ligado'))

$('i-bpm').addEventListener('change', async (e) => {
  await chamar('ajustar_global', 'bpm', parseFloat(e.target.value) || 120)
  await atualizar()
})
$('i-compasso').addEventListener('change', async (e) => {
  await chamar('ajustar_global', 'compasso', parseInt(e.target.value) || 4)
  await atualizar()
})
$('i-master').addEventListener('input', (e) => chamar('ajustar_global', 'master_db', parseFloat(e.target.value)))
$('i-master').addEventListener('dblclick', (e) => { e.target.value = 0; chamar('ajustar_global', 'master_db', 0) })

async function novaFaixa() {
  const r = await chamar('nova_faixa')
  if (r) { S.sel = r.id; await atualizar() }
}
$('b-faixa').addEventListener('click', novaFaixa)

$('b-novo').addEventListener('click', async () => {
  if (!confirm('Começar um projeto novo? O que não foi salvo se perde.')) return
  await chamar('novo_projeto')
  S.picos = {}
  S.scroll = 0
  await atualizar()
})
$('b-abrir').addEventListener('click', async () => {
  const r = await chamar('abrir_projeto')
  if (r && r.projeto) {
    S.picos = {}
    S.scroll = 0
    await atualizar()
    if (r.avisos?.length) aviso(r.avisos.join(' · '), true)
    else aviso('Projeto aberto.')
  }
})
async function salvar(como = false) {
  const r = await chamar('salvar', como)
  if (r && r.projeto) { aviso(`Salvo em ${r.projeto}`); await atualizar() }
}
$('b-salvar').addEventListener('click', () => salvar(false))
$('b-importar').addEventListener('click', async () => {
  aviso('Escolha um ou mais arquivos de áudio…')
  const r = await chamar('importar')
  if (r && r.faixas) { aviso(`${r.faixas.length} faixa(s) importada(s).`); await atualizar() }
})
$('b-exportar').addEventListener('click', async () => {
  const r = await chamar('exportar_mix')
  if (r && r.arquivo) aviso(`Mix exportado: ${r.arquivo}`)
})

// ------------------------------------------------------------------ configurar áudio
let DISP = null

function preencherDispositivos(apiEscolhida, cfg) {
  const lista = DISP.dispositivos.filter((d) => d.api === apiEscolhida)
  const ent = lista.filter((d) => d.entradas > 0)
  const sai = lista.filter((d) => d.saidas > 0)
  $('c-entrada').innerHTML = '<option value="">(nenhuma, só tocar)</option>' +
    ent.map((d) => `<option ${d.nome === cfg.entrada ? 'selected' : ''}>${esc(d.nome)}</option>`).join('')
  $('c-saida').innerHTML = sai.map((d) => `<option ${d.nome === cfg.saida ? 'selected' : ''}>${esc(d.nome)}</option>`).join('')
  if (!cfg.entrada && ent.length) $('c-entrada').selectedIndex = 1
  const ehWasapi = apiEscolhida.includes('WASAPI')
  $('l-exclusivo').classList.toggle('oculto', !ehWasapi)
  $('w-exclusivo').classList.toggle('oculto', !ehWasapi)
  if (apiEscolhida === 'ASIO') espelharAsio()
}

function espelharAsio() {
  if ($('c-api').value !== 'ASIO') return
  const nome = $('c-saida').value
  const op = [...$('c-entrada').options].find((o) => o.value === nome)
  if (op) $('c-entrada').value = nome
}

async function abrirModalAudio(msg) {
  $('c-erro').textContent = msg || ''
  DISP = await chamar('dispositivos')
  if (!DISP) return
  const cfg = DISP.config || {}
  const comDisp = DISP.apis.filter((a) => DISP.dispositivos.some((d) => d.api === a))
  const preferida = cfg.api || (comDisp.includes('ASIO') ? 'ASIO' : comDisp.find((a) => a.includes('WASAPI')) || comDisp[0])
  $('c-api').innerHTML = comDisp.map((a) => `<option ${a === preferida ? 'selected' : ''}>${esc(a)}</option>`).join('')
  if (!comDisp.length) $('c-erro').textContent = 'Nenhuma placa de som encontrada.'
  preencherDispositivos($('c-api').value || '', cfg)
  if (cfg.sr) $('c-sr').value = String(cfg.sr)
  if (cfg.bloco) $('c-bloco').value = String(cfg.bloco)
  $('c-exclusivo').checked = !!cfg.exclusivo
  $('c-ajuste').value = S.resumo?.ajuste_latencia ?? 0
  $('c-info').textContent = S.resumo?.aberto
    ? `Agora: ${S.resumo.config.api}, ${S.resumo.latencia_ms} ms de ida e volta (a gravação já é alinhada com isso).`
    : ''
  $('modal-audio').classList.remove('oculto')
}

$('c-api').addEventListener('change', () => preencherDispositivos($('c-api').value, {}))
$('c-saida').addEventListener('change', espelharAsio)
$('b-audio').addEventListener('click', () => abrirModalAudio())
$('c-cancelar').addEventListener('click', () => $('modal-audio').classList.add('oculto'))
$('c-aplicar').addEventListener('click', async () => {
  $('c-erro').textContent = ''
  $('c-aplicar').disabled = true
  const cfg = {
    api: $('c-api').value, entrada: $('c-entrada').value || null, saida: $('c-saida').value,
    sr: parseInt($('c-sr').value), bloco: parseInt($('c-bloco').value), exclusivo: $('c-exclusivo').checked,
  }
  const r = await window.pywebview.api.configurar(cfg)
  $('c-aplicar').disabled = false
  if (r.erro) { $('c-erro').textContent = r.erro; return }
  await chamar('ajustar_global', 'ajuste_latencia', parseInt($('c-ajuste').value) || 0)
  await atualizar()
  $('modal-audio').classList.add('oculto')
  aviso(`Placa aberta: ${S.resumo.latencia_ms} ms de latência.`)
})

// ------------------------------------------------------------------ teclado
document.addEventListener('keydown', (e) => {
  const digitando = ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName) &&
    document.activeElement.type !== 'range'
  if (e.ctrlKey && e.key.toLowerCase() === 's') { e.preventDefault(); salvar(e.shiftKey); return }
  if (e.ctrlKey && e.key.toLowerCase() === 't') { e.preventDefault(); novaFaixa(); return }
  if (digitando || !$('modal-audio').classList.contains('oculto') || document.body.classList.contains('modo-musica')) return
  if (e.code === 'Space') { e.preventDefault(); alternarPlay() }
  else if (e.key === 'r' || e.key === 'R') $('b-rec').click()
  else if (e.key === 'Home') $('b-inicio').click()
  else if (e.key === 'l' || e.key === 'L') $('b-loop').click()
  else if (e.key === 'm' || e.key === 'M') $('b-metro').click()
})

// nome da faixa: salva quando sai do campo
$('cabecalhos').addEventListener('focusout', async (e) => {
  if (!e.target.classList.contains('nome')) return
  const id = e.target.closest('.cab').dataset.id
  const r = await chamar('ajustar_faixa', id, 'nome', e.target.value)
  if (r) { trocarFaixa(r); S.sujo = true; if (id === S.sel) $('fx-faixa').textContent = r.nome }
})

// ------------------------------------------------------------------ aba Músicas (JARVIS MUSIC)
const M = { url: null, abrindo: false }

function mensagemMusica(txt) {
  $('m-msg').textContent = txt
  $('m-msg').classList.remove('oculto')
}

async function ligarMusica(escolher = false) {
  if (M.abrindo) return
  M.abrindo = true
  mensagemMusica('Ligando o JARVIS MUSIC…\nNa primeira vez pode levar uns segundos.')
  const r = await chamar('musica_abrir', escolher)
  M.abrindo = false
  if (!r) { mensagemMusica('Não consegui ligar o JARVIS MUSIC.\nClique em "pasta…" e escolha a pasta dele (a que tem backend e instalar.bat).'); return }
  if (r.cancelado) { if (!M.url) mensagemMusica('Escolha a pasta do JARVIS MUSIC em "pasta…".'); return }
  M.url = r.url
  $('m-frame').src = r.url
  $('m-frame').classList.remove('oculto')
  $('m-msg').classList.add('oculto')
  listarAnalises()
}

async function listarAnalises() {
  if (!M.url) return
  const r = await chamar('musica_analises')
  if (!r) return
  const sel = $('m-analises')
  const atual = sel.value
  sel.innerHTML = r.analises.length
    ? r.analises.map((a) => `<option value="${esc(a.id)}">${esc(a.arquivo || a.id)}${a.concluido ? '' : ' (processando)'}</option>`).join('')
    : '<option value="">nenhuma música analisada ainda</option>'
  if ([...sel.options].some((o) => o.value === atual)) sel.value = atual
  $('m-importar').disabled = !r.analises.length
}

function mostrarVista(vista) {
  document.querySelectorAll('.aba').forEach((a) => a.classList.toggle('ativa', a.dataset.vista === vista))
  document.body.classList.toggle('modo-musica', vista === 'musica')
  $('vista-musica').classList.toggle('oculto', vista !== 'musica')
  document.documentElement.style.setProperty('--topo', `${document.querySelector('.barra').offsetHeight}px`)
  if (vista === 'musica') { if (!M.url) ligarMusica(); else listarAnalises() }
  else setTimeout(ajustarTamanho, 0)
}

document.querySelectorAll('.aba').forEach((a) => a.addEventListener('click', () => mostrarVista(a.dataset.vista)))
$('m-atualizar').addEventListener('click', listarAnalises)
$('m-pasta').addEventListener('click', () => ligarMusica(true))
$('m-analises').addEventListener('focus', listarAnalises)
$('m-importar').addEventListener('click', async () => {
  const id = $('m-analises').value
  if (!id) return
  $('m-importar').disabled = true
  aviso('Trazendo as faixas para o estúdio…')
  const r = await chamar('musica_importar', id)
  $('m-importar').disabled = false
  if (!r) return
  S.picos = {}
  await atualizar()
  mostrarVista('estudio')
  aviso(`${r.faixas.length} faixas de "${r.musica}" no estúdio (BPM ${r.bpm}).`)
})

// ------------------------------------------------------------------ início
async function iniciar() {
  S.catalogo = await chamar('catalogo')
  await atualizar()
  if (!S.faixas.length) {
    await chamar('novo_projeto')
    await atualizar()
  }
  ciclo()
  requestAnimationFrame(quadro)
  if (!S.resumo?.aberto) abrirModalAudio()
}

if (window.pywebview && window.pywebview.api && window.pywebview.api.resumo) iniciar()
else window.addEventListener('pywebviewready', iniciar)
