import { useEffect, useRef } from 'react'
import { LuVolumeX, LuVolume2, LuHeadphones, LuGuitar, LuMic, LuDrum, LuPiano, LuAudioWaveform } from 'react-icons/lu'

const CORES = {
  voz: '#a78bfa', guitarra: '#22d3ee', guitarra_esquerda: '#38bdf8',
  guitarra_centro: '#a5f3fc', guitarra_direita: '#0ea5e9',
  baixo: '#34d399', bateria: '#fbbf24', piano: '#f472b6', outros: '#7dd3fc',
}
const ICONES = {
  voz: LuMic, guitarra: LuGuitar, guitarra_esquerda: LuGuitar,
  guitarra_centro: LuGuitar, guitarra_direita: LuGuitar,
  baixo: LuGuitar, bateria: LuDrum, piano: LuPiano, outros: LuAudioWaveform,
}

/** Uma pista do mixer: nome, forma de onda clicável, mudo, solo e volume. */
export default function Faixa({ faixa, mixer, pronta }) {
  const ref = useRef(null)
  const cor = CORES[faixa.id] || '#22d3ee'
  const Icone = ICONES[faixa.id] || LuAudioWaveform
  const { posicao, duracao, mudos, solos, volumes } = mixer
  const mudo = !!mudos[faixa.id]
  const solo = !!solos[faixa.id]

  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const w = cv.clientWidth, h = cv.clientHeight
    cv.width = w * dpr; cv.height = h * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)

    const picos = faixa.picos || []
    const meio = h / 2
    const passo = w / Math.max(picos.length, 1)
    const frac = duracao ? Math.min(1, posicao / duracao) : 0

    ctx.strokeStyle = 'rgba(125,211,252,.2)'
    ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(0, meio); ctx.lineTo(w, meio); ctx.stroke()

    picos.forEach((p, i) => {
      const x = i * passo
      const alt = Math.max(1.2, p * (h * 0.46))
      const passou = x / w <= frac
      ctx.fillStyle = passou ? cor : 'rgba(86,182,202,.42)'
      ctx.globalAlpha = passou ? 0.95 : 0.6
      ctx.fillRect(x, meio - alt, Math.max(1, passo * 0.8), alt * 2)
    })
    ctx.globalAlpha = 1

    if (frac > 0) {
      ctx.strokeStyle = '#fff'
      ctx.shadowColor = cor; ctx.shadowBlur = 8
      ctx.beginPath(); ctx.moveTo(frac * w, 0); ctx.lineTo(frac * w, h); ctx.stroke()
      ctx.shadowBlur = 0
    }
  }, [faixa.picos, posicao, duracao, cor])

  const clicar = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    mixer.irPara(((e.clientX - r.left) / r.width) * (duracao || 0))
  }

  return (
    <div className={`faixa${solo ? ' solada' : ''}${mudo ? ' mudo' : ''}`}>
      <div className="faixa-nome" style={{ color: cor }}>
        <i style={{ background: cor }} />
        <Icone size={15} />
        <span style={{ color: 'var(--texto)' }}>{faixa.rotulo}</span>
        {!pronta && <span style={{ color: 'var(--texto-3)', fontSize: 9 }}>carregando</span>}
      </div>
      <div className="faixa-ctrl">
        <button className={`ctrl${mudo ? ' ligado alerta' : ''}`} onClick={() => mixer.alternarMudo(faixa.id)}
          title={mudo ? 'tirar o mudo' : 'deixar mudo (remove o instrumento)'}>
          {mudo ? <LuVolumeX size={15} /> : <LuVolume2 size={15} />}
        </button>
        <button className={`ctrl${solo ? ' ligado' : ''}`} onClick={() => mixer.alternarSolo(faixa.id)}
          title="solar (ouvir só este instrumento)">
          <LuHeadphones size={15} />
        </button>
        <input type="range" min="0" max="1.4" step="0.02"
          value={volumes[faixa.id] ?? 0.85}
          onChange={(e) => mixer.ajustarVolume(faixa.id, Number(e.target.value))}
          title="volume" />
        <a className="btn btn-min" href={faixa.url} download title="baixar esta faixa">wav</a>
      </div>
      <div className="faixa-onda" onClick={clicar} title="clique para pular para este ponto">
        <canvas ref={ref} />
      </div>
    </div>
  )
}
