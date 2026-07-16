# Frontend architecture

The frontend is a static browser UI served by `frontend/server.js`. It intentionally has no bundler so the app can run on a local Windows machine with Node.js and the Python TTS service.

## Script loading order

`frontend/public/index.html` loads browser scripts in dependency order:

1. shared utilities and API client: `shared-ui.js`, `tts-api-client.js`
2. model and UI definitions: `irodori-emojis.js`, `model-catalog.js`, `model-capabilities.js`, `rvc-chunking.js`
3. shared application modules: `store.js`, `generation-core.js`, `audio-controller.js`
4. RVC pure UI modules: `rvc/rvc-form.js`, `rvc/rvc-mic-recorder.js`, `rvc/rvc-result.js`
5. page controllers: `normal-controller.js`, `compare-controller.js`, `rvc/rvc-controller.js`
6. page implementations and bootstrap: `avatar-sync.js`, `normal-page.js`, `compare-page.js`, `rvc-page.js`, `app.js`
7. dedicated screens: `reference-voices.js`, `reference-voices-ux.js`, `history.js`

The application uses the single `window.LocalTts` namespace for browser modules. Do not add unrelated top-level globals.

## Responsibility boundaries

### Shared modules

- `shared-ui.js`
  - Safe localStorage access, HTML escaping, JSON fetch handling, status updates, clipboard copy, and cursor insertion.
- `store.js`
  - Small in-memory store and storage adapter used by testable browser logic.
- `generation-core.js`
  - Seed normalization, chunk-setting normalization, model-capability validation, TTS request construction, chunk attachment, error humanization, and comparison-state transitions.
  - This is the authoritative browser-side implementation of these rules. `app.js` only keeps compatibility adapters for existing page code.
- `audio-controller.js`
  - Shared audio play/stop behavior and playback error handling.

### Page controllers

- `normal-controller.js`
  - Owns normal-generation event binding, form-change orchestration, reference preview, generation actions, and history actions.
- `compare-controller.js`
  - Owns comparison event binding, selection actions, result-card delegation, regeneration/adoption, and history actions.
- `rvc/rvc-controller.js`
  - Owns RVC source switching, form and microphone events, device-change handling, conversion actions, recent-history restore/clear actions, and RVC help popovers.

Controllers receive DOM elements and actions explicitly from `app.js`. They must not discover page state through undeclared variables.

### Page implementations

- `normal-page.js`, `compare-page.js`, `rvc-page.js`
  - Render page-specific state and implement the existing generation workflows.
  - They remain classic-script compatibility modules because the repository intentionally avoids a build step.
- `app.js`
  - Builds shared state, injects dependencies into controllers, loads initial API data, connects shared chunk/audio behavior, and selects the initial tab.
  - New page-specific event handling belongs in the relevant controller, not in `bindEvents()`.
- `reference-voices.js` and `reference-voices-ux.js`
  - Reference-voice recording, file import, YouTube registration flow, management subtabs, text editing, and archive actions.
- `history.js`
  - Full history page, search, filters, favorites, detail view, replay, and restore actions.

## First-time UX contracts

### Guide page

The guide is ordered by the user's next action, not by internal architecture. Because the guide is only visible after the browser app has opened, it treats startup as complete:

1. create and play one result in normal generation
2. choose normal generation, model comparison, or RVC conversion
3. register a reference voice only when using a voice-clone-capable model
4. use `local-tts.bat -Check` and on-screen diagnostics when blocked
5. review model, source-audio, and generated-output usage conditions

`local-tts.bat` is shown only as a later-launch note. First-install instructions belong to the repository entry documentation rather than the main in-app sequence. The task cards use the existing `data-tab` navigation. The reference-voice action also uses `data-voice-open="register"`. Do not restore a large long-text explanation to this page; chunking remains documented in the tooltips on normal generation, comparison, and RVC.

### Generation form hierarchy

