# HealthIA ONE frontend architecture

HealthIA ONE uses one visual system and semantic JavaScript modules. Version-number patches such as `ui-v2`, `ui-v3`, and similar files are prohibited.

## Runtime modules

- `web/app.js` — shell, chat, measurements, results, missions, one EventSource, and serialized state refresh.
- `web/patient-record.js` — patient record views and voice/composer enhancements.
- `web/family-documents.js` — pathological genogram and document archive.
- `web/continuity.js` — timeline, treatment, appointments, and visit preparation.
- `web/privacy-controls.js` — consent, quiet hours, pause, audit, and export.
- `web/profile-devices.js` — complete patient profile and Android Health Connect data.
- `web/icons.js` — deterministic icon decoration without recursive DOM observation.
- `web/styles.css` — the single canonical visual system.

## Performance contract

- One application bootstrap.
- One server-sent event connection.
- State refreshes are serialized and coalesced.
- No recursive `MutationObserver` for global page decoration.
- No periodic duplicate `/api/bootstrap` polling from feature modules.
- Feature modules may react to `healthia:state` events emitted by the shell.

## Repository guard

CI rejects any new file matching `web/ui-v*`. New features must extend a semantic module or introduce a clearly named module with a defined responsibility.
