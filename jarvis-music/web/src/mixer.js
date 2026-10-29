import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

/** Mixer multipista com Web Audio: todas as faixas tocam em sincronia,
 *  cada uma com volume, mudo e solo próprios (como no Moises).
 *
 *  Também cuida de: velocidade e tom do áudio (versões renderizadas no
 *  servidor com Signalsmith Stretch), loop A-B, metrônomo alinhado nas
 *  batidas detectadas e contagem antes de entrar.
 *
 *  Todo tempo exposto (posicao, duracao, loop, irPara) é o tempo da música
 *  original, então cifra, tab e batidas continuam valendo em qualquer velocidade.
 */
export function useMixer(faixas, { id, compassos, ritmo } = {}) {
  const ctxRef = useRef(null)
  const bufs = useRef(new Map())     // id -> AudioBuffer (da versão atual)
  const nos = useRef(new Map())      // id -> { ganho, fonte }
  const analise = useRef(null)
  const saidaClick = useRef(null)
  const sons = useRef(null)          // buffers do click
  const quadro = useRef(null)
  // relógio: a música estava em p0 (tempo original) quando o ctx marcava t0
  const relogio = useRef({ p0: 0, t0: 0 })
  const desloc = useRef(0)           // posição quando parado (tempo original)
  const motor = useRef({ vel: 1, st: 0, A: null, B: null, tocando: false })
  const agendados = useRef(new Set())
  const contagemTimers = useRef([])

  const [carregando, setCarregando] = useState(false)
  const [prontas, setProntas] = useState([])
  const [tocando, setTocando] = useState(false)
  const [posicao, setPosicao] = useState(0)
  const [duracao, setDuracao] = useState(0)
  const [nivel, setNivel] = useState(0)
  const [volumes, setVolumes] = useState({})
  const [mudos, setMudos] = useState({})
  const [solos, setSolos] = useState({})
  const [velocidade, setVelocidade] = useState(1)
  const [semitons, setSemitons] = useState(0)
  const [variacao, setVariacao] = useState(null)   // {feitas, total, erro, alvo:{vel, st}}
  const [loop, setLoop] = useState({ a: null, b: null })
  const [click, setClick] = useState(false)
  const [volumeClick, setVolumeClick] = useState(0.8)
  const [contagem, setContagem] = useState(false)
  const [contando, setContando] = useState(null)   // número da contagem na tela
  const [voltas, setVoltas] = useState(0)           // quantas vezes o loop A-B já repetiu
  const ultimaPos = useRef(0)

  const ctx = () => {
    if (!ctxRef.current) {
      const AC = window.AudioContext || window.webkitAudioContext
      const ac = new AC()
      ctxRef.current = ac
      analise.current = ac.createAnalyser()
      analise.current.fftSize = 512
      analise.current.connect(ac.destination)
      saidaClick.current = ac.createGain()
      saidaClick.current.connect(ac.destination)
      // click: "tic" curto; o 1º tempo do compasso mais agudo e mais forte
      const fazer = (freq, forca) => {
        const n = Math.floor(ac.sampleRate * 0.05)
        const b = ac.createBuffer(1, n, ac.sampleRate)
        const d = b.getChannelData(0)
        for (let i = 0; i < n; i++) {
          const t = i / ac.sampleRate
          d[i] = Math.sin(2 * Math.PI * freq * t) * Math.exp(-t * 90) * forca
        }
        return b
      }
      sons.current = { forte: fazer(1760, 0.9), fraco: fazer(1175, 0.6) }
    }
    return ctxRef.current
  }

  // batidas para o metrônomo: a grade dos compassos (regular) ou as do detector
  const batidas = useMemo(() => {
    if (compassos?.length) {
      const l = []
      for (const c of compassos) c.batidas.forEach((b, i) => l.push({ t: b, forte: i === 0 && !c.anacruse }))
      return l
    }
    const fortes = new Set((ritmo?.fortes || []).map((t) => t.toFixed(2)))
    return (ritmo?.batidas || []).map((t) => ({ t, forte: fortes.has(t.toFixed(2)) }))
  }, [compassos, ritmo])
  const batidasRef = useRef(batidas)
  batidasRef.current = batidas

  /** posição na música (tempo original) num instante do AudioContext */
  const posEm = useCallback((tctx) => {
    const { p0, t0 } = relogio.current
    const { vel, A, B } = motor.current
    let p = p0 + Math.max(0, tctx - t0) * vel
    if (A !== null && B !== null && B > A && p0 < B && p >= B) p = A + ((p - A) % (B - A))
    return p
  }, [])

  // ------------------------------------------------------------ carregar faixas
  const carregarConjunto = useCallback(async (urls, aoProgredir) => {
    const ac = ctx()
    const novo = new Map()
    const ids = Object.keys(urls)
    let i = 0
    const trabalhar = async () => {
      while (i < ids.length) {
        const fid = ids[i++]
        try {
          const r = await fetch(urls[fid])
          novo.set(fid, await ac.decodeAudioData(await r.arrayBuffer()))
          aoProgredir?.(fid, novo.get(fid))
        } catch { /* faixa que não carregou fica de fora */ }
      }
    }
    await Promise.all([trabalhar(), trabalhar(), trabalhar()])
    return novo
  }, [])

  useEffect(() => {
    let cancelado = false
    if (!faixas?.length) {
      bufs.current.clear()
      setProntas([]); setDuracao(0); setPosicao(0); setTocando(false)
      return
    }
    setCarregando(true)
    motor.current.vel = 1; motor.current.st = 0
    setVelocidade(1); setSemitons(0); setVariacao(null)
    ;(async () => {
      const urls = Object.fromEntries(faixas.map((f) => [f.id, f.url]))
      const ok = []
      const novo = await carregarConjunto(urls, (fid, b) => {
        if (cancelado) return
        bufs.current.set(fid, b)
        ok.push(fid)
        setProntas([...ok])
        setDuracao((d) => Math.max(d, b.duration))
      })
      if (cancelado) return
      bufs.current = novo
      setCarregando(false)
    })()
    return () => { cancelado = true }
  }, [faixas, carregarConjunto])

  // ------------------------------------------------------------------ volumes
  const ganhoDe = useCallback((fid) => {
    const temSolo = Object.values(solos).some(Boolean)
    if (mudos[fid]) return 0
    if (temSolo && !solos[fid]) return 0
    return volumes[fid] ?? 0.85
  }, [volumes, mudos, solos])
  const ganhoRef = useRef(ganhoDe)
  ganhoRef.current = ganhoDe

  useEffect(() => {
    const ac = ctxRef.current
    if (!ac) return
    for (const [fid, n] of nos.current) n.ganho.gain.setTargetAtTime(ganhoDe(fid), ac.currentTime, 0.02)
  }, [ganhoDe])

  useEffect(() => {
    if (saidaClick.current) saidaClick.current.gain.value = volumeClick
  }, [volumeClick])

  // ---------------------------------------------------------- tocar e parar
  const pararFontes = useCallback(() => {
    for (const [, n] of nos.current) {
      try { n.fonte.stop() } catch { /* já parada */ }
      n.fonte.disconnect()
    }
    nos.current.clear()
    contagemTimers.current.forEach(clearTimeout)
    contagemTimers.current = []
    setContando(null)
  }, [])

  const clicar = useCallback((quando, forte) => {
    const ac = ctxRef.current
    if (!ac || !sons.current) return
    const s = ac.createBufferSource()
    s.buffer = forte ? sons.current.forte : sons.current.fraco
    s.connect(saidaClick.current)
    s.start(quando)
  }, [])

  /** começa a tocar de `de` (tempo original); com contagem, entra depois dela */
  const iniciar = useCallback((de, comContagem) => {
    const ac = ctx()
    pararFontes()
    const { vel, A, B } = motor.current
    const dur = duracaoRef.current
    let p = Math.max(0, Math.min(Number.isFinite(de) ? de : desloc.current, dur || 0))
    if (A !== null && B !== null && (p < A || p >= B)) p = A
    if (dur && p >= dur - 0.05) p = 0
    let quando = ac.currentTime + 0.06

    if (comContagem) {
      // um compasso de contagem, no andamento do trecho onde vai entrar
      const lista = compassosRef.current || []
      const c = lista.find((x) => x.inicio <= p && p < x.fim) || lista[0]
      const n = c ? Math.max(2, c.batidas.length) : 4
      const passo = (c ? (c.fim - c.inicio) / Math.max(1, c.batidas.length) : 0.5) / vel
      for (let k = 0; k < n; k++) {
        clicar(quando + k * passo, k === 0)
        contagemTimers.current.push(setTimeout(() => setContando(k + 1), (quando - ac.currentTime + k * passo) * 1000))
      }
      quando += n * passo
      contagemTimers.current.push(setTimeout(() => setContando(null), (quando - ac.currentTime) * 1000))
    }

    for (const [fid, buf] of bufs.current) {
      const fonte = ac.createBufferSource()
      fonte.buffer = buf
      if (A !== null && B !== null && B > A) {
        fonte.loop = true
        fonte.loopStart = A / vel
        fonte.loopEnd = B / vel
      }
      const ganho = ac.createGain()
      ganho.gain.value = ganhoRef.current(fid)
      fonte.connect(ganho).connect(analise.current)
      fonte.start(quando, p / vel)
      nos.current.set(fid, { fonte, ganho })
    }
    relogio.current = { p0: p, t0: quando }
    ultimaPos.current = p   // pular para trás (irPara, troca de velocidade) não conta como volta do loop
    agendados.current = new Set()
    motor.current.tocando = true
    setTocando(true)
  }, [pararFontes, clicar])

  const duracaoRef = useRef(duracao)
  duracaoRef.current = duracao
  const compassosRef = useRef(compassos)
  compassosRef.current = compassos
  const contagemRef = useRef(contagem)
  contagemRef.current = contagem

  const tocar = useCallback(async (de) => {
    const ac = ctx()
    if (ac.state === 'suspended') await ac.resume()
    iniciar(de, contagemRef.current)
  }, [iniciar])

  const pausar = useCallback(() => {
    const ac = ctxRef.current
    if (ac && motor.current.tocando) desloc.current = posEm(ac.currentTime)
    pararFontes()
    motor.current.tocando = false
    setTocando(false)
    setPosicao(desloc.current)
  }, [pararFontes, posEm])

  const irPara = useCallback((s) => {
    if (!Number.isFinite(s)) return
    desloc.current = Math.max(0, Math.min(s, duracaoRef.current || 0))
    setPosicao(desloc.current)
    if (motor.current.tocando) iniciar(desloc.current, false)
  }, [iniciar])

  /** continua do mesmo ponto depois de trocar áudio/loop, sem contagem */
  const retomar = useCallback(() => {
    const ac = ctxRef.current
    if (!ac || !motor.current.tocando) return
    iniciar(posEm(ac.currentTime), false)
  }, [iniciar, posEm])

  // ------------------------------------------------------------ loop A-B
  const definirLoop = useCallback((a, b) => {
    if (a !== null && b !== null && b - a < 0.2) return
    motor.current.A = a
    motor.current.B = b
    setLoop({ a, b })
    retomar()
  }, [retomar])

  const marcarA = useCallback(() => {
    const ac = ctxRef.current
    const p = motor.current.tocando && ac ? posEm(ac.currentTime) : desloc.current
    const b = motor.current.B !== null && motor.current.B > p + 0.2 ? motor.current.B : null
    motor.current.A = p; motor.current.B = b
    setLoop({ a: p, b })
    if (b !== null) retomar()
  }, [posEm, retomar])

  const marcarB = useCallback(() => {
    const ac = ctxRef.current
    const p = motor.current.tocando && ac ? posEm(ac.currentTime) : desloc.current
    const a = motor.current.A
    if (a === null || p - a < 0.2) return
    definirLoop(a, p)
  }, [posEm, definirLoop])

  const limparLoop = useCallback(() => definirLoop(null, null), [definirLoop])

  // ------------------------------------------------- velocidade e tom do áudio
  const pedidoRef = useRef(0)
  const mudarVariacao = useCallback(async (vel, st) => {
    vel = Math.round(vel * 100) / 100
    st = Math.round(st)
    if (vel === motor.current.vel && st === motor.current.st) return
    const pedido = ++pedidoRef.current
    const original = vel === 1 && st === 0
    setVariacao({ feitas: 0, total: faixas?.length || 0, erro: null, alvo: { vel, st } })
    try {
      let urls
      if (original) {
        urls = Object.fromEntries(faixas.map((f) => [f.id, f.url]))
      } else {
        const fd = new FormData()
        fd.append('velocidade', String(vel))
        fd.append('semitons', String(st))
        let r = await fetch(`/api/variacao/${id}`, { method: 'POST', body: fd })
        let info = await r.json()
        if (!r.ok) throw new Error(info.detail || 'não consegui preparar essa versão')
        while (!info.pronto) {
          if (info.erro) throw new Error(info.erro)
          if (pedido !== pedidoRef.current) return
          setVariacao({ feitas: info.feitas, total: info.total, erro: null, alvo: { vel, st } })
          await new Promise((ok) => setTimeout(ok, 700))
          r = await fetch(`/api/variacao/${id}?velocidade=${vel}&semitons=${st}`)
          info = await r.json()
          if (!r.ok) throw new Error(info.detail || 'falhou')
        }
        urls = Object.fromEntries(Object.entries(info.faixas).map(([fid, arq]) =>
          [fid, `/api/arquivo/${id}/variacoes/${info.chave}/${arq}`]))
      }
      if (pedido !== pedidoRef.current) return
      setVariacao({ feitas: 0, total: 0, erro: null, alvo: { vel, st }, decodificando: true })
      const novo = await carregarConjunto(urls)
      if (pedido !== pedidoRef.current) return
      // troca o áudio no mesmo ponto da música
      const ac = ctxRef.current
      const estava = motor.current.tocando
      const p = estava && ac ? posEm(ac.currentTime) : desloc.current
      if (estava) pararFontes()
      bufs.current = novo
      setDuracao(Math.max(0, ...[...novo.values()].map((b) => b.duration)) * vel)
      motor.current.vel = vel
      motor.current.st = st
      setVelocidade(vel)
      setSemitons(st)
      desloc.current = p
      if (estava) iniciar(p, false)
      setVariacao(null)
      return true
    } catch (e) {
      if (pedido === pedidoRef.current) setVariacao({ erro: e.message, alvo: { vel, st } })
      return false
    }
  }, [faixas, id, carregarConjunto, posEm, pararFontes, iniciar])

  // ------------------------------------- relógio, metrônomo e medidor de volume
  useEffect(() => {
    const dados = new Uint8Array(256)
    const passo = () => {
      const ac = ctxRef.current
      if (ac && tocando) {
        const p = posEm(ac.currentTime)
        const { A, B } = motor.current
        const comLoop = A !== null && B !== null
        if (!comLoop && duracao && p >= duracao) {
          pararFontes(); motor.current.tocando = false
          desloc.current = 0; setPosicao(0); setTocando(false)
        } else {
          // o loop voltou do B para o A: conta uma volta
          if (comLoop && p < ultimaPos.current - 0.25) setVoltas((v) => v + 1)
          ultimaPos.current = p
          setPosicao(p)
        }
        if (analise.current) {
          analise.current.getByteTimeDomainData(dados)
          let soma = 0
          for (const v of dados) soma += (v - 128) ** 2
          setNivel(Math.min(1, Math.sqrt(soma / dados.length) / 48))
        }
      } else if (!tocando) setNivel((n) => (n > 0.01 ? n * 0.85 : 0))
      quadro.current = requestAnimationFrame(passo)
    }
    quadro.current = requestAnimationFrame(passo)
    return () => cancelAnimationFrame(quadro.current)
  }, [tocando, duracao, pararFontes, posEm])

  // agenda os clicks um pouco à frente (não depende do quadro da tela)
  useEffect(() => {
    if (!tocando || !click) return
    const tick = () => {
      const ac = ctxRef.current
      if (!ac) return
      const agora = ac.currentTime
      const { vel, A, B } = motor.current
      const { t0 } = relogio.current
      const ini = Math.max(agora, t0)
      const janela = 0.15
      const p = posEm(ini)
      const trechos = []
      const fimP = p + janela * vel
      if (A !== null && B !== null && fimP > B && p < B) {
        trechos.push([p, B, 0])
        trechos.push([A, A + (fimP - B), (B - p) / vel])
      } else trechos.push([p, fimP, 0])
      for (const [de, ate, extra] of trechos) {
        for (const b of batidasRef.current) {
          if (b.t < de || b.t >= ate) continue
          const quando = ini + extra + (b.t - de) / vel
          const k = Math.round(quando * 100)
          if (agendados.current.has(k)) continue
          agendados.current.add(k)
          clicar(quando, b.forte)
        }
      }
    }
    tick()
    const t = setInterval(tick, 25)
    return () => clearInterval(t)
  }, [tocando, click, posEm, clicar])

  useEffect(() => () => { pararFontes(); ctxRef.current?.close() }, [pararFontes])

  return {
    carregando, prontas, tocando, posicao, duracao, nivel,
    volumes, mudos, solos,
    tocar, pausar, irPara,
    alternarMudo: (fid) => setMudos((m) => ({ ...m, [fid]: !m[fid] })),
    alternarSolo: (fid) => setSolos((s) => ({ ...s, [fid]: !s[fid] })),
    ajustarVolume: (fid, v) => setVolumes((x) => ({ ...x, [fid]: v })),
    zerarMixer: () => { setMudos({}); setSolos({}); setVolumes({}) },
    ganhos: () => Object.fromEntries((faixas || []).map((f) => [f.id, ganhoDe(f.id)])),
    // velocidade e tom
    velocidade, semitons, variacao, mudarVariacao,
    // loop
    loop, marcarA, marcarB, definirLoop, limparLoop, voltas, zerarVoltas: () => setVoltas(0),
    id,
    // para o "tocar junto": mesmo relógio do áudio
    contexto: ctx, posicaoEm: posEm, tocandoAgora: () => motor.current.tocando,
    // metrônomo e contagem
    click, setClick, volumeClick, setVolumeClick, contagem, setContagem, contando,
  }
}

export function tempoTexto(s) {
  if (!Number.isFinite(s)) return '0:00'
  const m = Math.floor(s / 60)
  const r = Math.floor(s % 60)
  return `${m}:${String(r).padStart(2, '0')}`
}
