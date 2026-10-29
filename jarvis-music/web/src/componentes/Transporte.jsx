import { useEffect, useRef } from 'react'
import { LuPlay, LuPause, LuRotateCcw, LuSlidersHorizontal, LuMinus, LuPlus, LuRepeat, LuX, LuTimer, LuHourglass } from 'react-icons/lu'
import { tempoTexto } from '../mixer'
import TreinoProgressivo from './TreinoProgressivo'

const VELOCIDADES = [0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1]

/** Barra de play: botão, tempo, linha do tempo com batidas, compassos e o loop A-B,
 *  e as ferramentas de estudo (velocidade, tom, loop, metrônomo e contagem). */
export default function Transporte({ mixer, ritmo, compassos }) {
  const ref = useRef(null)
  const { posicao, duracao, tocando, loop, velocidade, semitons, variacao } = mixer

  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const w = cv.clientWidth, h = cv.clientHeight
    cv.width = w * dpr; cv.height = h * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)
    if (!duracao) return

    if (loop.a !== null) {
      const xa = (loop.a / duracao) * w
      const xb = loop.b !== null ? (loop.b / duracao) * w : xa + 2
      ctx.fillStyle = 'rgba(251,191,36,.16)'
      ctx.fillRect(xa, 0, Math.max(2, xb - xa), h)
      ctx.fillStyle = '#fbbf24'
      ctx.fillRect(xa - 1, 0, 2, h)
      if (loop.b !== null) ctx.fillRect(xb - 1, 0, 2, h)
    }
    const fortes = new Set((ritmo?.fortes || []).map((t) => t.toFixed(2)))
    for (const b of ritmo?.batidas || []) {
      const x = (b / duracao) * w
      const forte = fortes.has(b.toFixed(2))
      ctx.strokeStyle = forte ? 'rgba(165,243,252,.75)' : 'rgba(56,189,248,.28)'
      ctx.lineWidth = forte ? 1.6 : 1
      ctx.beginPath(); ctx.moveTo(x, forte ? 2 : h * 0.3); ctx.lineTo(x, h - 2); ctx.stroke()
    }
    const x = (Math.min(posicao, duracao) / duracao) * w
    ctx.strokeStyle = '#fff'; ctx.shadowColor = '#22d3ee'; ctx.shadowBlur = 10
    ctx.lineWidth = 2
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke()
  }, [posicao, duracao, ritmo, loop])

  const clicar = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    mixer.irPara(((e.clientX - r.left) / r.width) * (duracao || 0))
  }

  // compasso atual (pelos compassos reais quando existirem)
  let compasso = 1
  const lista = compassos || []
  const atual = lista.findIndex((c) => c.inicio <= posicao && posicao < c.fim)
  if (atual >= 0) compasso = lista[atual].n
  else if (ritmo?.bpm && posicao) {
    const tempos = parseInt(ritmo?.compasso, 10) || 4
    compasso = Math.floor(posicao / ((60 / ritmo.bpm) * tempos)) + 1
  }

  // loop ajustado aos compassos: A no começo do compasso, B no fim
  const marcar = (qual) => {
    if (!lista.length) return qual === 'a' ? mixer.marcarA() : mixer.marcarB()
    const c = lista[Math.max(0, atual)] || lista[0]
    if (qual === 'a') {
      const b = loop.b !== null && loop.b > c.inicio + 0.2 ? loop.b : c.fim
      mixer.definirLoop(c.inicio, b)
    } else {
      const a = loop.a !== null && loop.a < c.fim - 0.2 ? loop.a : c.inicio
      mixer.definirLoop(a, c.fim)
    }
  }

  const alvo = variacao?.alvo
  const velMostrada = alvo && !variacao.erro ? alvo.vel : velocidade
  const stMostrado = alvo && !variacao.erro ? alvo.st : semitons
  const mudar = (v, s) => mixer.mudarVariacao(Math.min(1.25, Math.max(0.5, v)), Math.min(6, Math.max(-6, s)))

  return (
    <div className="transporte-caixa">
      <div className="transporte">
        <button className={`play${tocando ? ' tocando' : ''}`}
          onClick={() => (tocando ? mixer.pausar() : mixer.tocar())}
          title={tocando ? 'pausar (espaço)' : 'tocar (espaço)'}>
          {tocando ? <LuPause size={22} /> : <LuPlay size={22} />}
        </button>
        <button className="ctrl" onClick={() => mixer.irPara(loop.a ?? 0)} title="voltar ao início (ou ao A do loop)">
          <LuRotateCcw size={15} />
        </button>
        <div className="tempo">
          {tempoTexto(posicao)} / {tempoTexto(duracao)}
          <span style={{ color: 'var(--texto-3)' }}> · compasso {compasso}</span>
        </div>
        <div className="linha-tempo" onClick={clicar} title="clique para pular">
          <canvas ref={ref} />
        </div>
        <button className="btn btn-min" onClick={mixer.zerarMixer} title="voltar todos os volumes, mudos e solos">
          <LuSlidersHorizontal size={13} /> zerar mixer
        </button>
      </div>

      <div className="estudo">
        <div className="estudo-grupo" title="velocidade sem mudar o tom">
          <span className="estudo-rotulo">velocidade</span>
          {VELOCIDADES.map((v) => (
            <button key={v} className={`chip-v${Math.abs(velMostrada - v) < 0.001 ? ' on' : ''}`}
              onClick={() => mudar(v, stMostrado)}>{Math.round(v * 100)}%</button>
          ))}
          <button className="ctrl mini" onClick={() => mudar(velMostrada - 0.05, stMostrado)} title="-5%"><LuMinus size={12} /></button>
          <b className="estudo-valor">{Math.round(velMostrada * 100)}%</b>
          <button className="ctrl mini" onClick={() => mudar(velMostrada + 0.05, stMostrado)} title="+5%"><LuPlus size={12} /></button>
        </div>

        <div className="estudo-grupo" title="tom do áudio (a cifra acompanha)">
          <span className="estudo-rotulo">tom</span>
          <button className="ctrl mini" onClick={() => mudar(velMostrada, stMostrado - 1)} title="descer meio tom"><LuMinus size={12} /></button>
          <b className="estudo-valor">{stMostrado > 0 ? `+${stMostrado}` : stMostrado}</b>
          <button className="ctrl mini" onClick={() => mudar(velMostrada, stMostrado + 1)} title="subir meio tom"><LuPlus size={12} /></button>
          {(velMostrada !== 1 || stMostrado !== 0) && (
            <button className="chip-v" onClick={() => mudar(1, 0)} title="voltar ao original">original</button>
          )}
        </div>

        <div className="estudo-grupo" title="repetir um trecho sem parar (ajusta aos compassos)">
          <LuRepeat size={14} className={loop.b !== null ? 'estudo-ativo' : ''} />
          <button className={`chip-v${loop.a !== null ? ' on' : ''}`} onClick={() => marcar('a')}>A</button>
          <button className={`chip-v${loop.b !== null ? ' on' : ''}`} onClick={() => marcar('b')}>B</button>
          {loop.a !== null && (
            <>
              <span className="estudo-info">{tempoTexto(loop.a)}{loop.b !== null ? ` → ${tempoTexto(loop.b)}` : ''}</span>
              <button className="ctrl mini" onClick={mixer.limparLoop} title="tirar o loop"><LuX size={12} /></button>
            </>
          )}
        </div>

        <TreinoProgressivo mixer={mixer} id={mixer.id} />

        <div className="estudo-grupo">
          <button className={`chip-v${mixer.click ? ' on' : ''}`} onClick={() => mixer.setClick((c) => !c)}
            title="metrônomo nas batidas detectadas da música">
            <LuTimer size={12} /> click
          </button>
          {mixer.click && (
            <input type="range" min="0" max="1.5" step="0.05" value={mixer.volumeClick} style={{ width: 70 }}
              onChange={(e) => mixer.setVolumeClick(Number(e.target.value))} title="volume do click" />
          )}
          <button className={`chip-v${mixer.contagem ? ' on' : ''}`} onClick={() => mixer.setContagem((c) => !c)}
            title="um compasso de contagem antes de a música entrar">
            <LuHourglass size={12} /> contagem
          </button>
        </div>

        {variacao && !variacao.erro && (
          <span className="estudo-status">
            {variacao.decodificando ? 'carregando o áudio…'
              : `preparando ${Math.round(alvo.vel * 100)}%${alvo.st ? ` ${alvo.st > 0 ? '+' : ''}${alvo.st}` : ''} · ${variacao.feitas}/${variacao.total} faixas`}
          </span>
        )}
        {variacao?.erro && <span className="estudo-status erro">{variacao.erro}</span>}
      </div>

      {mixer.contando && <div className="contagem-grande">{mixer.contando}</div>}
    </div>
  )
}
