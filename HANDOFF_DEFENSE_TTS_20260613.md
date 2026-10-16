# Defense Speech TTS Task - 2026-06-13

- Created saved production task: `defense_speech_v15`
- Saved task label: `Sprechtext Verteidigung V15 DE-ZH TTS`
- Server task path: `/var/lib/anki-streamlit-subtitle/tasks/defense_speech_v15`
- Source UTF-8 text: `exports/defense_speech_v15/source_utf8.md`
- Rebuild script: `tools/rebuild_defense_speech_task.py`
- Full audio: `sprechtext_verteidigung_v15.normalized.mp3`
- Clip directory: `subtitle_clips`
- Clips: `clip_001.mp3` through `clip_036.mp3`
- Original TTS voice: `de-DE-KatjaNeural`
- Current TTS voice: `de-DE-ConradNeural` (male)
- Current V2 task for `ooJerry@gmail.com`: `6b84542e-bb8b-45a9-a736-9483c815c509`
- Duration after male-voice rebuild: about `694.1s`

Behavior:

- All 36 slides are preselected in `favorites`.
- `push_excluded=[]`, so the Favorite list is ready for Anki push.
- The user can uncheck individual rows in the `Push` column before pushing.

Important encoding note:

- Do not pipe the DE/ZH source text through Windows PowerShell stdin.
- That corrupted German umlauts and Chinese in the first attempt.
- The final task was rebuilt from the UTF-8 source file.

Verification:

- Manifest has 36 segments and 36 translations.
- No `?` corruption in German/Chinese manifest content.
- 36 clip files exist on the server.
- Full audio exists on the server.
- `https://anki.3mudi.com/`: HTTP 200.
- Full audio Range request under `/subtitle-media/defense_speech_v15/`: HTTP 206.
- `clip_001.mp3` Range request: HTTP 206.

2026-06-13 male-voice update:

- Rebuilt all 36 clips and the full audio with `de-DE-ConradNeural`.
- Updated `tools/rebuild_defense_speech_task.py` to accept `DEFENSE_TTS_VOICE` and `DEFENSE_TTS_RATE`.
- Uploaded male audio to the saved subtitle task and V2 task storage.
- The first V2 task URL was cached by Cloudflare for 4 hours, so it was replaced with a fresh task ID:
  `6b84542e-bb8b-45a9-a736-9483c815c509`.
- Fresh V2 full-audio and clip URLs returned HTTP 206 with Cloudflare cache MISS.
