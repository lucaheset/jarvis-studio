import { useEffect, useRef, useState } from 'react'
import { LuTrendingUp, LuSquare } from 'react-icons/lu'

/** Treino de velocidade progressiva: repete o loop A-B começando devagar e
 *  sobe a velocidade a cada N voltas até chegar no alvo. */
export default function TreinoProgressivo({ mixer, id }) {
  const [aberto, setAberto] = useState(false)
  const [de, setDe] = useState(60)
  const [ate, setAte] = useState(100)
  const [passo, setPasso] = useState(5)
  const [reps, setReps] = useState(3)
  const [ativo, setAtivo] = useState(false)
  const [atual, setAtual] = useState(null)
  const [msg, setMsg] = useState('')
  const trocando = useRef(false)
  const temLoop = mixer.loop.a !== null && mixer.loop.b !== null

  // deixa a próxima velocidade sendo preparada no servidor enquanto você toca
  const preparar = (vel) => {
    vel = Math.min(ate, vel)
    if (vel === 100) return
    const fd = new FormData()
    fd.append('velocidade', String(vel / 100))
    fd.append('semitons', String(mixer.semitons))
    fetch(`/api/variacao/${id}`, { method: 'POST', body: fd }).catch(() => {})
  }

  const irPara = async (vel) => {
    trocando.current = true
    setAtual(vel)
    setMsg(`preparando ${vel}%…`)
    const ok = await mixer.mudarVariacao(vel / 100, mixer.semitons)
    if (ok === false) {  // o servidor não conseguiu preparar essa velocidade: para em vez de fingir
      trocando.current = false
      setAtivo(false); setAtual(null)
      setMsg(`não consegui preparar ${vel}%: treino parado`)
      return
    }
    mixer.irPara(mixer.loop.a)
    mixer.zerarVoltas()
    if (!mixer.tocando) mixer.tocar()
    setMsg('')
    trocando.current = false
    if (vel < ate) preparar(vel + passo)
  }

  const comecar = async () => {
    if (!temLoop) { setMsg('marque o trecho com A e B primeiro'); return }
    setAtivo(true)
    await irPara(de)
  }

  const parar = () => { setAtivo(false); setAtual(null); setMsg('') }

  // a cada volta completa do loop, confere se já é hora de subir
  useEffect(() => {
    if (!ativo || trocando.current || atual === null) return
    if (mixer.voltas < reps) return
    const prox = Math.min(ate, atual + passo)
    if (atual >= ate) {
      setAtivo(false)
      setMsg(`concluído: ${reps} voltas em ${ate}%`)
      return
    }
    irPara(prox)
  }, [mixer.voltas]) // eslint-disable-line react-hooks/exhaustive-deps

  // se o loop for tirado no meio, o treino para
  useEffect(() => { if (ativo && !temLoop) parar() }, [temLoop]) // eslint-disable-line react-hooks/exhaustive-deps

  const degraus = []
  for (let v = de; v <= ate; v += passo) degraus.push(v)
  if (degraus[degraus.length - 1] !== ate) degraus.push(ate)

  return (
    <>
      <div className="estudo-grupo">
        <button className={`chip-v${aberto || ativo ? ' on' : ''}`} onClick={() => setAberto((a) => !a)}
          title="velocidade progressiva: sobe a velocidade sozinho a cada tantas voltas do loop">
          <LuTrendingUp size={12} /> treino
        </button>
        {ativo && (
          <span className="estudo-info">
            {atual}% · volta {Math.min(mixer.voltas + 1, reps)}/{reps}
            {atual < ate ? ` · depois ${Math.min(ate, atual + passo)}%` : ' · última'}
          </span>
        )}
      </div>
      {aberto && (
        <div className="treino">
          <label>de <input type="number" min="25" max="100" step="5" value={de} disabled={ativo}
            onChange={(e) => setDe(Math.max(25, Math.min(ate, Number(e.target.value) || 60)))} />%</label>
          <label>até <input type="number" min="30" max="125" step="5" value={ate} disabled={ativo}
            onChange={(e) => setAte(Math.max(de, Math.min(125, Number(e.target.value) || 100)))} />%</label>
          <label>subindo <input type="number" min="1" max="25" value={passo} disabled={ativo}
            onChange={(e) => setPasso(Math.max(1, Math.min(25, Number(e.target.value) || 5)))} />%</label>
          <label>a cada <input type="number" min="1" max="20" value={reps} disabled={ativo}
            onChange={(e) => setReps(Math.max(1, Math.min(20, Number(e.target.value) || 3)))} /> voltas</label>
          <div className="treino-degraus">
            {degraus.map((v) => (
              <i key={v} className={atual === null ? '' : v < atual ? 'feito' : v === atual ? 'agora' : ''} title={`${v}%`} />
            ))}
          </div>
          {ativo
            ? <button className="btn btn-min btn-perigo" onClick={parar}><LuSquare size={12} /> parar treino</button>
            : <button className="btn btn-min btn-primario" onClick={comecar} disabled={!temLoop}
                title={temLoop ? '' : 'marque o trecho com A e B primeiro'}>
                <LuTrendingUp size={12} /> começar
              </button>}
          {!temLoop && !ativo && <span className="treino-dica">marque o trecho com A e B</span>}
          {msg && <span className="treino-dica">{msg}</span>}
        </div>
      )}
    </>
  )
}
