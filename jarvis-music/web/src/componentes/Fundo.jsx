import { useEffect, useRef } from 'react'

/** Fundo em 3 camadas: brilhos radiais, grade em perspectiva e partículas subindo. */
export default function Fundo() {
  const ref = useRef(null)

  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    let quadro
    const pontos = Array.from({ length: 70 }, () => ({
      x: Math.random(),
      y: Math.random(),
      r: Math.random() * 1.6 + 0.3,
      v: Math.random() * 0.00025 + 0.00005,
      a: Math.random() * Math.PI * 2,
    }))

    const medir = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      cv.width = cv.clientWidth * dpr
      cv.height = cv.clientHeight * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    medir()
    window.addEventListener('resize', medir)

    const desenhar = () => {
      const { clientWidth: w, clientHeight: h } = cv
      ctx.clearRect(0, 0, w, h)
      ctx.fillStyle = '#7dd3fc'
      for (const p of pontos) {
        p.y -= p.v
        if (p.y < 0) p.y = 1
        p.a += 0.01
        ctx.globalAlpha = 0.25 + Math.sin(p.a) * 0.2
        ctx.beginPath()
        ctx.arc(p.x * w, p.y * h, p.r, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.globalAlpha = 1
      quadro = requestAnimationFrame(desenhar)
    }
    quadro = requestAnimationFrame(desenhar)
    return () => {
      cancelAnimationFrame(quadro)
      window.removeEventListener('resize', medir)
    }
  }, [])

  return (
    <div className="fundo">
      <div className="fundo-brilho" />
      <div className="fundo-grade" />
      <canvas ref={ref} className="fundo-particulas" />
    </div>
  )
}
