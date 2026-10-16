# Inhaltsnah Speech TTS Task - 2026-06-14

- Source file: `J:/00_Masterarbeit/49_答辩/Sprechtext_DE_ZH_inhaltsnah_nach_Vorbild.md`
- Source encoding: UTF-8
- Local export directory: `exports/sprechtext_inhaltsnah_nach_vorbild`
- Build script: `tools/build_tts_task_from_speech_md.py`
- TTS voice: `de-DE-ConradNeural` (male)
- V2 user email: `ooJerry@gmail.com`
- V2 user id: `d57eab64-8945-4b33-9026-f0b717635adb`
- V2 task id: `14cec7f0-bf30-4159-830c-852ba7357161`
- V2 task title: `Sprechtext DE-ZH inhaltsnah nach Vorbild TTS`
- Server task path: `/var/lib/anki/tasks/d57eab64-8945-4b33-9026-f0b717635adb/14cec7f0-bf30-4159-830c-852ba7357161`
- Full audio: `normalized.mp3`
- Clip directory: `clips`
- Clips: `clip_001.mp3` through `clip_036.mp3`
- Duration: about `1508.0s`

Verification:

- Parsed 36 Folie DE/ZH blocks.
- Database task stage is `done`, with `segment_count=36`.
- First DB segment German and Chinese text were verified as UTF-8 and readable.
- Full audio and `clip_001.mp3` returned HTTP 206 via `/api/audio/...`.
- Cloudflare cache status for the fresh URLs was `MISS`.

Notes:

- PowerShell `Get-Content` may display this source as mojibake because of console encoding; read it as UTF-8 in Python.
- `?` in German text is expected for question sentences and is not encoding corruption.
