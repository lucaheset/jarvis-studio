import { memo, useEffect, useMemo, useRef } from 'react'
import { indiceEm } from './usarCompassos'

const PX_TEMPO = 58          // largura de um tempo (semínima) na tela
const ALTURA_CORDA = 15      // distância entre as cordas
const SIMBOLO = { bend: 'b', 'bend 1 tom+': 'b', slide: '/', 'hammer-on': 'h', 'pull-off': 'p', vibrato: '~' }
/** posição (0..1) de t dentro do compasso, seguindo as batidas reais */
function fracao(c, t) {
  const bs = [...c.batidas, c.fim]
  const n = bs.length - 1
  for (let b = 0; b < n; b++) {
    if (t < bs[b + 1] || b === n - 1) {
      const f = Math.min(1, Math.max(0, (t - bs[b]) / Math.max(1e-6, bs[b + 1] - bs[b])))
      return (b + f) / n
    }
  }
  return 0
}

/** cor do compasso pela nota do "tocar junto" */
function notaBarClasse(v) {
  if (v == null) return ''
  return v >= 0.85 ? ' bom' : v >= 0.6 ? ' medio' : ' ruim'
}

/** Tablatura desenhada que acompanha a música: cursor, compasso aceso, acordes em cima. */
export default function TabAoVivo({ notas, compassos, mixer, seguir = true, editando = false, selecionada = null,
  aoSelecionar, aoAdicionar, notasBar = null, secoes = null }) {
  // notas de cada compasso, com a posição horizontal já calculada
  const porCompasso = useMemo(() => {
    const lista = compassos.map(() => [])
    for (const n of notas) {
      if (n.corda == null) continue
      let k = indiceEm(compassos, n.inicio + 0.02)
      if (k < 0) k = 0
      if (k >= lista.length) continue
      lista[k].push(n)
    }
    return lista.map((ns, k) => ns.map((n) => ({ ...n, x: fracao(compassos[k], n.inicio) })))
  }, [notas, compassos])

  const atual = indiceEm(compassos, mixer.posicao)

  return (
    <div className="tv">
      <Compassos compassos={compassos} porCompasso={porCompasso} atual={atual} seguir={seguir && !editando}
        aoClicar={(t) => mixer.irPara(t)} editando={editando} selecionada={selecionada}
        aoSelecionar={aoSelecionar} aoAdicionar={aoAdicionar} notasBar={notasBar} secoes={secoes} />
      {atual >= 0 && <Cursor compasso={compassos[atual]} indice={atual} posicao={mixer.posicao} />}
    </div>
  )
}

/** Linha que anda dentro do compasso atual (só ela redesenha a cada quadro). */
function Cursor({ compasso, indice, posicao }) {
  const ref = useRef(null)
  const acesas = useRef([])
  useEffect(() => {
    // acende a(s) nota(s) que estão soando agora
    for (const el of acesas.current) el.classList.remove('agora')
    acesas.current = []
    const notasEl = document.querySelectorAll(`.tv-compasso[data-k="${indice}"] .tv-nota`)
    for (const el of notasEl) {
      const ini = Number(el.dataset.ini), fim = Number(el.dataset.fim)
      if (ini <= posicao + 0.02 && posicao < Math.max(fim, ini + 0.12)) {
        el.classList.add('agora')
        acesas.current.push(el)
      }
    }
  })
  useEffect(() => {
    const el = document.querySelector(`.tv-compasso[data-k="${indice}"]`)
    const cursor = ref.current
    if (!el || !cursor) return
    const pai = cursor.parentElement.getBoundingClientRect()
    const r = el.getBoundingClientRect()
    const x = r.left - pai.left + cursor.parentElement.scrollLeft + fracao(compasso, posicao) * r.width
    cursor.style.transform = `translate(${x}px, ${r.top - pai.top + cursor.parentElement.scrollTop}px)`
    cursor.style.height = `${r.height}px`
  })
  return <div className="tv-cursor" ref={ref} />
}

