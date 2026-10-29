# J.A.R.V.I.S STUDIO

The JARVIS recording studio, in the style of Reaper: record tracks, monitor your guitar
with real‑time effects, load VST3 plugins and save projects. It is a real desktop app:
sound goes straight to the audio interface (ASIO), with no browser in between.

> The interface is in Brazilian Portuguese. UI labels are quoted below with their meaning.

## Install (once)

1. Run `instalar.bat`. It creates the virtual environment, installs everything (no CUDA
   needed) and adds a **JARVIS Studio** shortcut to the desktop.
2. At the end it lists your sound devices. Yours must show up with **ASIO**.

## First use

1. **Close Reaper** or any other DAW (most ASIO drivers accept only one program at a time).
2. Open JARVIS Studio. In **Configurar áudio** (audio setup) choose Driver = ASIO, your
   interface, 48000 Hz and a 256 buffer, then click **Aplicar** (apply).
3. Track 1 starts armed (red button) with monitoring on. Play your guitar: the track meter
   should move. If it doesn't, change the track's **Entrada** (input 1, input 2...).
4. Click **+ Efeito** at the bottom and pick, for example, the ready‑made chain
   "Guitarra distorcida" (distorted guitar). Tweak the controls while you play.
5. Press **R** (or the red button at the top) to record and **Space** to stop.

With **Contagem** (count‑in) on, a bar of metronome plays before recording starts.
Recordings are aligned automatically using the interface latency; if a take still feels
early or late, fine‑tune it in audio setup > latency adjustment.

## Songs tab (JARVIS MUSIC inside the Studio)

The **Músicas** tab at the top opens JARVIS MUSIC (separate and analyse songs) in the same
window. The Studio starts JARVIS MUSIC in the background and looks for its folder; when
this repository is cloned as is, the two folders sit side by side and it is found
automatically. Otherwise click **pasta…** and select the JARVIS MUSIC folder (the one with
`backend` and `instalar.bat`). The choice is remembered.

Once a song has been separated, select it and click **Abrir no estúdio** (open in studio):
every instrument becomes a track, the BPM comes along, and playback moves to the audio
interface (ASIO) with effects. An armed empty track stays at the bottom so you can record
your own guitar on top.

## Shortcuts

| Key | Action |
|---|---|
| Space | play / pause |
| R | record |
| Home | back to start |
| L | toggle loop (drag on the ruler to set the region) |
| M | metronome |
| Ctrl+S | save (Ctrl+Shift+S: save as) |
| Ctrl+T | new track |
| Ctrl + mouse wheel | zoom the timeline |
| Shift + mouse wheel | scroll the timeline |

Drag a recorded clip sideways to move where it starts (with **Grade** / grid on, it snaps
to the beat). Double‑click a volume or pan control to reset it.

## Effects

- **Built‑in:** noise gate, high‑pass, EQ (low, mid, high), low‑pass, compressor,
  distortion, clipping, bitcrush, chorus, phaser, delay, reverb, gain and limiter.
- **Ready‑made chains:** clean guitar, distorted guitar, vocals and bass.
- **VST3:** plugins installed in `C:\Program Files\Common Files\VST3` appear in the list;
  others can be loaded by browsing for a `.vst3` file. "Abrir janela do plugin" opens the
  plugin's own editor. Effect plugins only for now (VSTi instruments are planned).

Takes are always recorded dry and effects are applied on playback, like in Reaper, so you
can change the tone after recording.

## Projects

Saving creates a folder with `projeto.json` and one `.wav` per track. **Exportar mix**
renders a 24‑bit WAV with every effect. **Importar áudio** brings in any audio file (for
example the stems separated by JARVIS MUSIC) as a new track.

## Troubleshooting

- **Clicks and pops:** raise the buffer to 512 in audio setup.
- **"Não abriu a placa" (could not open the device):** another program is using ASIO.
  Close it and try again.
- **No ASIO in the list:** install your interface's driver (or ASIO4ALL), or use
  "Windows WASAPI" with "exclusivo" (exclusive) checked.
- **See errors:** start the app with `iniciar.bat`, which keeps a console window open.

## Files

```
app.py              opens the window
estudio/motor.py    audio engine: play, record, monitor, metronome
estudio/efeitos.py  effect catalogue and VST3
estudio/projeto.py  save, open and export
estudio/api.py      bridge between the UI and the engine
estudio/musica.py   starts JARVIS MUSIC and pulls its stems
ui/                 the interface (HTML, CSS and JS, no build step)
```
