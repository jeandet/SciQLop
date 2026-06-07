# AppStore plugin images — card thumbnail + screenshot carousel

**Date:** 2026-06-07
**Status:** Approved (design)
**Scope:** SciQLop client only (rendering). The registry (`sciqlop-appstore`) is a
separate repo; its changes are captured in a handoff doc, not implemented here.

## Goal

Let each appstore entry carry images, GNOME-Software-style:

- one **card thumbnail** shown in the grid card, and
- a set of **screenshots** shown as a **carousel** in the details panel, with
  click-to-enlarge.

The plugin store currently shows only an emoji type-icon per card and a text-only
details panel.

## Schema (consumed from `index.json`, both fields optional)

```jsonc
{
  "name": "Radio Dynamic Spectra",
  // ... existing fields (type, description, author, license, github, tags,
  //     versions, url, stars) unchanged ...
  "image": "https://sciqlop.github.io/sciqlop-appstore/assets/radio/card.png",
  "screenshots": [
    "https://sciqlop.github.io/sciqlop-appstore/assets/radio/01.png",
    "https://sciqlop.github.io/sciqlop-appstore/assets/radio/02.png"
  ]
}
```

- `image` (string URL) → card thumbnail.
- `screenshots` (list of string URLs) → details-panel carousel.
- Both are plain URL strings, **source-agnostic**. Hosting them in the registry
  repo and versioning them with the latest release is a *registry convention*
  (see handoff doc), not enforced or assumed by the client.

### Backward / forward compatibility

Additive and safe in both directions:

- The index is parsed with plain `json.loads` into `list[dict]`; there is no
  Pydantic model, `extra="forbid"`, or `TypedDict` gate. `_filter_packages` does
  `dict(pkg)` (copies all keys, only overrides `versions`), so unknown keys are
  preserved and ignored.
- The JS reads only named properties; unknown JSON keys are never accessed.
- Older SciQLop versions ignore the new fields and render as today. Newer SciQLop
  reading an older index (no fields) falls back gracefully.

Therefore the registry change can ship independently of any SciQLop release.

## Behavior

### Card thumbnail (grid)

`createPackageCard` resolves the image as:

1. `image`, else
2. `screenshots[0]`, else
3. today's emoji type-placeholder.

Rendered into the existing `.card-image` slot (already `object-fit: cover`,
100 px tall). An `onerror` handler reverts a failed/dead image to the emoji
placeholder so a broken-image glyph never shows.

### Screenshot carousel (details panel)

- Inserted at the **top of the details content**, directly under the title
  (GNOME-style prominence), before the Type/Author/Version fields.
- Source list resolves as: `screenshots`, else `[image]` if only `image` exists,
  else the carousel block is **omitted entirely**.
- One image visible at a time within a **fixed-height area** (consistent across
  all cards regardless of screenshot count — the reason this style was chosen).
- Navigation: ‹ › arrows and a row of dots. A single image shows **no** arrows or
  dots.
- **Click the visible image → fullscreen lightbox overlay** (dimmed backdrop;
  dismiss by click or Esc), because the panel is only ~420 px wide. Reuses the
  Esc-to-close handler added in the recent details-panel fix.
- Carousel state (current index) is local to each `showPackageDetails` render.
  `details-content.innerHTML` is rebuilt on every selection, so there is nothing
  to reset between plugins; the arrows/dots are wired immediately after insertion.

### Failure / degradation

- Missing fields → graceful (emoji card, no gallery).
- Broken screenshot URL → that slide is dropped on `onerror` (dots/arrows adjust);
  broken card image → emoji fallback.
- Offline / proxy failure → degrades to today's text-only behavior. No crashes,
  no broken-image icons.

## Components / files (SciQLop client only)

- `SciQLop/components/appstore/resources/appstore.js`
  - `cardImageUrl(pkg)` / `screenshotUrls(pkg)` resolver helpers.
  - `createPackageCard`: render `<img>` with `onerror` emoji fallback.
  - `showPackageDetails`: build + insert carousel at top; wire arrows/dots/lightbox.
  - `renderCarousel(urls)` (HTML) + `initCarousel(root)` (wiring) kept small and
    single-purpose.
  - lightbox open/close (reuses the existing Esc keydown handler).
- `SciQLop/components/appstore/resources/appstore.css`
  - carousel (image area, arrows, dots), lightbox overlay, minor card-image tweaks.
- `SciQLop/components/appstore/resources/appstore.html.j2`
  - a hidden `#lightbox` overlay container.
- **No backend change** — `image`/`screenshots` pass through untouched.

## Testing

Front-end rendering has no existing automated coverage (QWebEngine view).
Add one cheap, real Python test:

- `_filter_packages` **preserves** `image` and `screenshots` keys (guards the
  backend pass-through against a future refactor silently dropping them).

Manual verification: Tools → Plugin Store with a registry/test entry carrying
`image` + `screenshots` — confirm card thumbnail, carousel nav, lightbox, and all
fallbacks (no image, one image, dead URL, offline).

## Out of scope

- Registry-side implementation (schema validation in `build_index.py`, submission
  issue forms, image hosting) — delivered as a separate handoff document
  (`docs/appstore-plugin-images-registry-handoff.md`) for a `sciqlop-appstore`
  session.
- Video/GIF media, captions per screenshot, per-version screenshots.
- Local image caching (rely on QWebEngine's HTTP cache).
```
