# AppStore — GNOME Software-style layout

**Date:** 2026-06-18
**Status:** Design, pending implementation
**Companion:** earlier image-loading fix (`web_channel_page.py` enabling
`LocalContentCanAccessRemoteUrls`) is a prerequisite — already shipped on this branch.

## Goal

Reshape the in-app Plugin Store from a flat grid + cramped side panel into a
GNOME Software-style storefront: a featured hero banner, type-grouped tile rows,
top-level Explore / Installed / Updates pages, and a full-page app detail view.

## Scope

**Front-end only.** All work is in the three resource files:

- `SciQLop/components/appstore/resources/appstore.html.j2`
- `SciQLop/components/appstore/resources/appstore.css`
- `SciQLop/components/appstore/resources/appstore.js`

`backend.py` is **unchanged**. It already exposes everything the new UI needs:
per-entry `name / type / author / license / versions / tags / stars / image /
screenshots`, plus `fetch_packages`, `install_package`, `uninstall_package`,
`get_installed_versions`, `list_tags`. Version-compat filtering, host-package
isolation, and plugin hot-load all stay exactly as they are.

Out of scope: registry-side changes. "Featured" is derived client-side (see
below), so no new registry field is required.

## Page model

Replace the current `tab-bar` (All / Plugins / Workspaces / Templates / Examples)
with three top-level **pages**, GNOME-style:

| Page | Content |
|------|---------|
| **Explore** | Hero banner + type-grouped tile rows. The default landing page. |
| **Installed** | Tiles for entries where `installStatus(pkg) !== "not-installed"`. |
| **Updates** | Tiles for entries where `installStatus(pkg) === "update-available"`, each with an inline Update action. Page shows a count badge; empty state when none. |

Page state is a single `activePage` variable (`"explore" | "installed" |
"updates"`), mirroring the existing `activeCategory` pattern. Switching pages
re-renders the body.

The type tabs are **removed as navigation**; type instead becomes the section
grouping inside Explore (below). Tag chips and sort are retained but only shown
in flat-list contexts (search results, Installed, Updates) — not on Explore,
which is organised by section.

## Explore page

### Hero banner

- **Source:** all entries with a usable image (`image` or `screenshots[0]`),
  in registry order. This is the "auto-rotate entries with images" decision.
- Rotates automatically (e.g. 6 s interval) with manual dots; pauses on hover.
- Layout: full-width banner, screenshot as cover, left-aligned gradient veil
  carrying a "Featured" kicker, entry name, one-line summary, and a primary
  **Install** button (or **Installed ✓** / **Update** reflecting status).
- Clicking the banner body (not the button) opens that entry's detail page.
- If **no** entry has an image, the banner is omitted entirely and Explore opens
  straight into the section rows.

### Type sections

One section per type that has ≥1 entry, in fixed order: **Plugins, Workspaces,
Templates, Examples**. Each section is a heading (`Type` + "N available") above a
responsive tile grid (`repeat(auto-fill, minmax(...))`). Entries are sorted by
the existing sort rule (stars desc, then name).

### Tile

Image-forward, replacing the current compact card:

- **Top:** screenshot/`image` as a cover (taller than today, ~96px+), object-fit
  cover. On `error`, fall back to the gradient-initial placeholder.
- **Gradient-initial fallback** (replaces the emoji placeholder): a gradient
  whose hue is derived deterministically from the entry name, with the name's
  first letter centered. Keeps image-less entries (MSA, opencode, FDSN) looking
  intentional rather than broken.
- **Body:** name + inline status badge (Installed / Update) ; one-line summary
  (`description`, clamped to ~2 lines) ; footer with ★ stars · license · version.
- Hover lift (translateY + shadow). Click opens the detail page.

## Detail view (full page)

Replaces the slide-in `#details-panel` aside with a full-page view that hides the
Explore/Installed/Updates body while open.

- **Back** button (← ) returns to the previously active page, restoring scroll.
- **Left column:** large screenshot carousel (reuse existing `renderCarousel` /
  `initCarousel` / lightbox logic, which already handles arrows, dots, failed-image
  drop, and click-to-zoom) + a thumbnail strip under it.
- **Right column:** name, author, primary action button(s) — Install /
  Installed ✓ + Uninstall / Update + Uninstall (same states and handlers as today)
  — and a facts table (Type, License, Version, Installed, Requires, Stars, Tags).
- **Below, full width:** the description.
- The install/uninstall click handlers, `onInstallFinished` / `onUninstallFinished`
  result handling, and the install-error `<pre>` box are reused unchanged; only
  their container moves from the aside into the detail page.

## Search

When the search box is non-empty, Explore collapses its banner + sections into a
**single flat tile grid** of matches (same filter logic as today: name +
description + tags substring), with tag chips and sort visible. Clearing the
search restores the banner + sections. Installed/Updates pages always render as
flat grids and honour search within their subset.

## Component boundaries (appstore.js)

Keep functions small and single-purpose, following the existing file's style:

- `renderApp()` — top-level: dispatch on `activePage`, show/hide detail view.
- `renderExplore()` — banner (if any) + sections, or flat search results.
- `renderHero(entries)` / `startHeroRotation()` — banner + auto-rotation.
- `renderSection(type, entries)` and `createTile(pkg)` — replace `createPackageCard`.
- `placeholderTile(pkg)` — gradient-initial fallback markup (shared by tile + hero).
- `renderDetailPage(pkg)` — replaces `showPackageDetails`; reuses carousel/lightbox
  and the existing install/uninstall handlers.
- Retain: `installStatus`, `latestVersion`, `cardImageUrl`, `screenshotUrls`,
  `renderCarousel`, `initCarousel`, `openLightbox`, `escapeHtml`, `escapeAttr`,
  and the whole `backend` wiring in `init` / `onPackagesReady`.

## Theming

Continue to drive all colors from the injected SciQLop palette CSS variables
(`--Window`, `--Base`, `--Text`, `--Highlight`, `--Borders`, …) as the current
CSS does. No hard-coded colors except the existing status greens/ambers/reds and
the deterministic placeholder gradient (derived from palette `--Highlight` hue
where practical). Must look correct in both light and dark themes; the page is
re-rendered on `theme_changed` (already wired in `WebChannelPage`).

## Testing & verification

- **Backend untouched** ⇒ `tests/test_appstore_index.py` and
  `tests/test_appstore_install.py` must stay green (regression guard that the
  data contract the new UI relies on is intact).
- `tests/test_web_channel_page.py` (remote-image attribute) stays green.
- No JS unit-test harness exists in this repo, so the new front-end is verified
  **manually** against the running app: Explore banner rotates and only shows
  image-bearing entries; sections grouped by type; image-less tiles show the
  gradient-initial; clicking a tile opens the full-page detail with working
  carousel + lightbox; Install / Update / Uninstall still work and hot-load;
  Installed and Updates pages list the right entries; search collapses to a flat
  grid. The companion mockup
  (`.superpowers/brainstorm/.../store-fidelity.html`) is the visual reference.

## Non-goals / YAGNI

- No registry schema change (no `featured` field, no category metadata).
- No category/topic-tag sections (grouping is by type only).
- No per-entry "what's new" / changelog (registry has no such field).
- No new backend slots or persisted UI state beyond what exists.
