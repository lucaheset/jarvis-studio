# JARVIS MUSIC: research on the best techniques (Oct 2026)

Notes written before building JARVIS MUSIC, on which open models and methods to use for
each part of the pipeline.

## 1. Instrument separation

- **Choice: BS‑RoFormer SW (6 stems)**, the open model used in UVR 5.6. It is #1 on the
  MVSEP guitar leaderboard (SDR 9.01), tied with Apple's Logic Pro and well above
  Demucs 6s. It runs through the `audio-separator` package (python‑audio‑separator).
  Stems: vocals, guitar, bass, drums, piano, other.
- Lighter fallback: `htdemucs_6s` (Demucs).
- Source: https://mvsep.com/quality_checker/leaderboard/guitar

## 2. Rhythm vs. lead guitar

- No open model does this. Moises, AudioShake and LALAL do it with closed models.
- Combined approach:
  1. **Stereo panorama**: rhythm parts are usually double‑tracked L/R and the lead sits in
     the centre. Produces "guitar L", "guitar R" and "guitar centre" tracks.
  2. **Per‑passage classifier**, note by note: chords, low notes and repeated picking count
     as rhythm. Single high notes with bends/vibrato and high melodic density count as lead.
  3. **Manual adjustment in the UI**: mark a passage as rhythm or lead and the tab is redone.
- Source: https://moises.ai/blog/moises-news/new-guitar-separation-models/

## 3. Tablature

- **Note by note (audio to MIDI)**: a guitar‑specific model
  - "High‑Resolution Guitar Transcription via Domain Adaptation" (Riley et al.): zero‑shot
    state of the art on GuitarSet, works on electric guitar.
  - Alternatives: YourMT3+ (multi‑instrument, open) and Basic Pitch (Spotify, lightweight).
- **String and fret**: the best published model (Fretting‑Transformer, 72% accuracy vs. 56%
  for Guitar Pro) has no open code. Implemented instead: a playability optimiser, dynamic
  programming that minimises hand jumps and stretches, along the lines of the A* baseline
  in the same paper (63%).
- **Techniques**: bend, slide, vibrato and hammer‑on/pull‑off detected from the pitch curve,
  best effort. Reference: TART (2026) reaches 54% end‑to‑end F1. That is the current
  ceiling of the research field, not just of this tool.
- **Extras**: detect the tuning (Drop D, half step down) and export to Guitar Pro (.gp5) and
  MusicXML, which open in TuxGuitar / Guitar Pro / MuseScore for correction.
- Sources:
  - https://arxiv.org/pdf/2506.14223
  - https://arxiv.org/html/2609.11904
  - https://xavriley.github.io/HighResolutionGuitarTranscription/
  - https://github.com/mimbres/yourmt3

## 4. Guitar effects

- **SFXlearner** (DAFx 2023, open source): a ResNet‑18 that recognises 13 effects
  (overdrive, distortion, chorus, flanger, phaser, tremolo, reverb, delay, slapback and EQs).
  F1 around 0.88 on test audio; accuracy drops on real mixed music.
- Alongside the model, audio measurements:
  - amount of saturation
  - length of the reverb tail
  - delay time compared with the BPM (e.g. "dotted eighth delay")
- Sources:
  - https://dafx.de/paper-archive/2023/DAFx23_paper_30.pdf
  - https://github.com/fisheggg/SFXlearner

## 5. BPM, key and chords

- **BPM and bars**: beat_this (CPJKU), state of the art in beat tracking.
- **Key**: Essentia‑style key profiles (edma/temperley) with voting.
- **Bonus**: chord sheet across the whole song.

## Where it runs

- Heavy models run on your PC. With an NVIDIA GPU a song takes about 1 minute; CPU only,
  5 to 15 minutes.
- Interface: a web app opened in the browser (or inside JARVIS Studio).
