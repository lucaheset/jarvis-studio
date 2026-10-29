import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  LuHouse, LuSlidersHorizontal, LuGuitar, LuActivity, LuLibrary, LuMic,
  LuUpload, LuDownload, LuRotateCcw, LuSparkles, LuFileMusic, LuLink, LuMusic, LuWandSparkles,
} from 'react-icons/lu'
import Fundo from './componentes/Fundo'
import Orbe from './componentes/Orbe'
import Boot from './componentes/Boot'
import Faixa from './componentes/Faixa'
import Transporte from './componentes/Transporte'
import CifraAoVivo from './componentes/CifraAoVivo'
import Tablatura from './componentes/Tablatura'
import { useEspaco } from './componentes/comum'
import { usarCompassos } from './componentes/usarCompassos'
import Afinador from './componentes/Afinador'
import Biblioteca from './componentes/Biblioteca'
import Exportar from './componentes/Exportar'
import Gerar from './componentes/Gerar'
import BarraSecoes, { usarSecoes } from './componentes/Secoes'
import { useMixer, tempoTexto } from './mixer'
import './estilos.css'

const SECOES = [
  { id: 'inicio', rotulo: 'Início', Icone: LuHouse },
  { id: 'faixas', rotulo: 'Faixas', Icone: LuSlidersHorizontal },
  { id: 'cifra', rotulo: 'Cifra', Icone: LuMusic },
  { id: 'tablatura', rotulo: 'Tablatura', Icone: LuGuitar },
  { id: 'analise', rotulo: 'Análise', Icone: LuActivity },
  { id: 'afinador', rotulo: 'Afinador', Icone: LuMic },
  { id: 'gerar', rotulo: 'Gerar', Icone: LuWandSparkles },
  { id: 'biblioteca', rotulo: 'Biblioteca', Icone: LuLibrary },
]

