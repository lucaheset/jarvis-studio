import { useEffect, useRef, useState } from 'react'
import { LuMic, LuMicOff, LuVolume2 } from 'react-icons/lu'

const NOMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const AFINACOES = {
  'E padrão': [40, 45, 50, 55, 59, 64],
  'Eb (meio tom abaixo)': [39, 44, 49, 54, 58, 63],
  'D (um tom abaixo)': [38, 43, 48, 53, 57, 62],
  'Drop D': [38, 45, 50, 55, 59, 64],
  'Drop C#': [37, 44, 49, 54, 58, 63],
  'Drop C': [36, 43, 48, 53, 57, 62],
  'Drop B': [35, 42, 47, 52, 56, 61],
  'Baixo 4 cordas': [28, 33, 38, 43],
  'Baixo 5 cordas': [23, 28, 33, 38, 43],
}
const nome = (m) => `${NOMES[((m % 12) + 12) % 12]}${Math.floor(m / 12) - 1}`

/** YIN (de Cheveigné & Kawahara, 2002): frequência fundamental de um bloco. */
function yin(buf, sr, fmin = 28, fmax = 1400, limiar = 0.12) {
  const tauMax = Math.min(Math.floor(sr / fmin), Math.floor(buf.length / 2))
  const tauMin = Math.floor(sr / fmax)
  const n = buf.length - tauMax
  const d = new Float32Array(tauMax + 1)
  for (let tau = 1; tau <= tauMax; tau++) {
    let s = 0
    for (let i = 0; i < n; i++) { const x = buf[i] - buf[i + tau]; s += x * x }
    d[tau] = s
  }
  // diferença normalizada acumulada
  let soma = 0
  d[0] = 1
  for (let tau = 1; tau <= tauMax; tau++) { soma += d[tau]; d[tau] = soma ? (d[tau] * tau) / soma : 1 }
  let tau = -1
  for (let t = tauMin; t <= tauMax; t++) {
    if (d[t] < limiar) {
      while (t + 1 <= tauMax && d[t + 1] < d[t]) t++
      tau = t
      break
    }
  }
  if (tau < 0) return null
  // interpolação parabólica para precisão abaixo de uma amostra
  const a = d[tau - 1] ?? d[tau], b = d[tau], c = d[tau + 1] ?? d[tau]
  const den = a - 2 * b + c
  const fino = den ? tau + (a - c) / (2 * den) : tau
  return { freq: sr / fino, clareza: 1 - b }
}

