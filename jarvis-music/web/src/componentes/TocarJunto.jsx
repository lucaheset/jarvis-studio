import { useEffect, useMemo, useRef, useState } from 'react'
import { LuMic, LuMicOff, LuTarget, LuRepeat } from 'react-icons/lu'
import { nomeNota } from './comum'
import { indiceEm } from './usarCompassos'

/** YIN (de Cheveigné & Kawahara): fundamental de um bloco, para notas soltas. */
function yin(buf, sr, fmin = 70, fmax = 1400, limiar = 0.15) {
  const tauMax = Math.min(Math.floor(sr / fmin), Math.floor(buf.length / 2))
  const tauMin = Math.floor(sr / fmax)
  const n = buf.length - tauMax
  const d = new Float32Array(tauMax + 1)
  for (let tau = 1; tau <= tauMax; tau++) {
    let s = 0
    for (let i = 0; i < n; i++) { const x = buf[i] - buf[i + tau]; s += x * x }
    d[tau] = s
  }
  let soma = 0
  d[0] = 1
  for (let tau = 1; tau <= tauMax; tau++) { soma += d[tau]; d[tau] = soma ? (d[tau] * tau) / soma : 1 }
  for (let t = tauMin; t <= tauMax; t++) {
    if (d[t] < limiar) {
      while (t + 1 <= tauMax && d[t + 1] < d[t]) t++
      const a = d[t - 1] ?? d[t], b = d[t], c = d[t + 1] ?? d[t]
      const den = a - 2 * b + c
      return sr / (den ? t + (a - c) / (2 * den) : t)
    }
  }
  return null
}

/** croma (12 classes de altura) do espectro, para conferir acordes */
function croma(espectroDb, sr, nfft) {
  const v = new Float32Array(12)
  for (let k = 1; k < espectroDb.length; k++) {
    const f = (k * sr) / nfft
    if (f < 75 || f > 2200) continue
    const mag = 10 ** (espectroDb[k] / 20)
    const pc = ((Math.round(12 * Math.log2(f / 440)) + 69) % 12 + 12) % 12
    v[pc] += mag * mag
  }
  const norma = Math.hypot(...v) || 1
  return v.map((x) => x / norma)
}

/** Tocar junto com nota: ouve a guitarra pela entrada de áudio, confere com a tab e
 *  dá a nota de cada compasso. Usa o mesmo relógio do áudio da música. */