export default function App() {
  const [booting, setBooting] = useState(true)
  const [secao, setSecao] = useState('inicio')
  const [saude, setSaude] = useState(null)
  const [id, setId] = useState(null)
  const [estado, setEstado] = useState(null)
  const [sinalBiblioteca, setSinalBiblioteca] = useState(0)
  const entrada = useRef(null)

  const faixas = estado?.faixas || []
  const comp = usarCompassos(estado?.concluido ? estado : null, id)
  const mixer = useMixer(estado?.concluido ? faixas : null,
    { id, compassos: comp.dados?.compassos, ritmo: estado?.ritmo })
  const partes = usarSecoes(estado, id, comp)

  useEffect(() => {
    fetch('/api/saude').then((r) => r.json()).then(setSaude).catch(() => setSaude({ ok: false }))
  }, [])

  // acompanha a análise em andamento
  useEffect(() => {
    if (!id) return
    let vivo = true
    const puxar = async () => {
      try {
        const e = await (await fetch(`/api/estado/${id}`)).json()
        if (!vivo) return
        setEstado(e)
        if (!e.concluido && !e.erro) setTimeout(puxar, 1200)
        else {
          if (e.concluido) setSecao((s) => (s === 'inicio' ? 'faixas' : s))
          setSinalBiblioteca((x) => x + 1)
        }
      } catch {
        if (vivo) setTimeout(puxar, 2500)
      }
    }
    puxar()
    return () => { vivo = false }
  }, [id])

  const enviar = useCallback(async (arquivo) => {
    if (!arquivo) return
    const fd = new FormData()
    fd.append('arquivo', arquivo)
    setEstado(null)
    setSecao('inicio')
    const r = await fetch('/api/analisar', { method: 'POST', body: fd })
    const j = await r.json()
    setId(j.id)
  }, [])

  const enviarLink = useCallback(async (url) => {
    const fd = new FormData()
    fd.append('url', url)
    const r = await fetch('/api/analisar_link', { method: 'POST', body: fd })
    const j = await r.json()
    if (!r.ok) throw new Error(j.detail || 'não consegui usar esse link')
    setEstado(null)
    setSecao('inicio')
    setId(j.id)
  }, [])

  // música gerada no Suno: acompanha a análise na tela inicial, como um envio
  const analisarGerada = useCallback((novo) => {
    setEstado(null)
    setSecao('inicio')
    setId(novo)
  }, [])

  const abrir = useCallback((outro) => {
    setId(outro)
    setSecao('faixas')
  }, [])

  const trabalhando = !!(estado && !estado.concluido && !estado.erro)
  const estadoOrbe = trabalhando ? 'pensando' : mixer.tocando ? 'tocando' : 'parado'

  return (
    <>
      <Fundo />
      {booting && <Boot aoFechar={() => setBooting(false)} />}
      <div className="app">
        <nav className="sidebar">
          {SECOES.map(({ id: s, rotulo, Icone }) => {
            const travado = !['inicio', 'biblioteca', 'afinador', 'gerar'].includes(s) && !estado?.concluido
            return (
              <button key={s} className={`nav-item${secao === s ? ' ativo' : ''}`}
                disabled={travado} onClick={() => setSecao(s)}>
                <Icone className="nav-icone" />
                <span className="rotulo">{rotulo}</span>
                {s === 'faixas' && faixas.length > 0 && <span className="nav-contador">{faixas.length}</span>}
              </button>
            )
          })}
          <div className="sidebar-pe">
            {saude?.gpu && <div>GPU: {saude.gpu}</div>}
            {saude?.separador && <div>{saude.separador}</div>}
          </div>
        </nav>

        <div className="principal">
          <header className="topo">
            <div className="marca">
              <div>
                <h1 className="marca-nome">JARVIS <span>MUSIC</span></h1>
                <p className="marca-sub">SEU ESTÚDIO INTELIGENTE</p>
              </div>
              <ul className="marca-lema">
                <li>SEPARAR</li><li>TRANSCREVER</li><li>ESTUDAR</li>
              </ul>
            </div>
            <div className="topo-centro">
              {estado?.arquivo ? estado.arquivo : 'envie uma música para começar'}
              {estado?.etapa && !estado.concluido ? ` · ${estado.etapa}` : ''}
            </div>
            <div className="topo-direita">
              <span className={`status-ponto ${saude?.separador ? 'ok' : 'off'}`}>
                <i /> separador
              </span>
              <span className={`status-ponto ${saude?.gpu && !/CPU|não/.test(saude.gpu) ? 'ok' : 'off'}`}>
                <i /> gpu
              </span>
              <button className="btn btn-min" onClick={() => entrada.current?.click()}>
                <LuUpload size={13} /> nova música
              </button>
            </div>
          </header>

          <input ref={entrada} type="file" accept="audio/*,.mp3,.wav,.flac,.m4a,.ogg"
            style={{ display: 'none' }} onChange={(e) => enviar(e.target.files?.[0])} />

          <div className="conteudo">
            {estado?.concluido && ['faixas', 'cifra', 'tablatura'].includes(secao) && (
              <BarraSecoes dados={partes} mixer={mixer} />
            )}
            {secao === 'inicio' && (
              <Inicio estado={estado} estadoOrbe={estadoOrbe} nivel={mixer.nivel}
                aoEscolher={enviar} aoLink={enviarLink} aoClicar={() => entrada.current?.click()} />
            )}
            {secao === 'faixas' && <Faixas estado={estado} id={id} mixer={mixer} comp={comp} aoAtualizar={setEstado} />}
            {secao === 'cifra' && <Cifra estado={estado} mixer={mixer} comp={comp} />}
            {secao === 'tablatura' && <Tablatura estado={estado} id={id} mixer={mixer} comp={comp} secoesPorCompasso={partes.porCompasso} />}
            {secao === 'analise' && <Analise estado={estado} posicao={mixer.posicao} />}
            {secao === 'biblioteca' && <Biblioteca aoAbrir={abrir} atual={id} recarregarSinal={sinalBiblioteca} />}
            {secao === 'afinador' && <Afinador />}
            {secao === 'gerar' && <Gerar aoAnalisar={analisarGerada} />}
          </div>
        </div>
      </div>
    </>
  )
}

