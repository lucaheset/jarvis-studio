import { useEffect, useRef } from 'react'

/** Orbe HUD do JARVIS: anéis de marcação, arcos e globo de partículas.
 *  `estado`: 'parado' | 'ouvindo' | 'pensando' | 'tocando'
 *  `nivel`: 0..1, volume atual, usado para pulsar junto com a música. */
export default function Orbe({ estado = 'parado', nivel = 0, tam = 'min(380px, 38vh)', texto = 'MUSIC' }) {
  const ref = useRef(null)
  const vivo = useRef({ estado, nivel })

  useEffect(() => { vivo.current = { estado, nivel } }, [estado, nivel])

  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    let quadro, giro = 0, fase = 0

    // globo: pontos distribuídos na esfera de Fibonacci
    const N = 620
    const esfera = Array.from({ length: N }, (_, i) => {
      const y = 1 - (i / (N - 1)) * 2
      const r = Math.sqrt(Math.max(0, 1 - y * y))
      const t = Math.PI * (3 - Math.sqrt(5)) * i
      return [Math.cos(t) * r, y, Math.sin(t) * r]
    })

    const medir = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      cv.width = cv.clientWidth * dpr
      cv.height = cv.clientHeight * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    medir()
    const ro = new ResizeObserver(medir)
    ro.observe(cv)

    const desenhar = () => {
      const { estado: st, nivel: lv } = vivo.current
      const W = cv.clientWidth, H = cv.clientHeight
      const cx = W / 2, cy = H / 2, R = W * 0.47
      const vel = st === 'pensando' ? 0.009 : st === 'ouvindo' ? 0.004 : st === 'tocando' ? 0.0022 : 0.0012
      const luz = st === 'parado' ? 0.6 : 1
      giro += vel
      fase += 0.05
      const pulso = st === 'ouvindo' ? (Math.sin(fase) + 1) / 2 * 0.25 : 0
      ctx.clearRect(0, 0, W, H)

      // 1. halo
      const halo = ctx.createRadialGradient(cx, cy, R * 0.1, cx, cy, R)
      halo.addColorStop(0, `rgba(34,211,238,${0.18 * luz + lv * 0.25})`)
      halo.addColorStop(0.55, `rgba(14,116,144,${0.12 * luz})`)
      halo.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = halo
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill()

      // 2. marcas da mira
      ctx.strokeStyle = 'rgba(125,211,252,.35)'
      ctx.lineWidth = 1
      for (const s of [-1, 1]) {
        ctx.beginPath()
        ctx.moveTo(cx + s * R * 0.83, cy)
        ctx.lineTo(cx + s * R, cy)
        ctx.stroke()
      }

      // 3. anel de marcações
      ctx.save(); ctx.translate(cx, cy); ctx.rotate(giro)
      for (let i = 0; i < 180; i++) {
        const a = (i / 180) * Math.PI * 2
        const longa = i % 15 === 0
        ctx.strokeStyle = longa ? 'rgba(165,243,252,.8)' : 'rgba(56,189,248,.35)'
        ctx.lineWidth = longa ? 2 : 1
        const r1 = longa ? R * 0.925 : R * 0.95
        ctx.beginPath()
        ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1)
        ctx.lineTo(Math.cos(a) * R * 0.965, Math.sin(a) * R * 0.965)
        ctx.stroke()
      }
      ctx.restore()
      ctx.strokeStyle = 'rgba(56,189,248,.25)'
      ctx.lineWidth = 1
      ctx.beginPath(); ctx.arc(cx, cy, R * 0.985, 0, Math.PI * 2); ctx.stroke()

      // 4. dois arcos vermelhos (pulsam enquanto processa)
      ctx.save()
      ctx.strokeStyle = `rgba(255,59,92,${st === 'pensando' ? 0.35 + Math.abs(Math.sin(fase)) * 0.5 : 0.55})`
      ctx.lineWidth = 3; ctx.shadowColor = '#ff3b5c'; ctx.shadowBlur = 14
      for (const base of [Math.PI * 1.15, Math.PI * 0.15]) {
        ctx.beginPath(); ctx.arc(cx, cy, R * 0.885, base - giro * 0.6, base + 0.5 - giro * 0.6); ctx.stroke()
      }
      ctx.restore()

      // 5. seis segmentos ciano girando ao contrário
      ctx.save(); ctx.strokeStyle = 'rgba(34,211,238,.55)'; ctx.lineWidth = 2.5
      ctx.shadowColor = '#22d3ee'; ctx.shadowBlur = 10
      for (let i = 0; i < 6; i++) {
        const a = (i / 6) * Math.PI * 2 - giro * 1.6
        ctx.beginPath(); ctx.arc(cx, cy, R * 0.83, a, a + Math.PI / 4.2); ctx.stroke()
      }
      // 6. três arcos grossos
      ctx.strokeStyle = 'rgba(14,165,233,.35)'; ctx.lineWidth = 7; ctx.shadowBlur = 16
      for (let i = 0; i < 3; i++) {
        const a = (i / 3) * Math.PI * 2 + giro * 0.8
        ctx.beginPath(); ctx.arc(cx, cy, R * 0.755, a, a + Math.PI / 2.4); ctx.stroke()
      }
      // 7. círculo interno reagindo ao volume
      ctx.strokeStyle = `rgba(125,211,252,${0.45 + lv * 0.5})`
      ctx.lineWidth = 1.5; ctx.shadowBlur = 12
      ctx.beginPath(); ctx.arc(cx, cy, R * 0.7, 0, Math.PI * 2); ctx.stroke()
      ctx.restore()

      // 8. globo de partículas
      const inc = 0.35, cosI = Math.cos(inc), sinI = Math.sin(inc)
      const rg = R * 0.6 * (1 + lv * 0.06 + pulso * 0.04)
      for (const [x0, y0, z0] of esfera) {
        const x1 = x0 * Math.cos(giro * 2.2) - z0 * Math.sin(giro * 2.2)
        const z1 = x0 * Math.sin(giro * 2.2) + z0 * Math.cos(giro * 2.2)
        const y2 = y0 * cosI - z1 * sinI
        const z2 = y0 * sinI + z1 * cosI
        const p = (z2 + 1) / 2
        const onda = st === 'tocando' || st === 'ouvindo' ? Math.sin(fase * 0.6 + y0 * 6) * lv * 3 : 0
        ctx.globalAlpha = 0.25 + p * 0.65
        ctx.fillStyle = p > 0.5 ? '#cffafe' : '#38bdf8'
        const s = 0.7 + p * 1.5
        ctx.fillRect(cx + x1 * rg - s / 2 + onda, cy + y2 * rg - s / 2, s, s)
      }
      ctx.globalAlpha = 1
      // meridianos e paralelos
      ctx.strokeStyle = 'rgba(56,189,248,.18)'; ctx.lineWidth = 1
      for (let i = 0; i < 4; i++) {
        ctx.save(); ctx.translate(cx, cy); ctx.rotate(i * Math.PI / 4)
        ctx.beginPath(); ctx.ellipse(0, 0, rg * 0.35, rg, 0, 0, Math.PI * 2); ctx.stroke(); ctx.restore()
      }
      for (let i = 1; i <= 5; i++) {
        const y = -rg + (i / 6) * rg * 2
        const rr = Math.sqrt(Math.max(0, rg * rg - y * y))
        ctx.beginPath(); ctx.ellipse(cx, cy + y * cosI, rr, rr * 0.3, 0, 0, Math.PI * 2); ctx.stroke()
      }

      // 9. núcleo escuro para o texto respirar
      const nucleo = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.45)
      nucleo.addColorStop(0, 'rgba(2,12,26,.82)')
      nucleo.addColorStop(1, 'rgba(2,12,26,0)')
      ctx.fillStyle = nucleo
      ctx.beginPath(); ctx.arc(cx, cy, R * 0.45, 0, Math.PI * 2); ctx.fill()

      quadro = requestAnimationFrame(desenhar)
    }
    quadro = requestAnimationFrame(desenhar)
    return () => { cancelAnimationFrame(quadro); ro.disconnect() }
  }, [])

  return (
    <div style={{ position: 'relative', width: tam, aspectRatio: 1, containerType: 'inline-size' }}>
      <canvas ref={ref} style={{ width: '100%', height: '100%', display: 'block' }} />
      <div style={{
        position: 'absolute', inset: 0, display: 'grid', placeContent: 'center',
        textAlign: 'center', pointerEvents: 'none',
      }}>
        <div style={{
          fontFamily: 'Orbitron, sans-serif', fontSize: '10.5cqw', letterSpacing: '.24em',
          color: '#f0fdff', textShadow: '0 0 20px rgba(34,211,238,.9), 0 0 40px rgba(34,211,238,.5)',
          animation: estado === 'pensando' ? 'pulsar 1.2s ease-in-out infinite' : 'none',
        }}>JARVIS</div>
        <div style={{
          fontFamily: 'Orbitron, sans-serif', fontSize: '6.5cqw', letterSpacing: '.3em',
          color: '#a5f3fc', textShadow: '0 0 14px #22d3ee', marginTop: '2cqw',
        }}>{texto}</div>
      </div>
      <style>{'@keyframes pulsar{50%{opacity:.55}}'}</style>
    </div>
  )
}
