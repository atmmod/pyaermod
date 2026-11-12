# DBA: browser-gui

No database. State: the project document (project_io JSON, save_format_version 1, unchanged) in localStorage under `pyaermod-app/document`; uploaded files as base64 in IndexedDB `pyaermod-app`/`files`; both per-browser conveniences wrapped in try/catch. No schema migration: the file format is shared with pyaermod-app and not changed.
