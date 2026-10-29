import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { LuMusic, LuMinus, LuPlus, LuLocateFixed } from 'react-icons/lu'
import Transporte from './Transporte'
import { indiceEm } from './usarCompassos'

const NOTAS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const BEMOL = { Db: 'C#', Eb: 'D#', Gb: 'F#', Ab: 'G#', Bb: 'A#' }

/** Sobe ou desce um acorde em semitons ("F#m7" +1 -> "Gm7"). */
export function transpor(acorde, semitons) {
  if (!semitons || !acorde || acorde === 'N') return acorde
  const m = /^([A-G][#b]?)(.*)$/.exec(acorde)
  if (!m) return acorde
  const i = NOTAS.indexOf(BEMOL[m[1]] || m[1])
  if (i < 0) return acorde
  return NOTAS[(i + semitons + 120) % 12] + m[2]
}

/** Cifra que passa sozinha acompanhando os compassos da música. */
export default function CifraAoVivo({ estado, mixer, comp }) {
  const { dados, erro } = comp
  const [transp, setTransp] = useState(0)
  const [seguir, setSeguir] = useState(true)

  // cifra no tom que está tocando: transposição manual + tom do áudio
  const tt = transp + (mixer.semitons || 0)
  const compassos = dados?.compassos || []
  const pos = mixer.posicao
  const atual = indiceEm(compassos, pos)
  const c = compassos[atual]

  // tempo dentro do compasso
  let batida = -1
  if (c) for (let i = 0; i < c.batidas.length; i++) if (c.batidas[i] <= pos + 0.03) batida = i
  const acordeAgora = useMemo(() => {
    for (let i = atual; i >= 0; i--) {
      const lista = compassos[i].acordes.filter((a) => a.inicio <= pos + 0.03)
      if (lista.length) return lista[lista.length - 1].acorde
    }
    return null
  }, [compassos, atual, pos])
  const proximo = useMemo(() => {
    for (let i = Math.max(atual, 0); i < compassos.length; i++) {
      for (const a of compassos[i].acordes) {
        if (a.inicio > pos + 0.03 && a.acorde !== acordeAgora && a.acorde !== 'N') return a
      }
    }
    return null
  }, [compassos, atual, pos, acordeAgora])

  const tom = estado?.tom?.tom
  const tomTransp = tom ? `${transpor(tom.split(' ')[0], tt)} ${tom.split(' ')[1] || ''}` : null
  const faltam = proximo ? Math.max(0, proximo.inicio - pos) : null

  return (
    <div className="linhas">
      <section className="painel">
        <div className="painel-cabeca">
          <h2 className="painel-titulo"><LuMusic size={15} /> CIFRA AO VIVO</h2>
          <span className="painel-sub">
            {estado?.ritmo?.bpm ? `${estado.ritmo.bpm} BPM` : ''}
            {dados?.tempos_por_compasso ? ` · ${dados.tempos_por_compasso} tempos por compasso` : ''}
            {tomTransp ? ` · tom ${tomTransp}` : ''}
          </span>
        </div>
        <Transporte mixer={mixer} ritmo={estado?.ritmo} compassos={dados?.compassos} />

        {erro && <p className="aviso erro">{erro}</p>}
        {!dados && !erro && (
          <div className="vazio">gerando a cifra por compasso desta música (uns 20 segundos)…</div>
        )}

        {dados && (
          <div className="cv-hud">
            <div className="cv-agora">
              <small>{c ? (c.anacruse ? 'ANACRUSE' : `COMPASSO ${c.n}`) : 'PRONTO'}</small>
              <b key={acordeAgora}>{acordeAgora && acordeAgora !== 'N' ? transpor(acordeAgora, tt) : '–'}</b>
              <div className="cv-tempos">
                {(c?.batidas || Array.from({ length: dados.tempos_por_compasso || 4 })).map((_, i) => (
                  <i key={i} className={`${i === 0 ? 'forte' : ''}${mixer.tocando && i === batida ? ' on' : ''}`} />
                ))}
              </div>
            </div>
            <div className="cv-depois">
              <small>DEPOIS</small>
              <b>{proximo ? transpor(proximo.acorde, tt) : '–'}</b>
              {faltam !== null && mixer.tocando && <span>em {faltam.toFixed(1)}s</span>}
            </div>
            <div className="cv-opcoes">
              <span className="painel-sub">transpor</span>
              <div className="cv-transp">
                <button className="ctrl" onClick={() => setTransp((t) => t - 1)} title="descer meio tom"><LuMinus size={14} /></button>
                <b>{transp > 0 ? `+${transp}` : transp}</b>
                {mixer.semitons ? <small className="cv-audio">áudio {mixer.semitons > 0 ? '+' : ''}{mixer.semitons}</small> : null}
                <button className="ctrl" onClick={() => setTransp((t) => t + 1)} title="subir meio tom"><LuPlus size={14} /></button>
              </div>
              <button className={`btn btn-min${seguir ? ' ligado' : ''}`} onClick={() => setSeguir((s) => !s)}
                title="rolar a cifra sozinha acompanhando a música">
                <LuLocateFixed size={13} /> {seguir ? 'seguindo' : 'seguir'}
              </button>
            </div>
          </div>
        )}
      </section>

      {dados && compassos.length > 0 && (
        <section className="painel">
          <Grade compassos={compassos} atual={atual} transp={tt} seguir={seguir}
            aoClicar={(t) => mixer.irPara(t)} />
          <p className="aviso">
            Cifra automática: os acordes são estimados pelo áudio, então confira de ouvido. Clique num
            compasso para pular até ele.
          </p>
        </section>
      )}
    </div>
  )
}

/** Grade de compassos, 4 por linha. Só redesenha quando o compasso atual muda. */
const Grade = memo(function Grade({ compassos, atual, transp, seguir, aoClicar }) {
  const atualRef = useRef(null)
  const gradeRef = useRef(null)
  // rola só a grade (não a página) para manter o compasso atual no meio
  useEffect(() => {
    const g = gradeRef.current, el = atualRef.current
    if (!seguir || !g || !el) return
    const alvo = el.offsetTop - g.clientHeight / 2 + el.offsetHeight / 2
    g.scrollTo({ top: Math.max(0, alvo), behavior: 'smooth' })
  }, [atual, seguir])

  let anterior = null
  return (
    <div className="cv-grade" ref={gradeRef}>
      {compassos.map((c, i) => {
        const n = c.batidas.length || 1
        const itens = c.acordes.map((a, k) => {
          const repetido = k === 0 && a.acorde === anterior
          anterior = a.acorde
          return (
            <span key={k} className={`${repetido ? 'repetido' : ''}${a.acorde === 'N' ? ' silencio' : ''}`}
              style={{ left: `${(a.batida / n) * 100}%` }}>
              {a.acorde === 'N' ? '·' : transpor(a.acorde, transp)}
            </span>
          )
        })
        return (
          <button key={i} ref={i === atual ? atualRef : null}
            className={`cv-compasso${i === atual ? ' atual' : i < atual ? ' passou' : ''}${c.anacruse ? ' anacruse' : ''}`}
            onClick={() => aoClicar(c.inicio)} title={`ir para o compasso ${c.n}`}>
            <small>{c.anacruse ? '' : c.n}</small>
            <div className="cv-acordes">{itens}</div>
          </button>
        )
      })}
    </div>
  )
})
