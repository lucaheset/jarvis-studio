import { useEffect, useMemo, useState } from 'react'
import { LuLibrary, LuSearch, LuPencil, LuTrash2, LuCheck, LuX, LuPlay, LuLink } from 'react-icons/lu'
import { tempoTexto } from '../mixer'

/** Biblioteca: todas as músicas já analisadas, para abrir sem processar de novo. */
export default function Biblioteca({ aoAbrir, atual, recarregarSinal }) {
  const [itens, setItens] = useState(null)
  const [busca, setBusca] = useState('')
  const [ordem, setOrdem] = useState('recentes')
  const [editando, setEditando] = useState(null)
  const [nomeNovo, setNomeNovo] = useState('')
  const [apagando, setApagando] = useState(null)
  const [erro, setErro] = useState('')

  const carregar = () => fetch('/api/biblioteca').then((r) => r.json()).then(setItens).catch(() => setItens([]))
  useEffect(() => { carregar() }, [recarregarSinal])

  const lista = useMemo(() => {
    const q = busca.trim().toLowerCase()
    let l = (itens || []).filter((i) => !q || [i.arquivo, i.tom, i.link].some((x) => (x || '').toLowerCase().includes(q)))
    if (ordem === 'nome') l = [...l].sort((a, b) => (a.arquivo || '').localeCompare(b.arquivo || ''))
    if (ordem === 'bpm') l = [...l].sort((a, b) => (a.bpm || 0) - (b.bpm || 0))
    return l
  }, [itens, busca, ordem])

  const renomear = async (id) => {
    const fd = new FormData()
    fd.append('nome', nomeNovo)
    const r = await fetch(`/api/renomear/${id}`, { method: 'POST', body: fd })
    if (!r.ok) setErro((await r.json()).detail || 'não consegui renomear')
    setEditando(null)
    carregar()
  }

  const apagar = async (id) => {
    const r = await fetch(`/api/analise/${id}`, { method: 'DELETE' })
    if (!r.ok) setErro((await r.json()).detail || 'não consegui apagar')
    setApagando(null)
    carregar()
  }

  if (itens === null) return <div className="vazio">carregando a biblioteca…</div>

  return (
    <section className="painel">
      <div className="painel-cabeca">
        <h2 className="painel-titulo"><LuLibrary size={15} /> BIBLIOTECA</h2>
        <span className="painel-sub">{itens.length} músicas · abre na hora, sem processar de novo</span>
      </div>

      <div className="bib-barra">
        <label className="bib-busca">
          <LuSearch size={14} />
          <input placeholder="buscar por nome, tom ou link" value={busca} onChange={(e) => setBusca(e.target.value)} />
        </label>
        {['recentes', 'nome', 'bpm'].map((o) => (
          <button key={o} className={`aba${ordem === o ? ' ativo' : ''}`} onClick={() => setOrdem(o)}>{o}</button>
        ))}
      </div>
      {erro && <p className="aviso erro">{erro}</p>}
      {!lista.length && <div className="vazio">{itens.length ? 'nada encontrado' : 'nada analisado ainda'}</div>}

      <div className="bib-grade">
        {lista.map((i) => {
          const pronto = i.concluido
          return (
            <div key={i.id} className={`bib-card${i.id === atual ? ' atual' : ''}${i.erro ? ' falhou' : ''}`}>
              {editando === i.id ? (
                <div className="bib-editar">
                  <input autoFocus value={nomeNovo} onChange={(e) => setNomeNovo(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') renomear(i.id); if (e.key === 'Escape') setEditando(null) }} />
                  <button className="ctrl mini" onClick={() => renomear(i.id)} title="salvar"><LuCheck size={12} /></button>
                  <button className="ctrl mini" onClick={() => setEditando(null)} title="cancelar"><LuX size={12} /></button>
                </div>
              ) : (
                <h3 title={i.arquivo}>{i.arquivo}</h3>
              )}
              <div className="bib-dados">
                {pronto ? (
                  <>
                    <span>{tempoTexto(i.duracao)}</span>
                    {i.bpm ? <span>{i.bpm} BPM</span> : null}
                    {i.tom ? <span>{i.tom}</span> : null}
                    {i.compasso ? <span>{i.compasso}</span> : null}
                    <span>{i.faixas} faixas</span>
                  </>
                ) : i.erro ? <span className="erro">falhou</span> : <span>{i.progresso}% · {i.etapa}</span>}
              </div>
              <div className="bib-pe">
                <small>
                  {i.criado ? new Date(i.criado * 1000).toLocaleDateString('pt-BR') : ''}
                  {i.link && <a href={i.link} target="_blank" rel="noreferrer" title={i.link}> <LuLink size={11} /></a>}
                </small>
                {apagando === i.id ? (
                  <span className="bib-confirma">
                    apagar tudo desta música?
                    <button className="btn btn-min btn-perigo" onClick={() => apagar(i.id)}>apagar</button>
                    <button className="btn btn-min" onClick={() => setApagando(null)}>não</button>
                  </span>
                ) : (
                  <span className="bib-acoes">
                    <button className="ctrl mini" title="renomear" onClick={() => { setEditando(i.id); setNomeNovo(i.arquivo || '') }}>
                      <LuPencil size={12} />
                    </button>
                    <button className="ctrl mini" title="apagar" disabled={!pronto && !i.erro} onClick={() => setApagando(i.id)}>
                      <LuTrash2 size={12} />
                    </button>
                    <button className="btn btn-min btn-primario" onClick={() => aoAbrir(i.id)}>
                      <LuPlay size={12} /> {i.id === atual ? 'aberta' : 'abrir'}
                    </button>
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
