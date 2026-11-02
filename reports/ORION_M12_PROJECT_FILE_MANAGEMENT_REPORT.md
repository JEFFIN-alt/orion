# Orion M12 — Project File Management Report

## Summary

M12 adds a project-scoped file library to the existing Control Room, using Orion's SQLite database, local managed storage, existing task services, and the existing controlled CSV input path. The pending Campus Placement Insights task was not executed. No model inference, external upload, commit, or push was performed. The default `data` directory was not modified; migration and execution tests used temporary databases.

## Architecture inspected

The implementation reuses the existing project/task records, `Database` migrations and connection handling, `InputService`, `TaskWorkers`, `ControlRoom` read models, and loopback `web_chat` HTTP server. The browser sends files to project-scoped endpoints; Python validates, hashes, stores, and records them. Existing task approval/execution and the CSV worker's independent verifier are unchanged.

## Database and storage

Schema migration 9 creates project file and flat-folder metadata, append-only file events, and task attachment history. It has constraints/indexes for per-project content deduplication and same-project task/file associations. The migration test starts with schema 8 records and confirms old project, task, input, CSV configuration, approval, and execution records remain present after initialization.

Files are stored beneath the configured database directory at `projects/<project UUID>/assets/<file UUID>.blob`; a hidden UUID `.partial` is used during upload and removed on success/failure. SQLite stores the original/display name, extension, detected MIME and detection method, size, SHA-256, timestamp, uploader label, description, folder, lifecycle status, and CSV input link/status. Uploads stream in 64 KiB blocks, use generated IDs, and publish without overwriting. Stale unregistered blobs/partials older than one hour are cleaned when the project library is inspected.

Limits: 50 MiB per project file and 512 MiB of active files per project. CSV connection retains the existing CSV input limit (10 MiB) and configuration limits. Duplicate bytes in the same project are reported and not stored again.

## Accepted file types and security

- Images: PNG, JPG/JPEG, WEBP, GIF.
- Documents: PDF, DOC/DOCX, TXT, MD, RTF.
- Data: CSV, XLS/XLSX, JSON, XML.
- Development: PY, JS, HTML, CSS, SQL, YAML/YML, TOML.
- Archives: ZIP, retained without extraction.

SVG is not accepted. The browser-provided MIME type is not trusted. The server applies an extension allowlist plus content-signature checks for images, PDF, Office/ZIP, and RTF; text types must be valid UTF-8 (with format checks where implemented). Uploaded content is never executed and ZIP entries are not extracted. Storage paths are generated and project-scoped; file reads verify the database path binding, file size, and SHA-256. Cross-project lookup and task attachment are rejected. Downloads use attachment disposition, `nosniff`, no-store and restrictive CSP headers. HTML/JS and other source files are previewed only as text, never as active browser documents. Deletion first quarantines the file and detaches active task links; failed filesystem deletion remains quarantined and can be retried. CSV inputs already created are retained for execution history.

## Control Room functionality

Each project's detail view has Overview, Tasks, Files, Research, and Activity tabs. Files provides drag/drop and multi-file selection, upload progress, duplicate notices, grid/list views, filename search, categories, unassigned filter, flat folders, details, display-name/description/folder edits, safe preview, download, task associations, CSV binding, and confirmed deletion. Task details show current project-file attachments and their attach/remove history. The application server remains bound to `127.0.0.1:8765`.

Image and text-like previews work. PDF preview is not implemented; PDFs download. Folders are flat, not nested. There is no document extraction/OCR, spreadsheet parsing, archive extraction, cloud storage, or future research/coding/image worker input adapter.

## Task and CSV integration

A project file can be attached to multiple tasks in its own project. Detaching records history and does not delete the library file. CSV binding checks that the task and file share the project, that the task is pending, and that no incompatible worker assignment exists. It verifies/reuses a prior managed CSV input by bytes and digest or imports the project file through `InputService`, applies the task's existing CSV limits, and assigns `csv-profile`. This configures the task but does not request approval or execute it.

The existing CSV worker and independent output verifier were not changed. An end-to-end test performed CSV worker execution and verification only in a temporary test database.

## Tests and checks

- Full regression after the older-schema backup correction: `233` tests, `OK` (`0` failures, `0` errors).
- JavaScript syntax: `node --check src/orion/control-room.js` passed.
- `git diff --check` passed; Git emitted only line-ending normalization warnings.
- The new migration, upload/API behaviors, digest checks, duplicate handling, file limits, invalid types, traversal rejection, cross-project isolation, attachment lifecycle, CSV integration, deletion quarantine/retry, safe previews, and schema-8 preservation have focused tests.

## Live database and first use

The live database was safely backed up to `data/orion-pre-m12-20261102.sqlite3` using SQLite online backup. The backup has schema 8 and passed `integrity_check`; all 23 pre-M12 tables and rows match the migrated database exactly. The M12 migration then advanced `data/orion.sqlite3` to schema 9, with clean integrity and no foreign-key errors. The backup command initially had an outdated-schema gate that prevented this documented sequence; the CLI now allows online backup of a healthy supported older schema while other commands still require schema 9. The live Control Room was restarted to load the new routes. The identified Campus Placement Insights project is `79b9c7ad-43e7-4e63-a6da-ec2ba1792687`. Its pending “dataset analysis” task is `bf9f9435-1c45-4374-a8e2-b416ed318b09`; it remains unassigned and unexecuted.

To use the library: refresh `http://127.0.0.1:8765/`, select **Projects**, click **Open project →** on a project card, then choose the **Files** tab in the project detail view. Drag/drop or browse for files. Use the file detail panel to preview/download/edit or attach files to tasks. For a CSV task, choose “Connect as CSV worker input”; inspect the task configuration and use Orion's normal approval flow if execution is later desired.

## Remaining limitations

- Tests use isolated temporary databases; the live database was separately backed up and migrated, and the running UI was checked against the new project-file API.
- PDF preview, nested folders, CSV parsing during upload, and non-CSV worker consumption are not implemented.
- CSV integration is limited by the existing 10 MiB input limit; larger files remain stored but cannot be bound to `csv-profile`.
- File metadata/hash validation establishes byte integrity, not that a file is harmless or that its contents are true.
- Project and task deletion are not currently supported by Orion; therefore their cascading file cleanup is not applicable.
