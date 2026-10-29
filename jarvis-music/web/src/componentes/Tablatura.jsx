import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  LuGuitar, LuDownload, LuRotateCcw, LuPencil, LuUndo2, LuSave, LuTrash2, LuX, LuVolume2, LuPlay, LuTarget,
} from 'react-icons/lu'
import Transporte from './Transporte'
import TabAoVivo from './TabAoVivo'
import TocarJunto from './TocarJunto'
import { midiDaCorda, nomeNota, tocarNota, useEspaco } from './comum'
import { tempoTexto } from '../mixer'

const TECNICAS = [['hammer-on', 'h'], ['pull-off', 'p'], ['slide', '/'], ['bend', 'b'], ['vibrato', '~']]

/** Tela da tablatura: visual que acompanha a música, texto, arquivos e o editor de notas. */
export default function Tablatura({ estado, id, mixer, comp, secoesPorCompasso }) {
  const tabs = estado?.tabs || {}
  const ids = Object.keys(tabs)
  const [escolhida, setFaixa] = useState(null)
  const faixa = escolhida && ids.includes(escolhida) ? escolhida : ids[0]
  const [papel, setPapel] = useState('completo')
  const [sens, setSens] = useState(0.5)
  const [refazendo, setRefazendo] = useState(false)
  const [erro, setErro] = useState('')
  const [locais, setLocais] = useState({})
  const [modo, setModo] = useState('visual')
  const [seguir, setSeguir] = useState(true)
  const [junto, setJunto] = useState(false)
  const [notasBar, setNotasBar] = useState(null)

  // ---------------------------------------------------------------- editor
  const [editando, setEditando] = useState(false)
  const [edicao, setEdicao] = useState(null)        // {faixa, notas, historico}
  const [sel, setSel] = useState(null)
  const [salvando, setSalvando] = useState(false)

  const tab = locais[faixa] || tabs[faixa]
  const afin = tab?.afinacao || 'E padrão'
  const base = useMemo(() => (tab?.notas || []).map((n, i) => ({ ...n, uid: i })), [tab])
  const todas = edicao && edicao.faixa === faixa ? edicao.notas : base
  const notas = useMemo(() => todas.filter((n) => papel === 'completo' || n.papel === papel), [todas, papel])
  const mudancas = edicao && edicao.faixa === faixa ? edicao.historico.length : 0
  const selNota = editando ? todas.find((n) => n.uid === sel) : null

  useEspaco(mixer)

  const aplicar = useCallback((fn) => {
    setEdicao((e) => {
      const atual = e && e.faixa === faixa ? e : { faixa, notas: base, historico: [] }
      const novas = fn(atual.notas)
      if (novas === atual.notas) return atual
      return { faixa, notas: novas, historico: [...atual.historico.slice(-80), atual.notas] }
    })
  }, [faixa, base])

  const mudarNota = useCallback((uid, fn) => aplicar((ns) => ns.map((n) => (n.uid === uid ? { ...fn(n), editada: true } : n))), [aplicar])

  const mudarCorda = useCallback((corda) => {
    if (!selNota) return
    const casa = selNota.midi - midiDaCorda(afin, corda)  // mesma nota, outra corda
    if (casa < 0 || casa > 24) return
    mudarNota(selNota.uid, (n) => ({ ...n, corda, casa }))
  }, [selNota, afin, mudarNota])

  const mudarCasa = useCallback((casa) => {
    if (!selNota) return
    casa = Math.max(0, Math.min(24, casa))
    const midi = midiDaCorda(afin, selNota.corda) + casa
    mudarNota(selNota.uid, (n) => ({ ...n, casa, midi, nota: nomeNota(midi) }))
  }, [selNota, afin, mudarNota])

  const alternarTecnica = (t) => selNota && mudarNota(selNota.uid, (n) => {
    const l = n.tecnicas || []
    return { ...n, tecnicas: l.includes(t) ? l.filter((x) => x !== t) : [...l.filter((x) => !x.startsWith('bend') || t !== 'bend'), t] }
  })

  const apagar = useCallback(() => {
    if (!selNota) return
    const ordem = [...todas].sort((a, b) => a.inicio - b.inicio)
    const i = ordem.findIndex((n) => n.uid === selNota.uid)
    aplicar((ns) => ns.filter((n) => n.uid !== selNota.uid))
    setSel(ordem[i + 1]?.uid ?? ordem[i - 1]?.uid ?? null)
  }, [selNota, todas, aplicar])

  const adicionar = useCallback(({ inicio, corda, passo }) => {
    const perto = todas.filter((n) => n.corda === corda).sort((a, b) => Math.abs(a.inicio - inicio) - Math.abs(b.inicio - inicio))[0]
    const casa = perto && Math.abs(perto.inicio - inicio) < 4 ? perto.casa : 0
    const midi = midiDaCorda(afin, corda) + casa
    const trecho = (tab?.trechos || []).find((x) => x.inicio <= inicio && inicio < x.fim)
    const uid = Math.max(-1, ...todas.map((n) => n.uid)) + 1
    aplicar((ns) => [...ns, {
      uid, inicio, fim: inicio + passo * 2, corda, casa, midi, nota: nomeNota(midi), tecnicas: [],
      papel: trecho?.papel || 'base', forca: 0.7, editada: true,
    }])
    setSel(uid)
    tocarNota(midi, 0.8)
  }, [todas, afin, tab, aplicar])

  const desfazer = useCallback(() => {
    setEdicao((e) => (e && e.historico.length ? { ...e, notas: e.historico[e.historico.length - 1], historico: e.historico.slice(0, -1) } : e))
  }, [])

  const descartar = () => { setEdicao(null); setSel(null) }

  const salvar = async () => {
    if (!edicao) return
    setSalvando(true); setErro('')
    try {
      const corpo = { notas: edicao.notas.map(({ uid, x, ...n }) => n) }  // eslint-disable-line no-unused-vars
      const r = await fetch(`/api/tab/${id}/${faixa}/notas`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo),
      })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || 'não consegui salvar')
      setLocais((l) => ({ ...l, [faixa]: j }))
      setEdicao(null)
    } catch (e) {
      setErro(e.message)
    } finally { setSalvando(false) }
  }

  // atalhos do editor
  const digitos = useRef({ txt: '', t: 0 })
  useEffect(() => {
    if (!editando) return
    const tecla = (e) => {
      const alvo = e.target
      if (alvo?.tagName === 'INPUT' || alvo?.tagName === 'TEXTAREA' || alvo?.tagName === 'SELECT') return
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); desfazer(); return }
      if (!selNota) return
      const ordem = [...notas].sort((a, b) => a.inicio - b.inicio || b.corda - a.corda)
      const i = ordem.findIndex((n) => n.uid === selNota.uid)
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault()
        const prox = ordem[i + (e.key === 'ArrowRight' ? 1 : -1)]
        if (prox) { setSel(prox.uid); tocarNota(prox.midi, 0.6) }
      } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        e.preventDefault()
        mudarCorda(selNota.corda + (e.key === 'ArrowUp' ? -1 : 1))
      } else if (e.key === '+' || e.key === '=' || e.key === 'PageUp') {
        e.preventDefault(); mudarCasa(selNota.casa + 1)
      } else if (e.key === '-' || e.key === 'PageDown') {
        e.preventDefault(); mudarCasa(selNota.casa - 1)
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault(); apagar()
      } else if (e.key === 'Escape') {
        setSel(null)
      } else if (e.key.toLowerCase() === 'n') {
        tocarNota(selNota.midi)
      } else if (/^[0-9]$/.test(e.key)) {
        // digitar a casa: "1" e depois "2" rápido = casa 12
        const agora = performance.now()
        const d = digitos.current
        d.txt = agora - d.t < 700 && d.txt.length < 2 ? d.txt + e.key : e.key
        d.t = agora
        const v = Number(d.txt)
        if (v <= 24) mudarCasa(v)
      }
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [editando, selNota, notas, mudarCorda, mudarCasa, apagar, desfazer])

  // ---------------------------------------------------------- refazer automático
  const refazer = async () => {
    if (mudancas && !window.confirm('Refazer a tablatura apaga as correções que ainda não foram salvas. Continuar?')) return
    setRefazendo(true); setErro('')
    try {
      const fd = new FormData()
      fd.append('sensibilidade', String(sens))
      const r = await fetch(`/api/tab/${id}/${faixa}`, { method: 'POST', body: fd })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || 'não consegui refazer a tablatura')
      setLocais((l) => ({ ...l, [faixa]: j }))
      setEdicao(null)
    } catch (e) {
      setErro(e.message)
    } finally { setRefazendo(false) }
  }

  const ouvirTrecho = () => {
    if (!selNota) return
    mixer.irPara(Math.max(0, selNota.inicio - 0.4))
    mixer.tocar()
    setTimeout(() => mixer.pausar(), (1.8 / (mixer.velocidade || 1)) * 1000)
  }

  if (!ids.length) return <div className="vazio">esta música não tem faixa de guitarra reconhecida</div>
  const antiga = tab && !tab.motor
  const rotulo = (f) => estado.faixas.find((x) => x.id === f)?.rotulo || f
  const compassos = comp.dados?.compassos || []

  return (
    <div className="linhas">
      <section className="painel">
        <div className="painel-cabeca">
          <h2 className="painel-titulo"><LuGuitar size={15} /> TABLATURA</h2>
          <span className="painel-sub">
            {tab?.afinacao ? `afinação ${tab.afinacao} · ${notas.length} notas` : ''}
            {tab?.editada ? ` · ${tab.n_editadas || 0} corrigidas à mão` : ''}
          </span>
        </div>
        <Transporte mixer={mixer} ritmo={estado.ritmo} compassos={compassos} />

        <div className="aba-linha" style={{ marginTop: 12 }}>
          {ids.map((f) => (
            <button key={f} className={`aba${faixa === f ? ' ativo' : ''}`}
              onClick={() => { setFaixa(f); setSel(null) }}>{rotulo(f)}</button>
          ))}
          <span className="aba-sep" />
          {['completo', 'base', 'solo'].map((p) => (
            <button key={p} className={`aba${papel === p ? ' ativo' : ''}`} onClick={() => setPapel(p)}>{p}</button>
          ))}
          <span className="aba-sep" />
          {['visual', 'texto'].map((m) => (
            <button key={m} className={`aba${modo === m ? ' ativo' : ''}`} onClick={() => setModo(m)}>{m}</button>
          ))}
          {modo === 'visual' && (
            <button className={`aba${seguir ? ' ativo' : ''}`} onClick={() => setSeguir((s) => !s)}>
              {seguir ? 'seguindo' : 'seguir'}
            </button>
          )}
          {modo === 'visual' && (
            <button className={`aba editar${editando ? ' ativo' : ''}`} onClick={() => { setEditando((v) => !v); setSel(null) }}>
              <LuPencil size={12} /> {editando ? 'editando' : 'corrigir notas'}
            </button>
          )}
          {modo === 'visual' && (
            <button className={`aba${junto ? ' ativo' : ''}`} onClick={() => { setJunto((v) => !v); setNotasBar(null) }}
              title="tocar junto: o programa ouve sua guitarra e dá nota por compasso">
              <LuTarget size={12} /> tocar junto
            </button>
          )}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="painel-sub">sensibilidade</span>
            <input type="range" min="0.2" max="0.8" step="0.05" value={sens}
              onChange={(e) => setSens(Number(e.target.value))} />
            <button className="btn btn-min" onClick={refazer} disabled={refazendo}>
              <LuRotateCcw size={13} /> {refazendo ? 'refazendo (uns 30 s)' : 'refazer'}
            </button>
          </div>
        </div>

        {antiga && (
          <p className="aviso">
            Esta tablatura foi feita com o motor antigo. Clique em <b>refazer</b> para gerar de novo com o
            transcritor novo (bem mais fiel).
          </p>
        )}
        {mixer.semitons > 0 && (
          <p className="tv-capo">O áudio está {mixer.semitons} {mixer.semitons === 1 ? 'semitom' : 'semitons'} acima: use capotraste na casa {mixer.semitons} e toque as mesmas formas da tab.</p>
        )}
        {mixer.semitons < 0 && (
          <p className="tv-capo">O áudio está {-mixer.semitons} {mixer.semitons === -1 ? 'semitom' : 'semitons'} abaixo: afine a guitarra {-mixer.semitons === 1 ? 'meio tom' : `${-mixer.semitons} semitons`} abaixo para tocar a tab como está.</p>
        )}
        {erro && <p className="aviso erro">{erro}</p>}

        {editando && (
          <div className="editor">
            {selNota ? (
              <>
                <div className="editor-grupo">
                  <span className="estudo-rotulo">nota</span>
                  <b className="editor-nota">{selNota.nota || nomeNota(selNota.midi)}</b>
                  <small>{tempoTexto(selNota.inicio)}</small>
                </div>
                <div className="editor-grupo" title="trocar de corda mantendo a mesma nota (↑ ↓)">
                  <span className="estudo-rotulo">corda</span>
                  {[1, 2, 3, 4, 5, 6].map((c) => {
                    const casa = selNota.midi - midiDaCorda(afin, c)
                    const ok = casa >= 0 && casa <= 24
                    return (
                      <button key={c} disabled={!ok} className={`chip-v${selNota.corda === c ? ' on' : ''}`}
                        onClick={() => mudarCorda(c)} title={ok ? `corda ${c}, casa ${casa}` : 'essa nota não existe nesta corda'}>
                        {c}{ok && selNota.corda !== c ? <sub>{casa}</sub> : null}
                      </button>
                    )
                  })}
                </div>
                <div className="editor-grupo" title="casa (+ / − ou digite o número)">
                  <span className="estudo-rotulo">casa</span>
                  <button className="ctrl mini" onClick={() => mudarCasa(selNota.casa - 1)}>−</button>
                  <input className="editor-casa" type="number" min="0" max="24" value={selNota.casa}
                    onChange={(e) => mudarCasa(Number(e.target.value) || 0)} />
                  <button className="ctrl mini" onClick={() => mudarCasa(selNota.casa + 1)}>+</button>
                </div>
                <div className="editor-grupo">
                  {TECNICAS.map(([t, s]) => {
                    const on = (selNota.tecnicas || []).some((x) => x === t || (t === 'bend' && x.startsWith('bend')))
                    return <button key={t} className={`chip-v${on ? ' on' : ''}`} onClick={() => alternarTecnica(t)} title={t}>{s} {t}</button>
                  })}
                </div>
                <div className="editor-grupo">
                  {['base', 'solo'].map((p) => (
                    <button key={p} className={`chip-v${selNota.papel === p ? ' on' : ''}`}
                      onClick={() => mudarNota(selNota.uid, (n) => ({ ...n, papel: p }))}>{p}</button>
                  ))}
                </div>
                <div className="editor-grupo">
                  <button className="chip-v" onClick={() => tocarNota(selNota.midi)} title="ouvir a nota (N)"><LuVolume2 size={12} /> nota</button>
                  <button className="chip-v" onClick={ouvirTrecho} title="ouvir a música nesse ponto"><LuPlay size={12} /> trecho</button>
                  <button className="chip-v perigo" onClick={apagar} title="apagar (Delete)"><LuTrash2 size={12} /> apagar</button>
                </div>
              </>
            ) : (
              <span className="editor-dica">
                Clique numa nota para corrigir, ou num espaço vazio da corda para criar uma nota.
                Atalhos: ← → nota anterior/próxima · ↑ ↓ mesma nota em outra corda · + − ou números para a casa ·
                Delete apaga · N ouve · Ctrl+Z desfaz.
              </span>
            )}
            <div className="editor-acoes">
              <button className="btn btn-min" onClick={desfazer} disabled={!mudancas}><LuUndo2 size={13} /> desfazer</button>
              <button className="btn btn-min" onClick={descartar} disabled={!mudancas}><LuX size={13} /> descartar</button>
              <button className="btn btn-min btn-primario" onClick={salvar} disabled={!mudancas || salvando}>
                <LuSave size={13} /> {salvando ? 'salvando…' : `salvar${mudancas ? ` (${mudancas})` : ''}`}
              </button>
            </div>
          </div>
        )}

        {junto && modo === 'visual' && <TocarJunto notas={notas} compassos={compassos} mixer={mixer} aoNotas={setNotasBar} />}

        {modo === 'visual' && compassos.length > 0
          ? <TabAoVivo notas={notas} compassos={compassos} mixer={mixer} seguir={seguir}
              editando={editando} selecionada={sel} aoSelecionar={(u) => { setSel(u); const n = todas.find((x) => x.uid === u); if (n) tocarNota(n.midi, 0.7) }}
              aoAdicionar={adicionar} secoes={secoesPorCompasso} notasBar={junto ? notasBar : null} />
          : <pre className="tab-texto">{tab?.ascii?.[papel] || '(sem notas)'}</pre>}

        {tab?.arquivos && (
          <div className="aba-linha" style={{ marginTop: 12 }}>
            {Object.entries(tab.arquivos)
              .filter(([k]) => k.startsWith(papel))
              .map(([k, nome]) => (
                <a key={k} className="btn btn-min" href={`/api/arquivo/${id}/${nome}`} download>
                  <LuDownload size={13} /> {k.split('_').pop()}
                </a>
              ))}
            {mudancas > 0 && <span className="painel-sub">salve as correções para atualizar os arquivos</span>}
          </div>
        )}
        <p className="aviso">
          Transcrição automática: confira de ouvido e corrija aqui mesmo em "corrigir notas". As correções
          vão junto para o Guitar Pro, MusicXML e MIDI.
        </p>
      </section>
    </div>
  )
}