export default function TocarJunto({ notas, compassos, mixer, aoNotas }) {
  const [ligado, setLigado] = useState(false)
  const [entradas, setEntradas] = useState([])
  const [entrada, setEntrada] = useState('')
  const [latencia, setLatencia] = useState(0.12)    // segundos entre você tocar e o som chegar aqui
  const [calibrando, setCalibrando] = useState(null)
  const [erro, setErro] = useState('')
  const [ultimo, setUltimo] = useState(null)        // {tocou, esperado, ok}
  const [placar, setPlacar] = useState({})          // k -> {certo, errado, perdido}
  const audio = useRef(null)
  const estado = useRef({ casados: new Set(), placar: {}, extras: 0 })
  const latRef = useRef(latencia)
  latRef.current = latencia
  // o laço da entrada vive além de um render: lê sempre o mixer atual
  const mixerRef = useRef(mixer)
  mixerRef.current = mixer

  // eventos esperados: notas que começam juntas formam um evento (acorde)
  const eventos = useMemo(() => {
    const ord = [...notas].sort((a, b) => a.inicio - b.inicio)
    const ev = []
    for (const n of ord) {
      const ultimoEv = ev[ev.length - 1]
      if (ultimoEv && n.inicio - ultimoEv.t < 0.035) ultimoEv.midis.push(n.midi)
      else ev.push({ t: n.inicio, midis: [n.midi], k: Math.max(0, indiceEm(compassos, n.inicio + 0.02)) })
    }
    ev.forEach((e, i) => { e.i = i })
    return ev
  }, [notas, compassos])
  const eventosRef = useRef(eventos)
  eventosRef.current = eventos

  const listar = async () => {
    try { setEntradas((await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'audioinput')) } catch { /* sem permissão */ }
  }
  useEffect(() => { listar() }, [])

  const publicar = () => {
    const p = estado.current.placar
    setPlacar({ ...p })
    const porBar = {}
    for (const [k, v] of Object.entries(p)) {
      const tot = v.certo + v.errado + v.perdido
      if (tot) porBar[k] = v.certo / tot
    }
    aoNotas?.(porBar)
  }

  const zerar = () => {
    estado.current = { casados: new Set(), placar: {}, extras: 0 }
    setPlacar({}); setUltimo(null); aoNotas?.(null)
  }

  // nova volta do loop: as notas do trecho podem ser tocadas de novo
  useEffect(() => { estado.current.casados = new Set() }, [mixer.voltas])

  const registrar = (k, campo) => {
    const p = estado.current.placar
    p[k] = p[k] || { certo: 0, errado: 0, perdido: 0 }
    p[k][campo]++
  }

  /** um ataque detectado na guitarra: casa com o evento esperado mais perto */
  const aoAtaque = (tCtx, midi, cr) => {
    const mixer = mixerRef.current
    if (!mixer.tocandoAgora()) return
    const vel = mixer.velocidade || 1
    // áudio com tom mudado: você toca com capotraste/afinação e soa a nota deslocada
    const st = mixer.semitons || 0
    const t = mixer.posicaoEm(tCtx - latRef.current)
    const tol = 0.13 * vel
    const ev = eventosRef.current
    let lo = 0, hi = ev.length - 1
    while (lo < hi) { const m = (lo + hi) >> 1; if (ev[m].t < t - tol) lo = m + 1; else hi = m }
    let melhor = null
    for (let i = lo; i < ev.length && ev[i].t <= t + tol; i++) {
      if (estado.current.casados.has(i)) continue
      if (!melhor || Math.abs(ev[i].t - t) < Math.abs(melhor.t - t)) melhor = ev[i]
    }
    if (!melhor) { estado.current.extras++; return }
    estado.current.casados.add(melhor.i)
    let ok
    if (melhor.midis.length === 1) {
      const e = melhor.midis[0] + st
      ok = midi !== null && (midi === e || Math.abs(midi - e) === 12)   // erro de oitava do detector conta
    } else {
      const alvo = new Float32Array(12)
      for (const m of melhor.midis) alvo[(((m + st) % 12) + 12) % 12] = 1
      const na = Math.hypot(...alvo) || 1
      let sim = 0
      for (let i = 0; i < 12; i++) sim += (alvo[i] / na) * cr[i]
      ok = sim > 0.62
    }
    registrar(melhor.k, ok ? 'certo' : 'errado')
    setUltimo({
      tocou: midi !== null && melhor.midis.length === 1 ? nomeNota(midi) : 'acorde',
      esperado: melhor.midis.length === 1 ? nomeNota(melhor.midis[0] + st) : melhor.midis.map((m) => nomeNota(m + st).replace(/\d/, '')).join(' '),
      ok,
    })
    publicar()
  }

  // notas que passaram sem você tocar viram "perdidas"
  useEffect(() => {
    if (!ligado || !mixer.tocando) return
    const t = setInterval(() => {
      const ac = mixer.contexto()
      const agora = mixer.posicaoEm(ac.currentTime - latRef.current)
      const tol = 0.13 * (mixer.velocidade || 1)
      const ev = eventosRef.current
      const ini = audio.current?.inicio ?? 0
      let mudou = false
      for (const e of ev) {
        if (e.t > agora - tol) break
        if (e.t < ini || estado.current.casados.has(e.i)) continue
        if (agora - e.t > 2.5) { estado.current.casados.add(e.i); continue }  // muito antigo: ignora
        estado.current.casados.add(e.i)
        registrar(e.k, 'perdido')
        mudou = true
      }
      if (mudou) publicar()
    }, 120)
    return () => clearInterval(t)
  }, [ligado, mixer.tocando]) // eslint-disable-line react-hooks/exhaustive-deps

  const desligar = () => {
    const a = audio.current
    if (a) { clearInterval(a.timer); a.stream.getTracks().forEach((t) => t.stop()); a.fonte.disconnect() }
    audio.current = null
    setLigado(false)
  }

  const ligar = async (id = entrada) => {
    desligar()
    setErro('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { deviceId: id ? { exact: id } : undefined, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      })
      await listar()
      const ac = mixer.contexto()
      if (ac.state === 'suspended') await ac.resume()
      const fonte = ac.createMediaStreamSource(stream)
      const an = ac.createAnalyser()
      an.fftSize = 2048
      an.smoothingTimeConstant = 0
      fonte.connect(an)   // não vai para as caixas: só análise
      const buf = new Float32Array(an.fftSize)
      const esp = new Float32Array(an.frequencyBinCount)
      let media = 0.002, ultimoAtaque = 0, pendente = null
      const timer = setInterval(() => {
        an.getFloatTimeDomainData(buf)
        // energia dos últimos ~10 ms (fim do bloco)
        let e = 0
        for (let i = buf.length - 480; i < buf.length; i++) e += buf[i] * buf[i]
        const rms = Math.sqrt(e / 480)
        const agora = ac.currentTime
        if (pendente && agora >= pendente.analisarEm) {
          // 50 ms depois do ataque: o som já estabilizou para medir a altura
          const f = yin(buf, ac.sampleRate)
          an.getFloatFrequencyData(esp)
          const midi = f ? Math.round(69 + 12 * Math.log2(f / 440)) : null
          aoAtaque(pendente.t, midi, croma(esp, ac.sampleRate, an.fftSize))
          if (calibRef.current) calibRef.current.push(pendente.t)
          pendente = null
        }
        if (rms > Math.max(0.01, media * 2.2) && agora - ultimoAtaque > 0.07) {
          ultimoAtaque = agora
          pendente = { t: agora - 0.01, analisarEm: agora + 0.05 }
        }
        media = media * 0.92 + rms * 0.08
      }, 8)
      audio.current = { stream, fonte, an, timer, inicio: mixer.posicao }
      setLigado(true)
    } catch (e) {
      setErro(e.name === 'NotAllowedError'
        ? 'o navegador não deixou usar o microfone: libere no cadeado da barra de endereço'
        : `não consegui abrir a entrada (${e.message})`)
    }
  }
  useEffect(() => () => desligar(), [])  // eslint-disable-line react-hooks/exhaustive-deps

  // calibração: 8 clicks; você toca junto e medimos o atraso médio
  const calibRef = useRef(null)
  const calibrar = async () => {
    if (!ligado) await ligar()
    const ac = mixer.contexto()
    const inicio = ac.currentTime + 1.0
    const clicks = []
    for (let i = 0; i < 8; i++) {
      const t = inicio + i * 0.6
      clicks.push(t)
      const o = ac.createOscillator(), g = ac.createGain()
      o.frequency.value = i % 4 ? 1175 : 1760
      g.gain.setValueAtTime(0.0001, t)
      g.gain.exponentialRampToValueAtTime(0.5, t + 0.002)
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.05)
      o.connect(g).connect(ac.destination)
      o.start(t); o.stop(t + 0.06)
    }
    calibRef.current = []
    setCalibrando('toque uma corda junto com cada click (8 vezes)…')
    setTimeout(() => {
      const ataques = calibRef.current || []
      calibRef.current = null
      const atrasos = clicks.map((c) => {
        const perto = ataques.filter((a) => Math.abs(a - c) < 0.35).sort((x, y) => Math.abs(x - c) - Math.abs(y - c))[0]
        return perto === undefined ? null : perto - c
      }).filter((x) => x !== null).sort((a, b) => a - b)
      if (atrasos.length < 4) { setCalibrando(`só ouvi ${atrasos.length} de 8 ataques: tente de novo tocando mais forte`); return }
      const med = atrasos[Math.floor(atrasos.length / 2)]
      setLatencia(Math.max(0, Math.min(0.4, med)))
      setCalibrando(`atraso medido: ${Math.round(med * 1000)} ms`)
    }, (inicio - ac.currentTime + 8 * 0.6 + 0.5) * 1000)
  }

  // resumo
  const tot = Object.values(placar).reduce((a, v) => ({ certo: a.certo + v.certo, errado: a.errado + v.errado, perdido: a.perdido + v.perdido }), { certo: 0, errado: 0, perdido: 0 })
  const todos = tot.certo + tot.errado + tot.perdido
  const piores = Object.entries(placar)
    .map(([k, v]) => ({ k: Number(k), nota: v.certo / Math.max(1, v.certo + v.errado + v.perdido), n: v.certo + v.errado + v.perdido }))
    .filter((x) => x.n >= 2 && x.nota < 0.85).sort((a, b) => a.nota - b.nota).slice(0, 4)

  const praticar = (k) => {
    const c = compassos[k]
    if (!c) return
    mixer.definirLoop(c.inicio, c.fim)
    mixer.irPara(c.inicio)
  }

  return (
    <div className="tj">
      <div className="tj-linha">
        <span className="estudo-rotulo"><LuTarget size={12} /> tocar junto</span>
        <button className={`btn btn-min ${ligado ? 'btn-perigo' : 'btn-primario'}`} onClick={() => (ligado ? desligar() : ligar())}>
          {ligado ? <><LuMicOff size={13} /> parar</> : <><LuMic size={13} /> ligar a guitarra</>}
        </button>
        <select value={entrada} onChange={(e) => { setEntrada(e.target.value); if (ligado) ligar(e.target.value) }}>
          <option value="">entrada padrão</option>
          {entradas.map((d, i) => <option key={d.deviceId || i} value={d.deviceId}>{d.label || `entrada ${i + 1}`}</option>)}
        </select>
        <label className="tj-lat" title="atraso entre você tocar e o som chegar no programa">
          atraso <input type="range" min="0" max="0.4" step="0.005" value={latencia} onChange={(e) => setLatencia(Number(e.target.value))} />
          <b>{Math.round(latencia * 1000)} ms</b>
        </label>
        <button className="btn btn-min" onClick={calibrar}>calibrar</button>
        {todos > 0 && <button className="btn btn-min" onClick={zerar}>zerar</button>}
        {calibrando && <span className="treino-dica">{calibrando}</span>}
      </div>
      {erro && <p className="aviso erro">{erro}</p>}
      {ligado && (
        <div className="tj-linha">
          <span className={`tj-agora${ultimo ? (ultimo.ok ? ' ok' : ' erro') : ''}`}>
            {ultimo ? <>tocou <b>{ultimo.tocou}</b> · era <b>{ultimo.esperado}</b></> : 'dê play e toque junto com a tab'}
          </span>
          {todos > 0 && (
            <span className="tj-placar">
              <b>{Math.round((tot.certo / todos) * 100)}%</b> certo · {tot.errado} erradas · {tot.perdido} perdidas
            </span>
          )}
          {piores.length > 0 && (
            <span className="tj-piores">
              praticar:
              {piores.map((p) => (
                <button key={p.k} className="chip-v" onClick={() => praticar(p.k)} title="fazer loop neste compasso">
                  <LuRepeat size={11} /> compasso {compassos[p.k]?.n} ({Math.round(p.nota * 100)}%)
                </button>
              ))}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