/** Afinador pelo microfone ou pela interface de áudio. */
export default function Afinador() {
  const [ligado, setLigado] = useState(false)
  const [erro, setErro] = useState('')
  const [entradas, setEntradas] = useState([])
  const [entrada, setEntrada] = useState('')
  const [afinacao, setAfinacao] = useState('E padrão')
  const [referencia, setReferencia] = useState(440)
  const [leitura, setLeitura] = useState(null)   // {freq, midi, cents}
  const [nivel, setNivel] = useState(0)
  const audio = useRef(null)
  const historico = useRef([])
  const refRef = useRef(referencia)
  refRef.current = referencia

  const listar = async () => {
    try {
      const ds = await navigator.mediaDevices.enumerateDevices()
      setEntradas(ds.filter((d) => d.kind === 'audioinput'))
    } catch { /* sem permissão ainda */ }
  }
  useEffect(() => { listar() }, [])

  const parar = () => {
    const a = audio.current
    if (a) {
      clearInterval(a.raf)
      a.stream.getTracks().forEach((t) => t.stop())
      a.ctx.close()
    }
    audio.current = null
    setLigado(false)
    setLeitura(null)
    setNivel(0)
  }

  const ligar = async (id = entrada) => {
    parar()
    setErro('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: id ? { exact: id } : undefined,
          echoCancellation: false, noiseSuppression: false, autoGainControl: false,
        },
      })
      await listar()
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      const fonte = ctx.createMediaStreamSource(stream)
      const an = ctx.createAnalyser()
      an.fftSize = 4096
      fonte.connect(an)
      const buf = new Float32Array(an.fftSize)
      const a = { stream, ctx, an, raf: 0 }
      audio.current = a
      setLigado(true)
      const quadro = () => {  // ~30 leituras por segundo bastam e poupam CPU
        an.getFloatTimeDomainData(buf)
        let rms = 0
        for (let i = 0; i < buf.length; i++) rms += buf[i] * buf[i]
        rms = Math.sqrt(rms / buf.length)
        setNivel(Math.min(1, rms * 6))
        const r = rms > 0.006 ? yin(buf, ctx.sampleRate) : null
        if (r && r.clareza > 0.85) {
          const h = historico.current
          h.push(r.freq)
          if (h.length > 5) h.shift()
          const f = [...h].sort((x, y) => x - y)[Math.floor(h.length / 2)]  // mediana: sem pulos
          const midiF = 69 + 12 * Math.log2(f / refRef.current)
          const midi = Math.round(midiF)
          setLeitura({ freq: f, midi, cents: Math.round((midiF - midi) * 100) })
        } else if (rms <= 0.006) {
          historico.current = []
        }
      }
      a.raf = setInterval(quadro, 33)
    } catch (e) {
      setErro(e.name === 'NotAllowedError'
        ? 'o navegador não deixou usar o microfone: libere o acesso no cadeado da barra de endereço'
        : `não consegui abrir a entrada de áudio (${e.message})`)
      setLigado(false)
    }
  }

  useEffect(() => () => parar(), [])

  const tocarReferencia = (midi) => {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const o = ctx.createOscillator()
    const g = ctx.createGain()
    o.type = 'triangle'
    o.frequency.value = refRef.current * 2 ** ((midi - 69) / 12)
    g.gain.setValueAtTime(0.0001, ctx.currentTime)
    g.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + 0.02)
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 2)
    o.connect(g).connect(ctx.destination)
    o.start()
    o.stop(ctx.currentTime + 2.05)
    setTimeout(() => ctx.close(), 2300)
  }

  const cordas = AFINACOES[afinacao]
  // corda mais perto da nota tocada
  let alvo = null
  if (leitura) {
    const midiF = leitura.midi + leitura.cents / 100
    alvo = cordas.reduce((m, c) => (Math.abs(c - midiF) < Math.abs(m - midiF) ? c : m), cordas[0])
  }
  const desvioAlvo = leitura && alvo !== null ? Math.round((leitura.midi + leitura.cents / 100 - alvo) * 100) : null
  const afinado = desvioAlvo !== null && Math.abs(desvioAlvo) <= 3
  const cents = leitura ? leitura.cents : 0

  return (
    <div className="linhas">
      <section className="painel">
        <div className="painel-cabeca">
          <h2 className="painel-titulo"><LuMic size={15} /> AFINADOR</h2>
          <span className="painel-sub">pelo microfone ou pela interface de áudio</span>
        </div>

        <div className="afi-controles">
          <button className={`btn ${ligado ? 'btn-perigo' : 'btn-primario'}`} onClick={() => (ligado ? parar() : ligar())}>
            {ligado ? <><LuMicOff size={15} /> desligar</> : <><LuMic size={15} /> ligar o afinador</>}
          </button>
          <label className="afi-campo">
            <span>entrada</span>
            <select value={entrada} onChange={(e) => { setEntrada(e.target.value); if (ligado) ligar(e.target.value) }}>
              <option value="">padrão do sistema</option>
              {entradas.map((d, i) => <option key={d.deviceId || i} value={d.deviceId}>{d.label || `entrada ${i + 1}`}</option>)}
            </select>
          </label>
          <label className="afi-campo">
            <span>afinação</span>
            <select value={afinacao} onChange={(e) => setAfinacao(e.target.value)}>
              {Object.keys(AFINACOES).map((a) => <option key={a}>{a}</option>)}
            </select>
          </label>
          <label className="afi-campo">
            <span>lá de referência</span>
            <input type="number" min="415" max="466" value={referencia}
              onChange={(e) => setReferencia(Math.min(466, Math.max(415, Number(e.target.value) || 440)))} /> Hz
          </label>
          <div className="afi-nivel" title="nível do sinal"><i style={{ width: `${nivel * 100}%` }} /></div>
        </div>
        {erro && <p className="aviso erro">{erro}</p>}

        <div className={`afi-mostrador${afinado ? ' ok' : ''}${leitura ? '' : ' vazio'}`}>
          <div className="afi-nota">
            {leitura ? NOMES[((leitura.midi % 12) + 12) % 12] : '–'}
            <small>{leitura ? Math.floor(leitura.midi / 12) - 1 : ''}</small>
          </div>
          <div className="afi-escala">
            {[-50, -40, -30, -20, -10, 0, 10, 20, 30, 40, 50].map((c) => (
              <i key={c} className={c === 0 ? 'zero' : ''} style={{ left: `${50 + c}%` }} />
            ))}
            <b className="afi-agulha" style={{ left: `${50 + Math.max(-50, Math.min(50, cents))}%` }} />
          </div>
          <div className="afi-info">
            {leitura
              ? <>{leitura.freq.toFixed(1)} Hz · {cents > 0 ? '+' : ''}{cents} cents
                {alvo !== null && <> · corda {nome(alvo)} {afinado ? '✓ afinada' : desvioAlvo > 0 ? `(${desvioAlvo} cents alta, afrouxe)` : `(${-desvioAlvo} cents baixa, aperte)`}</>}</>
              : ligado ? 'toque uma corda solta' : 'ligue o afinador para começar'}
          </div>
        </div>

        <div className="afi-cordas">
          {cordas.map((m, i) => (
            <button key={i} className={`afi-corda${alvo === m ? ' alvo' : ''}${alvo === m && afinado ? ' ok' : ''}`}
              onClick={() => tocarReferencia(m)} title="tocar a nota de referência">
              <b>{nome(m)}</b>
              <small>{(referencia * 2 ** ((m - 69) / 12)).toFixed(1)} Hz</small>
              <LuVolume2 size={11} />
            </button>
          ))}
        </div>
        <p className="aviso">
          Para a interface de áudio, escolha a entrada dela na lista (o navegador pede permissão na primeira vez).
          Clique numa corda para ouvir a nota de referência.
        </p>
      </section>
    </div>
  )
}
