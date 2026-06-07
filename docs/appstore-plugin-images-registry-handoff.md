# Handoff: plugin images in the SciQLop appstore registry

**For:** a working session in the **`sciqlop-appstore`** repo
(https://github.com/SciQLop/sciqlop-appstore, published to
https://sciqlop.github.io/sciqlop-appstore/).
**Companion:** SciQLop-side design at
`docs/superpowers/specs/2026-06-07-appstore-plugin-images-design.md` (the client
that consumes these fields).
**Date:** 2026-06-07

## What the SciQLop client now expects

The in-app Plugin Store (and the welcome page's featured section) read two new
**optional** fields from each entry in `index.json`:

| Field         | Type            | Used for                                   |
|---------------|-----------------|--------------------------------------------|
| `image`       | string (URL)    | the card thumbnail in the store grid       |
| `screenshots` | list of strings | a carousel + lightbox in the details panel |

Client resolution rules (so the registry knows what each field drives):

- **Card thumbnail** = `image` → else `screenshots[0]` → else an emoji placeholder.
- **Carousel** = `screenshots` → else `[image]` if only `image` is set → else no
  gallery is shown.
- Any URL that fails to load is silently dropped (emoji fallback for the card, the
  slide is removed for the carousel). Missing fields render exactly like today.

Both fields are **plain URL strings and source-agnostic** — the client does not
care where they point.

### This is safe to ship independently

The SciQLop client parses `index.json` with a plain `json.loads` and reads only
named properties — there is **no strict schema validation**, so:

- older SciQLop versions ignore `image`/`screenshots` and render as before;
- newer SciQLop with an old index falls back gracefully.

So you can roll out the registry change on its own schedule. The only changes that
would break compatibility are altering/removing an *existing* field or its type.

## Recommended hosting convention

Host images **inside this repo** and serve them from GitHub Pages alongside
`index.json`, so the images are versioned together with the registry and stay
contextual with the latest released entry. Authors may still point `image`/
`screenshots` at an external absolute URL (e.g. their own repo) when they prefer.

Suggested layout (confirm against the actual repo structure):

```
assets/
  <plugin-slug>/
    card.png          # card thumbnail
    01.png 02.png …   # screenshots, in display order
```

Referenced from the entry as **absolute** Pages URLs:

```
https://sciqlop.github.io/sciqlop-appstore/assets/<plugin-slug>/card.png
```

**URLs must be absolute.** The SciQLop store page is rendered via
`setHtml(html, base_url)` with a local `file://` base URL, so a relative path like
`assets/…` would resolve against the local filesystem and fail to load. Always
emit full `https://…` URLs in `index.json`.

## Image guidelines (to put in CONTRIBUTING / issue form help text)

- **Formats:** PNG or WebP preferred; JPEG acceptable. No SVG for screenshots.
- **Card thumbnail (`image`):** landscape, ~16:10, target ~800×500; it is rendered
  cropped to a 100 px-tall, full-width cover in the card.
- **Screenshots:** landscape ~16:9; 1280×720–1920×1080 is plenty.
- **File size:** keep each under ~300 KB (they load over the network in an
  embedded webview); optimize/compress before committing.
- **Count:** up to ~5 screenshots. More just makes the carousel longer; the client
  renders all of them.
- **Content:** real SciQLop UI showing the plugin in use, not logos/banners.

## `build_index.py` changes

Per the existing architecture (YAML per entry in category dirs →
`build_index.py` merges into `site/index.json` + `site/index.html`):

1. **Pass-through:** ensure `image` and `screenshots` are copied from the entry
   YAML into the merged `index.json`. If the builder copies whole dicts, this may
   already work; if it whitelists keys, add the two fields.
2. **Validation (warn, don't hard-fail unless you prefer):**
   - `image` is a string if present; `screenshots` is a list of strings if present.
   - basic URL shape (`http(s)://…` or a repo-relative `assets/…` path).
   - optional: for repo-hosted paths, assert the file exists under `assets/`.
   - optional: warn if a referenced image exceeds the size budget.
3. **`index.html`:** optionally surface the thumbnail on the human-facing page too,
   for parity with the in-app store.

## Submission issue forms

Add optional fields to the relevant GitHub issue form templates (e.g.
`submit-plugin`, `update-entry`):

- **Card image URL** (single) → `image`
- **Screenshot URLs** (one per line) → `screenshots`

Then update `process-submission.yml` (the body parser that generates/updates the
YAML) to read those inputs and emit `image:` / `screenshots:` into the entry.
Include the image guidelines above as field help text.

## Example entry YAML

```yaml
name: Radio Dynamic Spectra
type: plugin
description: Browse and plot radio dynamic spectra from ground and space observatories.
author: LPP
license: MIT
github: SciQLop/sciqlop-plugins
tags: [radio, spectrogram, heliophysics]
image: https://sciqlop.github.io/sciqlop-appstore/assets/radio-dynamic-spectra/card.png
screenshots:
  - https://sciqlop.github.io/sciqlop-appstore/assets/radio-dynamic-spectra/01.png
  - https://sciqlop.github.io/sciqlop-appstore/assets/radio-dynamic-spectra/02.png
versions:
  - version: "0.1.0"
    sciqlop: ">=0.12,<0.13"
    pip: https://github.com/SciQLop/sciqlop-plugins/releases/download/radio_dynamic_spectra/v0.1.0/sciqlop_radio_dynamic_spectra-0.1.0-py3-none-any.whl
```

## Quick checklist for the registry session

- [ ] Decide hosting convention (in-repo `assets/<slug>/` vs absolute external) and
      document it.
- [ ] `build_index.py`: pass `image`/`screenshots` into `index.json` (+ optional
      validation).
- [ ] Add image inputs to the submission issue form(s).
- [ ] Update `process-submission.yml` to emit the new fields.
- [ ] Add image guidelines to CONTRIBUTING / form help text.
- [ ] Add images + fields to at least one existing entry to validate end-to-end
      against the in-app store.
```
