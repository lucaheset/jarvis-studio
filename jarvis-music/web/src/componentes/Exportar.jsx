import { useState } from 'react'
import { LuDownload, LuPackage } from 'react-icons/lu'

/** Exporta as faixas separadas (para a DAW) ou a mixagem atual, em WAV ou MP3. */
export default function Exportar({ id, estado, mixer }) {
  const faixas = estado?.faixas || []
  const [formato, setFormato] = useState('wav')
  const [modo, setModo] = useState('stems')
  const [escolhidas, setEscolhidas] = useState(() => Object.fromEntries(faixas.map((f) => [f.id, !f.derivada_de])))
  const [comVariacao, setComVariacao] = useState(true)
  const [trabalhando, setTrabalhando] = useState(false)
  const [msg, setMsg] = useState('')
  const variado = mixer.velocidade !== 1 || mixer.semitons !== 0

  const baixar = async () => {
    setTrabalhando(true); setMsg('')
    try {
      const fd = new FormData()
      fd.append('formato', formato)
      fd.append('modo', modo)
      const lista = modo === 'mix' ? faixas.filter((f) => !f.derivada_de).map((f) => f.id)
        : faixas.filter((f) => escolhidas[f.id]).map((f) => f.id)
      fd.append('faixas', JSON.stringify(lista))
      if (modo === 'mix') fd.append('ganhos', JSON.stringify(mixer.ganhos()))
      if (variado && comVariacao) {
        fd.append('velocidade', String(mixer.velocidade))
        fd.append('semitons', String(mixer.semitons))
      }
      const r = await fetch(`/api/exportar/${id}`, { method: 'POST', body: fd })
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'falhou')
      const nome = decodeURIComponent((r.headers.get('content-disposition') || '').match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i)?.[1] || `export.${modo === 'mix' ? formato : 'zip'}`)
      const blob = await r.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = nome
      document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
      setMsg(`pronto: ${nome}`)
    } catch (e) {
      setMsg(`erro: ${e.message}`)
    } finally { setTrabalhando(false) }
  }

  return (
    <section className="painel">
      <div className="painel-cabeca">
        <h2 className="painel-titulo"><LuPackage size={15} /> EXPORTAR PARA A DAW</h2>
        <span className="painel-sub">WAV 24 bits ou MP3 320 kbps</span>
      </div>
      <div className="aba-linha">
        {[['stems', 'faixas separadas (.zip)'], ['mix', 'mixagem atual']].map(([m, r]) => (
          <button key={m} className={`aba${modo === m ? ' ativo' : ''}`} onClick={() => setModo(m)}>{r}</button>
        ))}
        <span className="aba-sep" />
        {['wav', 'mp3'].map((f) => (
          <button key={f} className={`aba${formato === f ? ' ativo' : ''}`} onClick={() => setFormato(f)}>{f}</button>
        ))}
      </div>
      {modo === 'stems' ? (
        <div className="exp-faixas">
          {faixas.map((f) => (
            <label key={f.id} className={`exp-faixa${escolhidas[f.id] ? ' on' : ''}`}>
              <input type="checkbox" checked={!!escolhidas[f.id]}
                onChange={(e) => setEscolhidas((x) => ({ ...x, [f.id]: e.target.checked }))} />
              {f.rotulo}
            </label>
          ))}
        </div>
      ) : (
        <p className="dica-exp">Soma as faixas com os volumes, mudos e solos que estão no mixer agora.</p>
      )}
      {variado && (
        <label className="exp-faixa on" style={{ marginTop: 8 }}>
          <input type="checkbox" checked={comVariacao} onChange={(e) => setComVariacao(e.target.checked)} />
          na velocidade {Math.round(mixer.velocidade * 100)}% e tom {mixer.semitons > 0 ? '+' : ''}{mixer.semitons} atuais
        </label>
      )}
      <div className="aba-linha" style={{ marginTop: 12, alignItems: 'center' }}>
        <button className="btn btn-primario" onClick={baixar} disabled={trabalhando}>
          <LuDownload size={14} /> {trabalhando ? 'preparando…' : 'exportar'}
        </button>
        {msg && <span className={`painel-sub${msg.startsWith('erro') ? ' erro-txt' : ''}`}>{msg}</span>}
      </div>
    </section>
  )
}
