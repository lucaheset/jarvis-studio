import { useEffect, useState } from 'react'

/** Compassos reais da música (com os acordes de cada um). Análises antigas não
 *  têm: pede ao servidor para gerar uma vez (uns 20 s). */
export function usarCompassos(estado, id) {
  const pronta = estado?.versao_cifra === 2
  const [dados, setDados] = useState(pronta ? estado : null)
  const [erro, setErro] = useState('')

  useEffect(() => {
    if (!estado || !id) { setDados(null); setErro(''); return }
    if (pronta) { setDados(estado); return }
    let vivo = true
    setDados(null); setErro('')
    fetch(`/api/cifra/${id}`, { method: 'POST' })
      .then(async (r) => {
        const j = await r.json().catch(() => ({}))
        if (!r.ok) {
          throw new Error(r.status === 404 || r.status === 405
            ? (j.detail && j.detail !== 'Not Found' ? j.detail
              : 'feche e abra o iniciar.bat de novo para ativar esta função')
            : j.detail || 'não consegui gerar os compassos')
        }
        if (vivo) setDados(j)
      })
      .catch((e) => vivo && setErro(e.message))
    return () => { vivo = false }
  }, [id, pronta, estado])

  return { dados, erro }
}

/** índice do último item com inicio <= t (busca binária) */
export function indiceEm(lista, t) {
  let lo = 0, hi = lista.length - 1, r = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (lista[mid].inicio <= t) { r = mid; lo = mid + 1 } else hi = mid - 1
  }
  return r
}