/* -------------------------------------------------------------------- início */
function Inicio({ estado, estadoOrbe, nivel, aoEscolher, aoLink, aoClicar }) {
  const [sobre, setSobre] = useState(false)
  const trabalhando = !!(estado && !estado.concluido && !estado.erro)

  // soltar um link (arrastado do navegador) também funciona
  const soltar = (e) => {
    e.preventDefault()
    setSobre(false)
    const arquivo = e.dataTransfer.files?.[0]
    if (arquivo) return aoEscolher(arquivo)
    const texto = (e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain') || '').trim()
    if (/^https?:\/\//i.test(texto)) aoLink(texto.split(/\s+/)[0]).catch(() => {})
  }

  return (
    <div className="enviar">
      <Orbe estado={estadoOrbe} nivel={nivel} />

      {!trabalhando && <CampoLink aoLink={aoLink} />}

      {!estado && (
        <div className={`solta${sobre ? ' sobre' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setSobre(true) }}
          onDragLeave={() => setSobre(false)}
          onDrop={soltar}>
          <h2>ENVIE UMA MÚSICA</h2>
          <p>arraste o arquivo (ou um link) aqui, ou escolha no computador · mp3, wav, flac, m4a</p>
          <button className="btn btn-primario" onClick={aoClicar}>
            <LuUpload size={15} /> escolher arquivo
          </button>
        </div>
      )}

      {trabalhando && (
        <div className="andamento painel">
          <div className="painel-cabeca">
            <h2 className="painel-titulo"><LuSparkles size={15} /> ANALISANDO</h2>
            <span className="painel-sub">{estado.progresso}%</span>
          </div>
          <div className="andamento-barra"><i style={{ width: `${estado.progresso}%` }} /></div>
          <div className="andamento-etapa">{estado.etapa}</div>
          <div className="registro">
            {(estado.registro || []).slice(-9).map((l, i) => <div key={i}>{l.texto}</div>)}
          </div>
        </div>
      )}

      {estado?.erro && (
        <div className="andamento painel">
          <h2 className="painel-titulo">FALHOU</h2>
          <p className="aviso erro">{estado.erro}</p>
          <button className="btn" onClick={aoClicar}>tentar outra música</button>
        </div>
      )}

      {estado?.concluido && (
        <div className="andamento painel">
          <h2 className="painel-titulo">PRONTO</h2>
          <p style={{ color: 'var(--texto-2)' }}>
            {estado.faixas.length} faixas · {tempoTexto(estado.duracao)} ·{' '}
            {estado.ritmo?.bpm} BPM · {estado.tom?.tom}
          </p>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------- link do YouTube */
function CampoLink({ aoLink }) {
  const [url, setUrl] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')

  const mandar = async (e) => {
    e.preventDefault()
    const limpo = url.trim()
    if (!limpo) return
    setEnviando(true)
    setErro('')
    try {
      await aoLink(limpo)
      setUrl('')
    } catch (err) {
      setErro(err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form className="link-caixa" onSubmit={mandar}>
      <div className="link-linha">
        <LuLink className="link-icone" />
        <input type="url" placeholder="cole o link do YouTube aqui" value={url}
          onChange={(e) => setUrl(e.target.value)} disabled={enviando} />
        <button className="btn btn-primario" type="submit" disabled={enviando || !url.trim()}>
          <LuDownload size={14} /> {enviando ? 'enviando' : 'baixar e analisar'}
        </button>
      </div>
      {erro && <p className="aviso erro">{erro}</p>}
    </form>
  )
}

/* -------------------------------------------------------------------- faixas */

function Cifra({ estado, mixer, comp }) {
  useEspaco(mixer)
  if (!estado?.concluido) return <div className="vazio">nenhuma música analisada ainda</div>
  return <CifraAoVivo estado={estado} mixer={mixer} comp={comp} />
}

function Faixas({ estado, id, mixer, comp, aoAtualizar }) {
  useEspaco(mixer)
  if (!estado?.concluido) return <div className="vazio">nenhuma música analisada ainda</div>
  const guitarras = estado.faixas.filter((f) => f.e_guitarra && f.derivada_de)
  return (
    <div className="linhas">
      <section className="painel">
        <div className="painel-cabeca">
          <h2 className="painel-titulo"><LuSlidersHorizontal size={15} /> MIXER</h2>
          <span className="painel-sub">
            {mixer.carregando ? `carregando ${mixer.prontas.length}/${estado.faixas.length}` : 'tudo carregado'}
          </span>
        </div>
        <Transporte mixer={mixer} ritmo={estado.ritmo} compassos={comp.dados?.compassos} />
        <div className="mixer" style={{ marginTop: 14 }}>
          {estado.faixas.filter((f) => !f.derivada_de).map((f) => (
            <Faixa key={f.id} faixa={f} mixer={mixer} pronta={mixer.prontas.includes(f.id)} />
          ))}
        </div>
      </section>

      <GuitarrasDerivadas estado={estado} id={id} mixer={mixer} guitarras={guitarras} aoAtualizar={aoAtualizar} />
      <Exportar id={id} estado={estado} mixer={mixer} />
    </div>
  )
}

/** Guitarras tiradas da faixa de guitarra: por panorama (L/C/R) ou por notas (base/solo). */
function GuitarrasDerivadas({ estado, id, mixer, guitarras, aoAtualizar }) {
  const [rodando, setRodando] = useState(false)
  const [aviso, setAviso] = useState('')
  const porNotas = guitarras.some((f) => f.metodo === 'notas')
  const temGuitarra = estado.faixas.some((f) => f.id === 'guitarra') && estado.tabs?.guitarra?.notas?.length
  const motivo = estado.base_solo && !estado.base_solo.ok ? estado.base_solo.motivo : ''

  const separar = async () => {
    setRodando(true); setAviso('')
    try {
      const r = await fetch(`/api/base_solo/${id}`, { method: 'POST' })
      const j = await r.json()
      if (!r.ok) {
        throw new Error(r.status === 404 || r.status === 405
          ? 'feche e abra o iniciar.bat de novo para ativar esta função' : j.detail || 'não consegui separar')
      }
      if (j.base_solo && !j.base_solo.ok) setAviso(j.base_solo.motivo)
      aoAtualizar(j)
    } catch (e) {
      setAviso(e.message)
    } finally { setRodando(false) }
  }

  if (!guitarras.length && !temGuitarra) return null
  return (
    <section className="painel">
      <div className="painel-cabeca">
        <h2 className="painel-titulo"><LuGuitar size={15} /> {porNotas ? 'GUITARRA BASE E SOLO' : 'GUITARRAS POR POSIÇÃO'}</h2>
        <span className="painel-sub">
          {porNotas ? 'separadas pelas notas da tablatura' : guitarras.length ? 'separadas pelo panorama do estéreo' : ''}
        </span>
        {!guitarras.length && (
          <button className="btn btn-min" style={{ marginLeft: 'auto' }} onClick={separar} disabled={rodando}>
            <LuSparkles size={13} /> {rodando ? 'separando (uns 30 s)…' : 'separar base e solo'}
          </button>
        )}
      </div>
      {guitarras.length > 0 && (
        <div className="mixer">
          {guitarras.map((f) => (
            <Faixa key={f.id} faixa={f} mixer={mixer} pronta={mixer.prontas.includes(f.id)} />
          ))}
        </div>
      )}
      {!guitarras.length && (
        <p className="aviso">
          {aviso || motivo || 'As guitarras desta música estão juntas no centro do estéreo, então não deu para separar por posição. ' +
            'Clique em "separar base e solo" para separar pelas notas da tablatura (acordes vão para a base, a linha de cima para o solo).'}
        </p>
      )}
      {guitarras.length > 0 && (
        <p className="aviso">
          {porNotas
            ? 'Separação pelas notas: fica limpa onde as partes tocam em regiões diferentes do braço; onde tocam a mesma nota juntas, uma vaza na outra.'
            : 'A base costuma estar gravada dobrada nos lados e o solo no centro. Essa divisão é uma aproximação: compare as faixas de ouvido antes de confiar nela.'}
        </p>
      )}
    </section>
  )
}

/* ----------------------------------------------------------------- tablatura */
/* -------------------------------------------------------------------- análise */
function Analise({ estado, posicao }) {
  if (!estado?.concluido) return <div className="vazio">nenhuma música analisada ainda</div>
  const { ritmo, tom, cifra = [], efeitos = {} } = estado
  const atual = cifra.find((c) => posicao >= c.inicio && posicao < c.fim)

  return (
    <div className="linhas">
      <div className="duas">
        <section className="painel">
          <div className="painel-cabeca"><h2 className="painel-titulo"><LuActivity size={15} /> MÚSICA</h2></div>
          <div className="grade-info">
            <div className="cartao">
              <h3>bpm</h3>
              <div className="valor">{ritmo?.bpm || '--'}</div>
              <div className="nota">{ritmo?.compasso || '4/4 (suposto)'} · {ritmo?.motor}</div>
            </div>
            <div className="cartao">
              <h3>tom</h3>
              <div className="valor">{tom?.tom || '--'}</div>
              <div className="nota">relativa: {tom?.relativa} · outras: {(tom?.alternativas || []).join(', ')}</div>
              <div className="medidor" style={{ marginTop: 8 }}>
                <div><i style={{ width: `${(tom?.confianca || 0) * 100}%` }} /></div>
              </div>
            </div>
            <div className="cartao">
              <h3>duração</h3>
              <div className="valor">{tempoTexto(estado.duracao)}</div>
              <div className="nota">{estado.faixas.length} faixas separadas</div>
            </div>
          </div>
        </section>

        <section className="painel">
          <div className="painel-cabeca">
            <h2 className="painel-titulo"><LuFileMusic size={15} /> CIFRA</h2>
            <span className="painel-sub">por compasso</span>
          </div>
          <div className="cifra">
            {cifra.length === 0 && <span style={{ color: 'var(--texto-3)' }}>não foi possível tirar a cifra</span>}
            {cifra.map((c, i) => (
              <span key={i} className={atual === c ? 'agora' : ''}>{c.acorde}</span>
            ))}
          </div>
        </section>
      </div>

      {Object.entries(efeitos).map(([faixa, info]) => (
        <section className="painel" key={faixa}>
          <div className="painel-cabeca">
            <h2 className="painel-titulo">EFEITOS · {estado.faixas.find((f) => f.id === faixa)?.rotulo || faixa}</h2>
          </div>
          {(info.efeitos || []).map((e, i) => (
            <div className="efeito-linha" key={i}>
              <span className="efeito-nome">{e.efeito}</span>
              <div className="medidor" style={{ width: 120 }}>
                <div><i style={{ width: `${e.confianca * 100}%` }} /></div>
              </div>
              <span style={{ color: 'var(--ciano-claro)', fontSize: 12, minWidth: 34 }}>
                {Math.round(e.confianca * 100)}%
              </span>
              <span className="efeito-como">{e.como}</span>
            </div>
          ))}
          <p className="aviso">{info.aviso}</p>
        </section>
      ))}
    </div>
  )
}

