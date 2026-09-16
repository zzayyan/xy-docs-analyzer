# XY Intelligence Design System — local copy

Pulled from the claude.ai/design project **"XY Intelligence Design System"**
(`projectId: 0481eef2-41ba-4806-847c-4bcf2b342693`) via the `DesignSync` tool's
read-only methods (`list_files` / `get_file`). This is a point-in-time copy,
not a live sync — re-pull manually if the source project changes.

## What's here

- `tokens/*.css`, `styles.css` — full copy, all six token files plus the
  import barrel.
- `components/{core,data,feedback,forms,navigation}/*.jsx` + `*.d.ts` — the
  subset this app uses: `Button`, `Card`, `Pill`, `Logo`, `BrandIcon` (core),
  `DataTable`, `ProgressBar`, `Metric` (data), `Alert`, `Badge` (feedback),
  `Textarea` (forms), `SideNav`, `Tabs` (navigation). `Input`, `Select`,
  `Checkbox`, `Switch`, `TopBar`, `SectionHeading`, `StepFlow` were not
  pulled — none of this app's screens need them. Re-pull them the same way
  (`get_file` on their path under `components/`) if a later screen does.
- `assets/icons/*.png`, `assets/logo-*.png` — see below.

## Known gap: two icons could not be fetched

`get_file` caps at 256 KiB per the tool's own description. Two icons in the
source set exceed that when base64-encoded (`brain-circuit.png`,
`team-gear-network.png`) — the returned content was silently truncated at
exactly 262144 base64 characters, which decodes to a corrupt PNG (confirmed
truncated with PIL). Both files were deleted rather than shipped corrupt.
Neither is wired into any screen yet, so this cost nothing functional. All
three icons that did fetch cleanly (`database-stack`, `user-lock`,
`dashboard-analytics`) are also currently unused — pulled ahead of the
screens that were expected to need them (documents nav, a privacy footer
note), but P1 shipped with a header-only shell (see `App.tsx`) that doesn't
use `BrandIcon` anywhere yet. Wire them in when a screen actually calls for
an icon, or delete the ones that go unused once the icon set settles.

If a later screen needs `brain-circuit` or similar, there's no way to fetch
it whole through this tool — get the file some other way (e.g. ask the user
to export it from claude.ai/design, or use a different brand icon that fits
under the cap) rather than re-attempting `get_file` on it.

## Path convention

`Logo` and `BrandIcon` resolve string paths themselves (see their `.jsx`),
so binary assets are served as static files rather than bundled as JS
modules — they live under `frontend/public/design-system/assets/` and are
referenced by every call site with an absolute path
(`/design-system/assets/...`), never a bare icon name, so `BrandIcon`'s
relative-path fallback never triggers.

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
