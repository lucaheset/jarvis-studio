import { useCallback, useEffect, useState } from 'react'
import { LuWandSparkles, LuExternalLink, LuRefreshCw, LuActivity, LuTriangleAlert } from 'react-icons/lu'
import { tempoTexto } from '../mixer'

const STATUS = {
  submitted: 'na fila do Suno', queued: 'na fila do Suno', streaming: 'compondo',
  complete: 'pronta', error: 'falhou',
}
const PEDIDO = {
  preparando: 'preparando', enviado: 'enviado ao Suno', gerando: 'compondo no Suno', pronto: 'pronto',
  manual: 'termine na janela do Suno', precisa_login: 'entre na conta', erro: 'falhou',
}

/** Gerar músicas com a conta do Suno do usuário e abrir na análise do app. */
export default function Gerar({ aoAnalisar }) {
  const [info, setInfo] = useState(null)
  const [abrindo, setAbrindo] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')
  const [personalizado, setPersonalizado] = useState(false)
  const [form, setForm] = useState({ descricao: '', letra: '', estilo: '', titulo: '', instrumental: false })

  const puxar = useCallback(() => fetch('/api/suno').then((r) => r.json()).then(setInfo).catch(() => {}), [])

  // enquanto há música sendo feita, acompanha mais de perto
  const fazendo = (info?.clips || []).some((c) => !['complete', 'error'].includes(c.status)) ||
    (info?.pedidos || []).some((p) => ['enviado', 'manual'].includes(p.status))
  useEffect(() => {
    puxar()
    const t = setInterval(puxar, fazendo ? 4000 : 15000)
    return () => clearInterval(t)
  }, [puxar, fazendo])

  const abrir = async () => {
    setAbrindo(true)
    setErro('')
    try {
      const r = await fetch('/api/suno/abrir', { method: 'POST' })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || 'não consegui abrir o Suno')
      setInfo(j)
    } catch (e) {
      setErro(e.message)
    } finally {
      setAbrindo(false)
    }
  }

  const gerar = async (e) => {
    e.preventDefault()
    setEnviando(true)
    setErro('')
    const corpo = personalizado
      ? { letra: form.letra, estilo: form.estilo, titulo: form.titulo, instrumental: form.instrumental }
      : { descricao: form.descricao, instrumental: form.instrumental }
    try {
      const r = await fetch('/api/suno/gerar', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo),
      })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || 'não consegui pedir a música')
      puxar()
    } catch (err) {
      setErro(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const analisar = async (clip) => {
    setErro('')
    const r = await fetch(`/api/suno/analisar/${clip}`, { method: 'POST' })
    const j = await r.json()
    if (!r.ok) return setErro(j.detail || 'não consegui abrir essa música')
    aoAnalisar(j.id)
  }

  const muda = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  const conectado = info?.janela && info?.logado
  const podeGerar = personalizado ? (form.letra.trim() || form.estilo.trim()) : form.descricao.trim()

  return (
    <div className="linhas">
      <section className="painel">
        <div className="painel-cabeca">
          <h2 className="painel-titulo"><LuWandSparkles size={15} /> GERAR NO SUNO</h2>
          <span className="painel-sub">
            {!info ? 'verificando' : !info.janela ? 'Suno desligado'
              : info.logado === false ? 'falta entrar na sua conta do Suno'
                : info.logado ? `conta Suno conectada${info.creditos != null ? ` · ${info.creditos} créditos` : ''}` : 'conectando'}
          </span>
          {!conectado && (
            <button className="btn btn-min" style={{ marginLeft: 'auto' }} onClick={abrir} disabled={abrindo}>
              <LuExternalLink size={13} /> {abrindo ? 'conectando' : 'conectar conta Suno'}
            </button>
          )}
        </div>

        {info && !info.navegador && <p className="aviso erro">Não achei o Chrome nem o Edge neste computador.</p>}
        {info && !conectado && (
          <p className="aviso">
            Só na primeira vez: clique em conectar e entre na sua conta na janela do Suno que aparece.
            O app nunca vê a sua senha. Depois disso a janela fica escondida e você pede tudo por aqui.
          </p>
        )}

        <form className="gerar-form" onSubmit={gerar}>
          <div className="bib-barra">
            <button type="button" className={`aba${!personalizado ? ' ativo' : ''}`} onClick={() => setPersonalizado(false)}>descrição</button>
            <button type="button" className={`aba${personalizado ? ' ativo' : ''}`} onClick={() => setPersonalizado(true)}>letra e estilo</button>
            <label className="gerar-check">
              <input type="checkbox" checked={form.instrumental} onChange={muda('instrumental')} /> instrumental
            </label>
          </div>
          {!personalizado ? (
            <textarea rows={3} maxLength={500} placeholder="ex.: rock pesado com riff de guitarra em drop D, voz masculina rasgada, sobre estrada à noite"
              value={form.descricao} onChange={muda('descricao')} />
          ) : (
            <>
              <input placeholder="título (opcional)" value={form.titulo} onChange={muda('titulo')} maxLength={80} />
              <input placeholder="estilo: ex.: blues rock, slide guitar, voz rouca, 90 bpm" value={form.estilo} onChange={muda('estilo')} maxLength={200} />
              {!form.instrumental && (
                <textarea rows={8} placeholder={'[Verse]\nsua letra aqui\n\n[Chorus]\n...'} value={form.letra} onChange={muda('letra')} />
              )}
            </>
          )}
          <div className="gerar-acoes">
            <button className="btn btn-primario" type="submit" disabled={enviando || !podeGerar}>
              <LuWandSparkles size={14} /> {enviando ? 'mandando ao Suno' : 'gerar música'}
            </button>
            <span className="painel-sub">o plano grátis do Suno dá 50 créditos por dia (cada pedido gasta 10 e faz 2 versões), só para uso não comercial</span>
          </div>
        </form>
        {erro && <p className="aviso erro">{erro}</p>}

        {(info?.pedidos || []).filter((p) => p.aviso && !['pronto', 'gerando'].includes(p.status)).slice(0, 2).map((p) => (
          <p key={p.id} className="aviso"><LuTriangleAlert size={12} /> {PEDIDO[p.status] || p.status}: {p.aviso}</p>
        ))}
      </section>

      <section className="painel">
        <div className="painel-cabeca">
          <h2 className="painel-titulo"><LuActivity size={15} /> SUAS MÚSICAS DO SUNO</h2>
          <span className="painel-sub">abra qualquer uma para separar, tirar cifra e tablatura</span>
          <button className="painel-acao" style={{ marginLeft: 'auto' }} onClick={puxar} title="atualizar"><LuRefreshCw size={13} /></button>
        </div>
        {!(info?.clips || []).length && (
          <div className="vazio">{conectado ? 'nenhuma música ainda: gere a primeira acima' : 'entre no Suno para ver suas músicas'}</div>
        )}
        <div className="bib-grade">
          {(info?.clips || []).map((c) => (
            <div key={c.id} className={`bib-card suno-card${c.status === 'error' ? ' falhou' : ''}`}>
              {c.capa && <img className="suno-capa" src={c.capa} alt="" loading="lazy" />}
              <div className="suno-texto">
                <h3 title={c.titulo}>{c.titulo || 'sem título'}</h3>
                <div className="bib-dados">
                  <span>{STATUS[c.status] || c.status}</span>
                  {c.duracao ? <span>{tempoTexto(c.duracao)}</span> : null}
                </div>
                {c.estilo && <div className="suno-estilo" title={c.estilo}>{c.estilo}</div>}
                {c.erro && <div className="aviso erro">{c.erro}</div>}
                {c.status === 'complete' && (
                  <button className="btn btn-min" onClick={() => analisar(c.id)}>
                    <LuActivity size={12} /> abrir na análise
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
