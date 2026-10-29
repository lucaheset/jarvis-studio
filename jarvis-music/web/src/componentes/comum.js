import { useEffect, useRef } from 'react'

export const NOMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
export const nomeNota = (m) => `${NOMES[((m % 12) + 12) % 12]}${Math.floor(m / 12) - 1}`

/** MIDI de cada corda, da 6ª (grave) para a 1ª, igual ao backend */
export const AFINACOES = {
  'E padrão': [40, 45, 50, 55, 59, 64],
  'Eb (meio tom abaixo)': [39, 44, 49, 54, 58, 63],
  'D (um tom abaixo)': [38, 43, 48, 53, 57, 62],
  'Drop D': [38, 45, 50, 55, 59, 64],
  'Drop C': [36, 43, 48, 53, 57, 62],
  'Drop C#': [37, 44, 49, 54, 58, 63],
  'C# padrão': [37, 42, 47, 52, 56, 61],
  'Drop B': [35, 42, 47, 52, 56, 61],
}
/** MIDI da corda (1 = mais aguda ... 6 = mais grave) */
export const midiDaCorda = (afinacao, corda) => (AFINACOES[afinacao] || AFINACOES['E padrão'])[6 - corda]

/** barra de espaço = play/pause em qualquer lugar da tela (menos digitando) */
export function useEspaco(mixer, ativo = true) {
  const mixerRef = useRef(mixer)
  mixerRef.current = mixer
  const ativoRef = useRef(ativo)
  ativoRef.current = ativo
  useEffect(() => {
    const tecla = (e) => {
      if (!ativoRef.current) return
      if (e.code !== 'Space' || e.repeat || e.ctrlKey || e.altKey || e.metaKey) return
      const alvo = e.target
      const digitando = alvo?.isContentEditable || alvo?.tagName === 'TEXTAREA' || alvo?.tagName === 'SELECT' ||
        (alvo?.tagName === 'INPUT' && !['range', 'checkbox', 'button'].includes(alvo.type))
      if (digitando) return
      e.preventDefault()  // não rola a página nem "clica" o botão em foco
      const m = mixerRef.current
      if (!m.prontas.length) return
      if (m.tocando) m.pausar()
      else m.tocar()
    }
    window.addEventListener('keydown', tecla, true)
    return () => window.removeEventListener('keydown', tecla, true)
  }, [])
}

/** Som de corda dedilhada (Karplus-Strong), para ouvir uma nota da tab. */
export function tocarNota(midi, duracao = 1.4) {
  const ac = new (window.AudioContext || window.webkitAudioContext)()
  const sr = ac.sampleRate
  const f = 440 * 2 ** ((midi - 69) / 12)
  const n = Math.floor(sr * duracao)
  const buf = ac.createBuffer(1, n, sr)
  const d = buf.getChannelData(0)
  const p = Math.max(2, Math.round(sr / f))
  const linha = new Float32Array(p).map(() => Math.random() * 2 - 1)
  let i = 0
  for (let k = 0; k < n; k++) {
    const a = linha[i], b = linha[(i + 1) % p]
    const v = 0.996 * 0.5 * (a + b)
    linha[i] = v
    d[k] = a * 0.5
    i = (i + 1) % p
  }
  const s = ac.createBufferSource()
  s.buffer = buf
  s.connect(ac.destination)
  s.start()
  setTimeout(() => ac.close(), duracao * 1000 + 300)
}