- Reference voice selection and seed are primary controls on normal generation, model comparison, and the TTS-input portion of RVC. Seed auto-increment stays compact beside the seed input.
- `instruction / 話し方メモ` and the Irodori emotion emoji palette live inside each screen's advanced settings. Controls that the selected model cannot use are hidden rather than shown disabled.
- RVC conversion is hidden when no complete `.pth` + `.index` pair is available. The tab instead shows the exact `models/rvc` placement path, a model-creation guide, incomplete-folder reasons, and a reload action. Ready models are selectable and resolve the request's model/index paths.
- Starting another generation must not remove or replace an existing audio player until a new result is ready. Comparison and RVC keep previous output available during processing and label retained comparison output as a previous result when a refresh fails.
- Normal-generation autoplay explicitly loads the new audio source, waits until browser media data is ready, and retries one same-source interrupted-play race. A source change is never retried.
- Normal generation, comparison, and RVC each expose a recent-history panel capped at 8 entries. RVC history restores the input source and conversion settings as well as replaying successful converted audio.
- The full history keeps at most 120 browser-local records but renders only 20 at first and adds 20 per request. It does not render while another page is active, compacts long diagnostic payloads before saving, reports storage failures, and provides one confirmed clear-all action that also clears the three recent-history panels.

### Reference voice page

The page has two independent subviews:

- `new registration`: the initial view, with method selection for microphone, local audio file, or video URL
- `registered voices`: listing, active/archived filters, preview, `voice.txt` editing, archive/restore, and reload

Only the selected registration method panel is visible. The `[hidden]` state is enforced in CSS because several panels otherwise define their own grid display. Registered voice IDs can be renamed from the management detail view; the directory is renamed server-side and browser form/history references are migrated to the new ID.

`reference-voices.js` owns existing microphone, video-URL, listing, edit, and archive behavior. `reference-voices-ux.js` owns subview/method switching, browser file selection and preview, import request validation, the success panel, and auto-growing video-URL transcript textareas. Internal route and identifier names remain unchanged. This separation prevents registration and management from sharing one always-visible layout.

### Reference voice events

- `local-tts:reference-voices-changed`: refresh selectors and management lists after a successful create, edit, archive, or restore operation
- `local-tts:reference-voice-registered`: explicit successful new registration with `{ voiceId, source }`; used for the completion panel
- `local-tts:reference-voice-renamed`: carries `{ previousVoiceId, voiceId }`; migrates active selectors, form settings, recent histories, and the full history page
- `local-tts:use-reference-voice`: asks `app.js` to open normal generation, refresh voices, and select the registered voice

The generic changed event must not be treated as a successful new registration because text edits, reloads, and archive changes also emit it.

Video-URL candidates use a three-column desktop grid, two columns on medium screens, and one column on narrow screens. Candidate textareas use `overflow-y: hidden` with JS auto-growth on initial render and input. The VTT parser removes repeated rolling-caption bridge text, and candidate selection does not backfill overlapping windows. After the first batch, `別の候補を5件追加` sends the shown time ranges as `excludeRanges`, merges the new job-scoped candidates, and keeps registration tied to each candidate's own `jobId`.

## Browser storage keys

- `local-tts-normal-history-v3`
- `local-tts-normal-form-settings-v1`
- `local-tts-compare-history-v1`
- `local-tts-compare-form-settings-v1`
- `local-tts-rvc-form-settings-v1`
- `local-tts-rvc-history-v1`
- `local-tts-rvc-mic-history-v1`
- `local-tts-rvc-mic-device-v1`
- `local-tts-rvc-chunk-settings-v1`
- `local-tts-rvc-file-path-history-v1`
- `local-tts-generation-history-v1`

Browser history and form settings are local-only. They are not durable project data and are not uploaded to the Python service.

## Adding behavior

- Add DOM-independent generation rules to `generation-core.js` and cover them in `public-core.test.js`.
- Add normal, comparison, or RVC event behavior to the corresponding controller.
- Add RVC form, microphone-state, or result normalization to `frontend/public/rvc/`.
- Keep DOM IDs, localStorage keys, routes, and existing startup UX compatible unless a migration is explicitly planned.

## Public repository constraints

Do not commit local-only data or machine-specific settings, including `config/config.local.json`, `.env` files, `reference/voices/`, `runtime/`, generated audio, model weights, or RVC indexes.

## Verification

```powershell
cd frontend
npm run check
npm test
npm run e2e:smoke
npm run e2e:reference-voices
npm run e2e:qwen-ui
npm run e2e:rvc-tabs
```

Run `npm run e2e:rvc-convert` only when the local RVC environment and `RVC_CONVERT_E2E=1` are available. Backend and repository-wide changes also require:

```powershell
python -m pytest --rootdir=. -c config/pytest.ini tests
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-setup-local-tts.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-managed-processes.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-clean-install.ps1 -AllowExistingState -PreflightOnly
```
