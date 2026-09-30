# XY Intelligence Design System — local copy

Pulled from the claude.ai/design project **"XY Intelligence Design System"**
(`projectId: 0481eef2-41ba-4806-847c-4bcf2b342693`) via the `DesignSync` tool's
read-only methods (`list_files` / `get_file`). This is a point-in-time copy,
not a live sync — re-pull manually if the source project changes.

## What's here

- `tokens/*.css`, `styles.css` — full copy, all six token files plus the
  import barrel.
- `components/{core,data,feedback}/*.jsx` + `*.d.ts` — only what this app
  renders: `Button`, `Logo` (core), `DataTable`, `ProgressBar` (data),
  `Alert`, `Badge` (feedback). Everything else in the source project was left
  out or deleted once unused (`Card`, `Pill`, `BrandIcon`, `Metric`,
  `Textarea`, `SideNav`, `Tabs`, and the brand icon PNGs). Re-pull a component
  the same way (`get_file` on its path under `components/`) when a screen
  needs it.
- `assets/logo-*.png` (served from `frontend/public/design-system/assets/`).

## Known gap: large assets cannot be fetched

`get_file` caps at 256 KiB per the tool's own description. Two icons in the
source set exceed that when base64-encoded (`brain-circuit.png`,
`team-gear-network.png`) — the returned content was silently truncated at
exactly 262144 base64 characters, which decodes to a corrupt PNG (confirmed
truncated with PIL). If a screen needs one, get the file some other way (e.g.
ask the user to export it from claude.ai/design, or use a different brand icon
that fits under the cap) rather than re-attempting `get_file` on it.

## Path convention

`Logo` resolves string paths itself (see its `.jsx`),
so binary assets are served as static files rather than bundled as JS
modules — they live under `frontend/public/design-system/assets/` and are
referenced by every call site with an absolute path
(`/design-system/assets/...`).

## Verifying a re-pulled binary asset

`get_file` returns base64 inline for anything under ~2KB of preview, or
writes it to a local `tool-results/*.txt` file when larger — but that file
is *also* subject to the same 256 KiB cap, so a large icon can still come
back truncated even after being "saved to a file". Always verify with:

```python
import base64
from PIL import Image
raw = base64.b64decode(content)
assert raw[:8] == bytes([137,80,78,71,13,10,26,10])  # PNG magic
Image.open(io.BytesIO(raw)).load()  # raises if truncated/corrupt
```

Never hand-retype a fetched base64 string into a `Write` call — a session
that did so once produced a plausible-looking but corrupt PNG (right magic
bytes and IEND trailer, wrong middle) that only PIL's `.load()` caught.
