import { useEffect, useState } from 'react'

const SISTEMAS = [
  ['núcleo de áudio', 'ONLINE'],
  ['separador de instrumentos', 'ONLINE'],
  ['transcritor de guitarra', 'ONLINE'],
  ['detector de bpm e tom', 'ONLINE'],
  ['analisador de efeitos', 'ONLINE'],
  ['mixer multipista', 'ONLINE'],
]

/** Tela de abertura, igual à do JARVIS: subsistemas ligando um a um. */
export default function Boot({ aoFechar }) {
  const [n, setN] = useState(0)

  useEffect(() => {
    const t = setInterval(() => setN((v) => Math.min(v + 1, SISTEMAS.length)), 260)
    const fim = setTimeout(aoFechar, 2700)
    return () => { clearInterval(t); clearTimeout(fim) }
  }, [aoFechar])

  return (
    <div className="boot" onClick={aoFechar}>
      <div>
        <h1>J.A.R.V.I.S</h1>
        <div className="sub">M U S I C</div>
        <ul>
          {SISTEMAS.map(([nome, est], i) => (
            <li key={nome} className={i < n ? 'on' : ''}>
              <span>{nome}</span><b className="ok">{i < n ? est : '...'}</b>
            </li>
          ))}
        </ul>
        <div className="boot-barra"><i style={{ width: `${(n / SISTEMAS.length) * 100}%` }} /></div>
      </div>
    </div>
  )
}
