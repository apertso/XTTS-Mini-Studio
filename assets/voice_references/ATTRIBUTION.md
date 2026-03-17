# Voice Reference Sources

These runtime reference WAV files are stored in this folder and loaded by the XTTS server from `manifest.json`.

## Processing

All checked-in WAV files in this folder were prepared from the source pages below by:

- downmixing to mono
- resampling to `22050 Hz`
- encoding as `PCM_16` WAV
- capping duration at `20s` when needed
- applying a light fade-in/fade-out
- peak-normalizing conservatively for clean playback and stable reference input

## Sources

- `lila_tretikov.wav`
  - Source: https://commons.wikimedia.org/wiki/File:Lila_Tretikov_voice.ogg
  - License: CC0 1.0

- `julie_etchingham.wav`
  - Source: https://commons.wikimedia.org/wiki/File:Julie_Etchingham_voice.ogg
  - License: CC BY-SA 4.0

- `david_lammy.wav`
  - Source: https://commons.wikimedia.org/wiki/File:David_Lammy_voice.ogg
  - License: CC BY-SA 4.0

- `david_harewood.wav`
  - Source: https://commons.wikimedia.org/wiki/File:David_Harewood_voice.ogg
  - License: CC BY-SA 4.0
