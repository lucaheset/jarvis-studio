# J.A.R.V.I.S MUSIC

A local studio to take any song apart: it separates the instruments into tracks, plays
them in sync with solo and mute per instrument, finds the BPM, key, chords and song
sections, and generates the guitar tablature (rhythm and lead in separate views).

It runs on your computer. No song ever leaves your machine.

> The interface is in Brazilian Portuguese.

---

## Install (Windows, NVIDIA GPU)

Needs **Python 3.10+** and **Node.js 18+** (to build the interface). `ffmpeg` is
provided automatically through `imageio-ffmpeg` if it is not on the PATH.

The quickest way is `instalar.bat`, which does all of the steps below. Manually:

```bat
cd jarvis-music

:: 1. isolated environment
python -m venv .venv
.venv\Scripts\activate

:: 2. PyTorch with CUDA 12.8 (RTX 50 series / Blackwell require CUDA 12.8+)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

:: 3. everything else
pip install -r backend\requisitos.txt
pip install --no-deps "basic-pitch>=0.4"
pip install --no-deps "git+https://github.com/xavriley/piano_transcription_inference.git"
```

Check that the GPU is detected:

```bat
python -c "import torch; print(torch.cuda.get_device_name(0))"
```

If you get an `sm_120` error, the installed PyTorch targets an older CUDA: repeat step 2.

Build the interface once:

```bat
cd web
npm ci
npm run build    :: outputs to backend\web
```

## Run

```bat
iniciar.bat
```

or `python backend\servidor.py` inside the venv, then open <http://127.0.0.1:8770>.
The first song downloads the separation model, so that wait only happens once.

To work on the interface with hot reload:

```bat
cd web
npm run dev      :: http://localhost:5173, proxies the API on port 8770
```

---

## What each part does

| Part | Tool | Notes |
|---|---|---|
| Instrument separation | BS‑RoFormer SW, 6 stems | #1 on the MVSEP guitar leaderboard. Falls back to Demucs |
| Rhythm vs. lead guitar | Stereo panorama + note‑level classifier | An approximation, see below |
| BPM and bars | beat_this | Falls back to librosa if not installed |
| Key | Key profiles over the chromagram | Shows alternatives and confidence |
| Chords | Chord template matching | Per bar, following the real downbeats |
| Song sections | SongFormer, heuristic fallback | Intro, verse, chorus, bridge, solo, outro |
| Tablature | Note transcription + playability optimiser | Picks string and fret with the least hand effort |
| Techniques | Per‑note pitch curve | Bend, slide, vibrato, hammer‑on and pull‑off |
| Tuning | Comparison with 8 tunings | E standard, Eb, D, Drop D, Drop C, Drop C#, C# and Drop B |
| Effects | Audio measurements (+ optional SFXlearner) | Saturation, reverb, delay relative to BPM, modulation |
| Speed / pitch | Signalsmith Stretch | Independent speed and pitch, stems stay in sync |
| Export | Guitar Pro (.gp5), MusicXML, MIDI, WAV, MP3 | Fix the tab in Guitar Pro, TuxGuitar or MuseScore |

Practice tools in the UI: live chord sheet, live tab, A‑B loop, progressive speed
trainer, play‑along scoring through your audio input, tuner, tab note editor and a
library of analysed songs. A song can also come from a YouTube link.

An optional **Gerar** (generate) tab drives a hidden browser window signed into your own
Suno account to create songs and send them straight into the analysis. No password or
cookie is stored by the app; you sign in once in that window, and solve any captcha
yourself.

## What is exact and what is an estimate

Worth knowing before you practise on top of the result:

- **Instrument separation** works well. It is the most mature part.
- **BPM and key** are right on most songs with a clear pulse.
- **Tablature** is the weakest point, and that is not a limit of this program: the best
  published system in 2026 gets about half of the notes right end to end. That is why
  export exists. Use the tab as a draft and fix the rest by ear.
- **Rhythm vs. lead** is a guess, based on stereo position and note type (chords and low
  register count as rhythm; single, high notes with bends count as lead). No open model
  does this split today.
- **Effects** reliably says whether the tone is clean or distorted, and estimates reverb,
  delay and modulation from the full mix. Treat it as a hint, not a verdict.

## Tips

- If the tab has too many or too few notes, adjust the **sensitivity** and click redo;
  lower finds fewer ghost notes, higher catches weak notes.
- To study only the guitar, solo its track (headphones button).
- To play along, mute the guitar and play over the rest.
- **Guitar L / C / R** tracks only appear when the recording really spreads guitars across
  the stereo field. Compare by ear before trusting them.

## Optional effects classifier

Detection already works without anything extra. To add the 13‑effect SFXlearner
classifier, download its weights and point to them with `JM_SFX=path\to\weights.pt`.

## Folders

```
backend/
  jarvis_music/     separation, analysis, tablature, sections, effects, export, GPU queue
  servidor.py       API and UI server
  dados/            one folder per analysed song (stems, tabs, state); not versioned
  modelos/          downloaded models; not versioned
web/                React interface (JARVIS look)
```

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `JM_PORTA` | server port | 8770 |
| `JM_DADOS` | where analyses are stored | `backend/dados` |
| `JM_MODELOS` | where downloaded models are stored | `backend/modelos` |
| `JM_SEM_GPU` | `1` forces everything onto the CPU | off |
| `JM_GPU_MEMORIA` | VRAM cap as a fraction of the card | 0.5 |