const Compassos = memo(function Compassos({ compassos, porCompasso, atual, seguir, aoClicar, editando, selecionada,
  aoSelecionar, aoAdicionar, notasBar, secoes }) {
  const caixa = useRef(null)
  useEffect(() => {
    const el = caixa.current?.querySelector(`.tv-compasso[data-k="${atual}"]`)
    const pai = caixa.current?.parentElement
    if (!seguir || !el || !pai) return
    const alvo = el.offsetTop - pai.clientHeight / 3
    if (Math.abs(pai.scrollTop - alvo) > el.offsetHeight / 2) pai.scrollTo({ top: Math.max(0, alvo), behavior: 'smooth' })
  }, [atual, seguir])

  let anterior = null
  return (
    <div className="tv-linhas" ref={caixa}>
      {compassos.map((c, k) => {
        const tempos = Math.max(1, c.batidas.length)
        const largura = tempos * PX_TEMPO
        const acordes = (c.acordes || []).filter((a) => a.acorde !== 'N').map((a) => {
          const repetido = a.batida === 0 && a.acorde === anterior
          anterior = a.acorde
          return repetido ? null : a
        }).filter(Boolean)
        return (
          <div key={k} data-k={k} style={{ width: largura }}
            className={`tv-compasso${k === atual ? ' atual' : ''}${editando ? ' editando' : ''}${notaBarClasse(notasBar?.[k])}`}
            onClick={(e) => {
              const r = e.currentTarget.getBoundingClientRect()
              const f = Math.min(0.999, Math.max(0, (e.clientX - r.left) / r.width))
              const bs = [...c.batidas, c.fim]
              const b = Math.max(0, Math.min(bs.length - 2, Math.floor(f * (bs.length - 1))))
              const resto = f * (bs.length - 1) - b
              const t = bs[b] + resto * (bs[b + 1] - bs[b])
              if (editando) {
                // clique num espaço vazio: nova nota na corda clicada, no tempo clicado (arredondado à semicolcheia)
                const corda = Math.max(1, Math.min(6, Math.round((e.clientY - r.top - 22) / ALTURA_CORDA) + 1))
                const q = Math.round(resto * 4) / 4
                aoAdicionar?.({ inicio: bs[b] + q * (bs[b + 1] - bs[b]), corda, passo: (bs[b + 1] - bs[b]) / 4 })
              } else aoClicar(t)
            }}>
            {secoes?.[k] && <span className={`tv-secao sec-${secoes[k].cor}`}>{secoes[k].nome}</span>}
            {notasBar?.[k] != null && <span className="tv-nota-bar">{Math.round(notasBar[k] * 100)}%</span>}
            <small className="tv-num">{c.anacruse ? '' : c.n}</small>
            {acordes.map((a, i) => (
              <b key={i} className="tv-acorde" style={{ left: (a.batida / tempos) * largura + 4 }}>{a.acorde}</b>
            ))}
            {Array.from({ length: 6 }, (_, i) => <i key={i} className="tv-corda" style={{ top: 22 + i * ALTURA_CORDA }} />)}
            {Array.from({ length: tempos - 1 }, (_, i) => (
              <i key={`t${i}`} className="tv-tempo" style={{ left: ((i + 1) / tempos) * largura }} />
            ))}
            {porCompasso[k].map((n, i) => {
              const tec = (n.tecnicas || []).map((t) => SIMBOLO[t]).filter(Boolean)[0]
              return (
                <span key={i}
                  className={`tv-nota${n.papel === 'solo' ? ' solo' : ''}${n.editada ? ' editada' : ''}${editando && n.uid === selecionada ? ' sel' : ''}`}
                  data-ini={n.inicio} data-fim={n.fim}
                  onClick={editando ? (e) => { e.stopPropagation(); aoSelecionar?.(n.uid) } : undefined}
                  style={{ left: 4 + n.x * (largura - 12), top: 22 + (n.corda - 1) * ALTURA_CORDA }}
                  title={`${n.nota || ''} · corda ${n.corda}, casa ${n.casa}${tec ? ` · ${n.tecnicas.join(', ')}` : ''}`}>
                  {n.casa}{tec && <sup>{tec}</sup>}
                </span>
              )
            })}
          </div>
        )
      })}
    </div>
  )
})
