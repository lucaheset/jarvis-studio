import { useEffect, useMemo, useState } from 'react'
import { LuRepeat } from 'react-icons/lu'
import { indiceEm } from './usarCompassos'

/** Partes da música (intro, verso, refrão...). Análises antigas não têm:
 *  pede ao servidor uma vez. */
export function usarSecoes(estado, id, comp) {
  const salvas = estado?.secoes
  const [secoes, setSecoes] = useState(salvas || null)
  const [erro, setErro] = useState('')
  const temCompassos = !!comp?.dados?.compassos?.length

  useEffect(() => {
    if (!estado?.concluido || !id) { setSecoes(null); setErro(''); return }
    if (salvas?.lista?.length) { setSecoes(salvas); return }
    if (!temCompassos) return
    let vivo = true
    setSecoes(null); setErro('')
    fetch(`/api/secoes/${id}`, { method: 'POST' })
      .then(async (r) => {
        const j = await r.json().catch(() => ({}))
        if (!r.ok) {
          throw new Error(r.status === 404 || r.status === 405
            ? 'feche e abra o iniciar.bat de novo para ativar as partes da música'
            : j.detail || 'não consegui achar as partes da música')
        }
        if (vivo) setSecoes(j)
      })
      .catch((e) => vivo && setErro(e.message))
    return () => { vivo = false }
  }, [id, estado?.concluido, salvas, temCompassos])

  // parte que começa em cada compasso (para marcar na tab)
  const porCompasso = useMemo(() => {
    const m = {}
    for (const s of secoes?.lista || []) m[s.k_ini] = s
    return m
  }, [secoes])

  const renomear = async (i, nome) => {
    const lista = secoes.lista.map((s, k) => (k === i ? { ...s, nome } : s))
    setSecoes({ ...secoes, lista })
    try {
      const r = await fetch(`/api/secoes/${id}/nomes`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nomes: lista.map((s) => s.nome) }),
      })
      if (r.ok) setSecoes(await r.json())
    } catch { /* o nome fica só na tela até a próxima vez */ }
  }

  return { secoes, porCompasso, erro, renomear }
}

/** Faixa colorida com as partes: clique pula, ⟲ repete a parte, duplo clique renomeia. */
export default function BarraSecoes({ dados, mixer }) {
  const { secoes, erro, renomear } = dados
  const [editando, setEditando] = useState(null)
  const lista = secoes?.lista || []
  if (erro) return <p className="aviso">{erro}</p>
  if (!lista.length) return secoes ? null : <div className="secoes carregando">procurando as partes da música…</div>

  const total = lista[lista.length - 1].fim - lista[0].inicio || 1
  const atual = indiceEm(lista, mixer.posicao)
  const { a, b } = mixer.loop

  return (
    <div className="secoes" title={secoes.motor ? `partes por ${secoes.motor}` : ''}>
      {lista.map((s, i) => {
        const emLoop = a !== null && b !== null && Math.abs(a - s.inicio) < 0.05 && Math.abs(b - s.fim) < 0.05
        return (
          <div key={i} className={`secao sec-${s.cor}${i === atual ? ' atual' : ''}${emLoop ? ' loop' : ''}`}
            style={{ flexGrow: Math.max(0.01, (s.fim - s.inicio) / total) }}
            onClick={() => mixer.irPara(s.inicio)}
            onDoubleClick={() => setEditando(i)}
            title={`${s.nome} · compassos ${s.k_ini + 1}–${s.k_fim} · clique para ir, duplo clique para renomear`}>
            {editando === i ? (
              <input autoFocus defaultValue={s.nome} maxLength={40}
                onClick={(e) => e.stopPropagation()}
                onBlur={(e) => { setEditando(null); if (e.target.value.trim() && e.target.value !== s.nome) renomear(i, e.target.value.trim()) }}
                onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur(); if (e.key === 'Escape') setEditando(null) }} />
            ) : <span>{s.nome}</span>}
            <button className="secao-loop" title="repetir esta parte (loop A-B)"
              onClick={(e) => {
                e.stopPropagation()
                if (emLoop) mixer.limparLoop()
                else { mixer.definirLoop(s.inicio, s.fim); mixer.irPara(s.inicio) }
              }}>
              <LuRepeat size={10} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
