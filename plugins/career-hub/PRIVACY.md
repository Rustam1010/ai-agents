# Data and privacy

Career Hub stores your profile, CV sources, original uploads, application history,
reference template settings and saved CVs in plugin-owned SQLite on your BB server.
If your BB server is remote, the data is stored on that server.

PDF, DOCX and text extraction run on the BB server in bounded workers. The plugin
does not call an external extraction service or fetch a live LinkedIn profile.
The bundled PDF font is loaded from the plugin package.

The optional assistant runs as a BB conversation through the provider you select.
Your messages, attachments and source text read by the assistant can be sent to
that provider under your BB/provider settings and quota or billing terms.
The plugin does not add a separate AI service or analytics endpoint; BB's own
services and your chosen provider have their own data handling policies.

Personal and Demo workspaces use separate stored state and assistant conversations.
Demo examples are fictional. Your data is not part of the public plugin repository.
Original uploads remain stored with the profile; JSON export contains extracted
text and profile data, while original files can be downloaded separately.

Record submissions after sending them yourself. Career Hub does not submit job
applications, contact employers or publish CVs automatically. Saved CV versions
retain their content and layout when the current profile changes.
