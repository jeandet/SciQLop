# AppStore GNOME Software-style Layout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reshape the in-app Plugin Store into a GNOME Software-style storefront — featured hero banner, type-grouped tile rows, Explore/Installed/Updates pages, and a full-page detail view.

**Architecture:** Front-end only. All changes live in the three resource files (`appstore.html.j2`, `appstore.css`, `appstore.js`). `backend.py` is untouched — it already serves every field (name/type/author/license/versions/tags/stars/image/screenshots) and the install/uninstall/installed-version slots the UI needs. Each task leaves the store runnable and is verified by launching the app and observing the result; the appstore backend tests are the regression guard that the data contract is intact.

**Tech Stack:** PySide6 QWebEngineView + QWebChannel, vanilla JS (ES5 style, matching the existing file), Jinja2 template, CSS driven by injected SciQLop palette variables.

**Spec:** `docs/superpowers/specs/2026-06-18-appstore-gnome-software-layout-design.md`
**Visual reference:** `.superpowers/brainstorm/3789794-1781816998/content/store-fidelity.html` (validated mockup — the target look).

---

## Testing note (read first)

This repo has **no JavaScript test harness**. The new front-end is verified **manually** by launching SciQLop and opening the Plugin Store (Welcome tab → Plugin Store, or the store toolbar button). Each task ends with a concrete "observe X" check.

The **regression guard** is the Python backend test suite, which must stay green because the UI depends on its data contract:

```bash
uv run pytest --no-xvfb tests/test_appstore_index.py tests/test_appstore_install.py tests/test_web_channel_page.py
```
(`--no-xvfb` is the project convention; drop it if your environment runs headed.)

Commit after every task.

---

## Task 1: New tile + gradient-initial fallback

Replace the compact `createPackageCard` with an image-forward `createTile`, and replace the emoji placeholder with a deterministic gradient + initial. HTML structure unchanged (still a flat `#package-cards` grid, tabs and side panel still work).

**Files:**
- Modify: `SciQLop/components/appstore/resources/appstore.js` (`createPackageCard` → `createTile`, add `placeholderTile`, `tileHue`)
- Modify: `SciQLop/components/appstore/resources/appstore.css` (`.card*` → `.tile*`)

- [ ] **Step 1: Add the placeholder helpers and replace `createPackageCard` in `appstore.js`**

Replace the entire `// --- Card creation ---` section (the `createPackageCard` function, lines ~124-180) with:

```javascript
// --- Tile creation ---

// Deterministic hue 0-359 from the entry name, so an image-less tile always
// gets the same color and tiles look intentional rather than broken.
function tileHue(name) {
    var h = 0;
    for (var i = 0; i < name.length; i++) {
        h = (h * 31 + name.charCodeAt(i)) % 360;
    }
    return h;
}

function placeholderTile(pkg) {
    var hue = tileHue(pkg.name || "?");
    var initial = (pkg.name || "?").trim().charAt(0).toUpperCase();
    return '<div class="tile-shot placeholder" style="background:linear-gradient(135deg,' +
        'hsl(' + hue + ',38%,32%),hsl(' + ((hue + 40) % 360) + ',32%,18%))">' +
        escapeHtml(initial) + '</div>';
}

function tileShot(pkg) {
    var url = cardImageUrl(pkg);
    if (!url) return placeholderTile(pkg);
    return '<div class="tile-shot"><img src="' + escapeAttr(url) + '"></div>';
}

function statusBadgeHtml(status) {
    if (status === "installed") return '<span class="status-badge installed">Installed</span>';
    if (status === "update-available") return '<span class="status-badge update">Update</span>';
    return "";
}

function createTile(pkg) {
    var tile = document.createElement("div");
    tile.className = "tile";
    tile.dataset.name = (pkg.name || "").toLowerCase();

    var status = installStatus(pkg);
    var latest = latestVersion(pkg);
    var versionStr = latest ? latest.version : "";
    var starsHtml = pkg.stars != null ? "★ " + pkg.stars : "★ —";
    var footer = [starsHtml, pkg.license || "—", versionStr ? "v" + versionStr : ""]
        .filter(Boolean)
        .map(function(s) { return '<span>' + escapeHtml(s) + '</span>'; })
        .join("");

    tile.innerHTML =
        tileShot(pkg) +
        '<div class="tile-body">' +
            '<div class="tile-name">' + escapeHtml(pkg.name) + statusBadgeHtml(status) + '</div>' +
            '<div class="tile-sum">' + escapeHtml(pkg.description || "") + '</div>' +
            '<div class="tile-ft">' + footer + '</div>' +
        '</div>';

    var img = tile.querySelector(".tile-shot img");
    if (img) {
        img.addEventListener("error", function() {
            tile.querySelector(".tile-shot").outerHTML = placeholderTile(pkg);
        });
    }

    tile.addEventListener("click", function() {
        if (tile === selectedCard) { hideDetails(); return; }
        selectCard(tile);
        showPackageDetails(pkg);
    });
    return tile;
}
```

- [ ] **Step 2: Point `renderCards` at `createTile`**

In `renderCards`, change the final loop body from `container.appendChild(createPackageCard(pkg));` to:

```javascript
        container.appendChild(createTile(pkg));
```

- [ ] **Step 3: Replace the card CSS with tile CSS in `appstore.css`**

Replace the `/* --- Card grid --- */` and `/* --- Cards --- */` blocks (everything from `.cards-grid` through `.status-badge.update`, lines ~120-229) with:

```css
/* --- Tile grid --- */

.cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 14px;
}

/* --- Tiles --- */

.tile {
    background: var(--Window);
    border: 1px solid var(--Borders);
    border-radius: 9px;
    overflow: hidden;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    user-select: none;
}

.tile:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 22px rgba(0, 0, 0, 0.45);
}

.tile.selected {
    border-color: var(--Highlight);
    box-shadow: 0 0 0 2px var(--Highlight);
}

.tile-shot {
    height: 120px;
    background: var(--AlternateBase);
}

.tile-shot img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}

.tile-shot.placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 120px;
    font-size: 2.4em;
    font-weight: 700;
    color: #cdd9ec;
}

.tile-body { padding: 9px 11px; }

.tile-name {
    font-size: 0.92em;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 6px;
}

.tile-sum {
    font-size: 0.8em;
    color: var(--UnselectedText);
    margin-top: 3px;
    line-height: 1.35;
    height: 2.7em;
    overflow: hidden;
}

.tile-ft {
    font-size: 0.78em;
    color: var(--UnselectedText);
    margin-top: 7px;
    display: flex;
    gap: 10px;
}

.status-badge {
    display: inline-block;
    font-size: 0.62em;
    padding: 1px 6px;
    border-radius: 4px;
    vertical-align: middle;
    font-weight: 500;
}

.status-badge.installed { background: #2ea043; color: #ffffff; }
.status-badge.update { background: #d29b00; color: #ffffff; }
```

- [ ] **Step 4: Launch the app and verify**

Run: `uv run sciqlop` → open the Plugin Store.
Expected: tiles are wider with a tall (120px) cover image; CDF Workbench / Radio / Copilot show real screenshots; MSA / opencode / FDSN show a colored gradient tile with their first initial (no emoji); each tile has a name, a two-line summary, and a ★ / license / version footer. Clicking a tile still opens the side panel.

- [ ] **Step 5: Run the regression guard**

Run: `uv run pytest --no-xvfb tests/test_appstore_index.py tests/test_appstore_install.py tests/test_web_channel_page.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add SciQLop/components/appstore/resources/appstore.js SciQLop/components/appstore/resources/appstore.css
git commit -m "feat(appstore): image-forward tiles with gradient-initial fallback"
```

---

## Task 2: Type-grouped sections

Group the Explore body into one section per type (Plugins, Workspaces, Templates, Examples). When a search query is present, render a flat grid instead. Tabs still exist and still filter to a single type.

**Files:**
- Modify: `SciQLop/components/appstore/resources/appstore.js` (`renderCards`, add `renderSection`, `filterPackages`)
- Modify: `SciQLop/components/appstore/resources/appstore.css` (section heading styles)

- [ ] **Step 1: Extract the filter and add section rendering in `appstore.js`**

Replace the whole `renderCards` function (lines ~88-122) with:

```javascript
var TYPE_ORDER = ["plugin", "workspace", "template", "example"];
var TYPE_LABEL = {plugin: "Plugins", workspace: "Workspaces", template: "Templates", example: "Examples"};

function filterPackages() {
    var query = (document.getElementById("search-input").value || "").toLowerCase();
    return allPackages.filter(function(pkg) {
        var type = pkg.type || "plugin";
        if (activeCategory && type !== activeCategory) return false;
        if (activeTags.size > 0) {
            var pkgTags = pkg.tags || [];
            var hasTag = false;
            activeTags.forEach(function(t) { if (pkgTags.indexOf(t) !== -1) hasTag = true; });
            if (!hasTag) return false;
        }
        if (query) {
            var text = (pkg.name + " " + pkg.description + " " + (pkg.tags || []).join(" ")).toLowerCase();
            if (text.indexOf(query) === -1) return false;
        }
        return true;
    });
}

function sortPackages(list) {
    return list.slice().sort(function(a, b) {
        if (activeSort === "stars") return (b.stars || 0) - (a.stars || 0);
        return a.name.localeCompare(b.name);
    });
}

function appendTiles(container, list) {
    sortPackages(list).forEach(function(pkg) { container.appendChild(createTile(pkg)); });
}

function renderSection(container, type, list) {
    if (list.length === 0) return;
    var head = document.createElement("div");
    head.className = "section-h";
    head.innerHTML = '<h4>' + escapeHtml(TYPE_LABEL[type] || type) + '</h4>' +
        '<span>' + list.length + ' available</span>';
    container.appendChild(head);
    var grid = document.createElement("div");
    grid.className = "cards-grid";
    appendTiles(grid, list);
    container.appendChild(grid);
}

function renderCards() {
    var query = (document.getElementById("search-input").value || "").toLowerCase();
    var container = document.getElementById("package-cards");
    container.innerHTML = "";
    var filtered = filterPackages();

    // Flat grid while searching or when a single type tab is active; otherwise
    // group into one section per type.
    if (query || activeCategory) {
        container.className = "cards-grid";
        appendTiles(container, filtered);
        return;
    }
    container.className = "sections";
    TYPE_ORDER.forEach(function(type) {
        renderSection(container, type, filtered.filter(function(p) { return (p.type || "plugin") === type; }));
    });
}
```

- [ ] **Step 2: Add section heading CSS in `appstore.css`**

Add after the `.cards-grid` block:

```css
/* --- Sections --- */

.sections { display: block; }

.section-h {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin: 18px 2px 10px;
}

.section-h h4 { font-size: 1.05em; font-weight: 600; }
.section-h span { font-size: 0.82em; color: var(--UnselectedText); }
.section-h:first-child { margin-top: 4px; }
```

- [ ] **Step 3: Launch and verify**

Run: `uv run sciqlop` → Plugin Store.
Expected: on the "All" tab, tiles are grouped under a "Plugins" heading (with "6 available") and a "Workspaces" heading if any workspace entries exist; clicking the "Plugins" tab shows a flat grid of just plugins; typing in search shows a flat grid of matches.

- [ ] **Step 4: Commit**

```bash
git add SciQLop/components/appstore/resources/appstore.js SciQLop/components/appstore/resources/appstore.css
git commit -m "feat(appstore): group explore tiles into per-type sections"
```

---

## Task 3: Hero banner + auto-rotation

Add a featured hero banner above the sections that rotates through entries with images. Hidden when searching or filtering by a tab.

**Files:**
- Modify: `SciQLop/components/appstore/resources/appstore.html.j2` (add `#hero` container)
- Modify: `SciQLop/components/appstore/resources/appstore.js` (`renderHero`, `startHeroRotation`, hook into `renderCards`)
- Modify: `SciQLop/components/appstore/resources/appstore.css` (hero styles)

- [ ] **Step 1: Add the hero container to `appstore.html.j2`**

Insert directly above `<div class="cards-grid" id="package-cards"></div>` (line 38):

```html
    <div id="hero"></div>
```

- [ ] **Step 2: Add hero rendering and rotation to `appstore.js`**

Add a module-level variable near the top (after `var activeSort = "stars";`):

```javascript
var heroTimer = null;
var heroIndex = 0;
```

Add these functions just above `renderCards`:

```javascript
// --- Hero banner ---

function featuredPackages() {
    return allPackages.filter(function(p) { return cardImageUrl(p); });
}

function heroActionLabel(status) {
    if (status === "installed") return "Installed ✓";
    if (status === "update-available") return "Update";
    return "Install";
}

function renderHero() {
    var host = document.getElementById("hero");
    if (heroTimer) { clearInterval(heroTimer); heroTimer = null; }
    var query = (document.getElementById("search-input").value || "");
    var feat = featuredPackages();
    if (query || activeCategory || feat.length === 0) { host.innerHTML = ""; return; }

    heroIndex = heroIndex % feat.length;
    drawHero(host, feat);
    if (feat.length > 1) {
        heroTimer = setInterval(function() {
            heroIndex = (heroIndex + 1) % feat.length;
            drawHero(host, feat);
        }, 6000);
    }
}

function drawHero(host, feat) {
    var pkg = feat[heroIndex];
    var status = installStatus(pkg);
    var dots = feat.map(function(_, i) {
        return '<i class="' + (i === heroIndex ? "on" : "") + '" data-i="' + i + '"></i>';
    }).join("");
    host.innerHTML =
        '<div class="hero">' +
            '<img src="' + escapeAttr(cardImageUrl(pkg)) + '">' +
            '<div class="hero-veil"></div>' +
            '<div class="hero-meta">' +
                '<span class="hero-kick">Featured</span>' +
                '<h3>' + escapeHtml(pkg.name) + '</h3>' +
                '<p>' + escapeHtml(pkg.description || "") + '</p>' +
                '<button class="hero-btn">' + heroActionLabel(status) + '</button>' +
            '</div>' +
            '<div class="hero-dots">' + dots + '</div>' +
        '</div>';

    host.querySelector(".hero").addEventListener("click", function(e) {
        if (e.target.closest(".hero-dots")) return;
        selectCard(null);
        showPackageDetails(pkg);
    });
    host.querySelectorAll(".hero-dots i").forEach(function(dot) {
        dot.addEventListener("click", function(e) {
            e.stopPropagation();
            heroIndex = parseInt(dot.dataset.i, 10);
            renderHero();
        });
    });
}
```

- [ ] **Step 3: Call `renderHero` from `renderCards`**

At the very top of `renderCards` (after the `container.innerHTML = ""` line is fine), add:

```javascript
    renderHero();
```

- [ ] **Step 4: Make `selectCard` tolerate a null argument in `appstore.js`**

Replace `selectCard` (lines ~413-417) with:

```javascript
function selectCard(card) {
    if (selectedCard) selectedCard.classList.remove("selected");
    selectedCard = card;
    if (card) card.classList.add("selected");
}
```

- [ ] **Step 5: Add hero CSS in `appstore.css`**

Add a new block before `/* --- Sections --- */`:

```css
/* --- Hero banner --- */

#hero:empty { display: none; }

.hero {
    position: relative;
    height: 180px;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid var(--Borders);
    margin-bottom: 6px;
    cursor: pointer;
}

.hero img { width: 100%; height: 100%; object-fit: cover; display: block; }

.hero-veil {
    position: absolute; inset: 0;
    background: linear-gradient(90deg, rgba(10,12,16,.92) 0%, rgba(10,12,16,.55) 45%, rgba(10,12,16,0) 100%);
}

.hero-meta {
    position: absolute; left: 22px; top: 0; bottom: 0;
    display: flex; flex-direction: column; justify-content: center; max-width: 55%;
}

.hero-kick { font-size: 0.72em; letter-spacing: 1px; text-transform: uppercase; color: var(--Highlight); font-weight: 600; }
.hero-meta h3 { font-size: 1.7em; margin: 4px 0 6px; color: #fff; }
.hero-meta p { font-size: 0.9em; color: #c6d0de; margin-bottom: 12px; }

.hero-btn {
    align-self: flex-start;
    background: var(--Highlight); color: var(--HighlightedText);
    border: none; border-radius: 7px; padding: 7px 22px; font-size: 0.9em; cursor: pointer;
}

.hero-dots { position: absolute; bottom: 10px; right: 14px; display: flex; gap: 6px; }
.hero-dots i { width: 8px; height: 8px; border-radius: 50%; background: #ffffff55; cursor: pointer; }
.hero-dots i.on { background: #fff; }
```

- [ ] **Step 6: Launch and verify**

Run: `uv run sciqlop` → Plugin Store.
Expected: a banner spans the top showing CDF Workbench's screenshot with a "Featured" kicker, name, summary, and Install button; it auto-advances every ~6s through the image-bearing entries; clicking a dot jumps to that entry; clicking the banner body opens its details; the banner disappears when you type in search or click a type tab.

- [ ] **Step 7: Commit**

```bash
git add SciQLop/components/appstore/resources/appstore.html.j2 SciQLop/components/appstore/resources/appstore.js SciQLop/components/appstore/resources/appstore.css
git commit -m "feat(appstore): auto-rotating featured hero banner"
```

---

## Task 4: Explore / Installed / Updates pages

Replace the type tab-bar with three top-level pages. Explore = hero + sections; Installed = flat grid of installed entries; Updates = flat grid of update-available entries with an inline Update action.

**Files:**
- Modify: `SciQLop/components/appstore/resources/appstore.html.j2` (tab-bar → page nav)
- Modify: `SciQLop/components/appstore/resources/appstore.js` (`activePage`, page rendering, nav handlers; retire `activeCategory`)
- Modify: `SciQLop/components/appstore/resources/appstore.css` (page-nav styles, empty state)

- [ ] **Step 1: Replace the tab-bar markup in `appstore.html.j2`**

Replace the `<div id="tab-bar">…</div>` block (lines 18-24) with:

```html
    <div id="page-nav">
        <button class="page-btn active" data-page="explore">Explore</button>
        <button class="page-btn" data-page="installed">Installed</button>
        <button class="page-btn" data-page="updates">Updates <span id="updates-count"></span></button>
    </div>
```

- [ ] **Step 2: Replace tab state/handlers with page state in `appstore.js`**

Replace `var activeCategory = "";` (line 6) with:

```javascript
var activePage = "explore";
```

Then update `renderCards` so the flat-vs-sections decision uses `activePage` instead of `activeCategory`. Replace the body of `renderCards` (the version from Task 2/3) with:

```javascript
function renderCards() {
    var query = (document.getElementById("search-input").value || "").toLowerCase();
    var container = document.getElementById("package-cards");
    container.innerHTML = "";
    renderHero();
    updateUpdatesCount();

    if (activePage === "installed") {
        container.className = "cards-grid";
        appendTiles(container, pageSubset(filterPackages()));
        emptyStateIfNeeded(container, "No plugins installed yet.");
        return;
    }
    if (activePage === "updates") {
        container.className = "cards-grid";
        appendTiles(container, pageSubset(filterPackages()));
        emptyStateIfNeeded(container, "Everything is up to date.");
        return;
    }
    // explore
    if (query) {
        container.className = "cards-grid";
        appendTiles(container, filterPackages());
        return;
    }
    container.className = "sections";
    var filtered = filterPackages();
    TYPE_ORDER.forEach(function(type) {
        renderSection(container, type, filtered.filter(function(p) { return (p.type || "plugin") === type; }));
    });
}

function pageSubset(list) {
    return list.filter(function(pkg) {
        var status = installStatus(pkg);
        if (activePage === "installed") return status !== "not-installed";
        if (activePage === "updates") return status === "update-available";
        return true;
    });
}

function emptyStateIfNeeded(container, message) {
    if (container.children.length > 0) return;
    container.className = "empty-state";
    container.innerHTML = '<p>' + escapeHtml(message) + '</p>';
}

function updateUpdatesCount() {
    var n = allPackages.filter(function(p) { return installStatus(p) === "update-available"; }).length;
    var el = document.getElementById("updates-count");
    if (el) el.textContent = n > 0 ? "(" + n + ")" : "";
}
```

In `filterPackages` (from Task 2), remove the `activeCategory` line — it no longer exists. The function's first two lines become:

```javascript
function filterPackages() {
    var query = (document.getElementById("search-input").value || "").toLowerCase();
    return allPackages.filter(function(pkg) {
        if (activeTags.size > 0) {
```

In `renderHero`, replace the guard `if (query || activeCategory || feat.length === 0)` with:

```javascript
    if (query || activePage !== "explore" || feat.length === 0) { host.innerHTML = ""; return; }
```

- [ ] **Step 3: Wire the page-nav buttons in `appstore.js`**

In the `DOMContentLoaded` handler, replace the `.tab` click-wiring block (lines ~422-429) with:

```javascript
    document.querySelectorAll(".page-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            document.querySelector(".page-btn.active").classList.remove("active");
            btn.classList.add("active");
            activePage = btn.dataset.page;
            hideDetails();
            renderCards();
        });
    });
```

In the body click-away handler (line ~454-458), replace the selector `.tab` with `.page-btn`:

```javascript
        if (!e.target.closest(".card, .tile, #details-panel, #detail-page, #lightbox, .tag-chip, .page-btn, #toolbar, #hero")) {
```

- [ ] **Step 4: Replace tab CSS with page-nav and empty-state CSS in `appstore.css`**

Replace the `/* --- Tab bar --- */` block (lines ~22-50) with:

```css
/* --- Page nav --- */

#page-nav {
    display: flex;
    gap: 4px;
    margin-bottom: 14px;
}

.page-btn {
    padding: 6px 16px;
    background: none;
    border: none;
    border-radius: 6px;
    color: var(--UnselectedText);
    cursor: pointer;
    font-size: 0.95em;
    font-weight: 500;
}

.page-btn:hover { color: var(--Text); }

.page-btn.active {
    background: var(--AlternateBase);
    color: var(--Text);
}

#updates-count { font-size: 0.85em; color: var(--Highlight); }

/* --- Empty state --- */

.empty-state {
    text-align: center;
    padding: 64px 16px;
    color: var(--UnselectedText);
    font-size: 0.95em;
}
```

- [ ] **Step 5: Launch and verify**

Run: `uv run sciqlop` → Plugin Store.
Expected: the top shows Explore / Installed / Updates instead of type tabs; Explore shows hero + per-type sections; Installed shows only entries you have installed (or "No plugins installed yet."); Updates shows only update-available entries (or "Everything is up to date.") and the nav shows a count badge when updates exist; switching pages closes any open details.

- [ ] **Step 6: Run the regression guard**

Run: `uv run pytest --no-xvfb tests/test_appstore_index.py tests/test_appstore_install.py tests/test_web_channel_page.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add SciQLop/components/appstore/resources/appstore.html.j2 SciQLop/components/appstore/resources/appstore.js SciQLop/components/appstore/resources/appstore.css
git commit -m "feat(appstore): Explore/Installed/Updates pages replace type tabs"
```

---

## Task 5: Full-page detail view

Replace the slide-in side panel with a full-page detail view: Back button, large carousel + thumbnails on the left, name/author/actions/facts on the right, description below. Reuse the existing carousel, lightbox, and install/uninstall handlers.

**Files:**
- Modify: `SciQLop/components/appstore/resources/appstore.html.j2` (`#details-panel` aside → `#detail-page`)
- Modify: `SciQLop/components/appstore/resources/appstore.js` (`renderDetailPage` replaces `showPackageDetails`; back/scroll handling)
- Modify: `SciQLop/components/appstore/resources/appstore.css` (detail-page styles; drop side-panel + `details-open` styles)

- [ ] **Step 1: Replace the details aside in `appstore.html.j2`**

Replace the `<aside id="details-panel" …>…</aside>` block (lines 40-45) with:

```html
    <div id="detail-page" class="hidden">
        <div class="detail-top"><button id="detail-back" type="button">&larr; Back</button></div>
        <div id="detail-content"></div>
    </div>
```

- [ ] **Step 2: Replace `showPackageDetails`/`hideDetails` with the full-page version in `appstore.js`**

Replace the entire `// --- Details panel ---` section — `showPackageDetails` (lines ~254-330), `hideDetails` (~388-397), and `selectCard`/`selectedCard` usage — with:

```javascript
// --- Detail page ---

var detailReturnScroll = 0;

function detailThumbsHtml(urls) {
    if (urls.length < 2) return "";
    var items = urls.map(function(u, i) {
        return '<div class="detail-thumb' + (i === 0 ? ' on' : '') + '" data-i="' + i +
            '"><img src="' + escapeAttr(u) + '"></div>';
    }).join("");
    return '<div class="detail-thumbs">' + items + '</div>';
}

function factRow(label, value) {
    return '<div class="detail-fact"><label>' + escapeHtml(label) + '</label><span>' + value + '</span></div>';
}

function detailActionsHtml(pkg, status, latest) {
    var name = escapeAttr(pkg.name);
    if (!latest) return "";
    var ver = escapeHtml(latest.version);
    if (status === "installed") {
        return '<button class="detail-btn installed" disabled>Installed ✓</button>' +
            '<button class="detail-btn uninstall" id="uninstall-btn" data-name="' + name + '">Uninstall</button>';
    }
    if (status === "update-available") {
        return '<button class="detail-btn update" id="install-btn" data-name="' + name + '">Update to v' + ver + '</button>' +
            '<button class="detail-btn uninstall" id="uninstall-btn" data-name="' + name + '">Uninstall</button>';
    }
    return '<button class="detail-btn install" id="install-btn" data-name="' + name + '">Install</button>';
}

function showPackageDetails(pkg) {
    var type = pkg.type || "plugin";
    var latest = latestVersion(pkg);
    var versionStr = latest ? latest.version : "—";
    var compatStr = latest && latest.sciqlop ? latest.sciqlop : "—";
    var status = installStatus(pkg);
    var installedVer = installedVersions[pkg.name] || null;
    var shots = screenshotUrls(pkg);
    var tagsHtml = (pkg.tags || []).join(" · ") || "—";
    var starsHtml = pkg.stars != null ? "★ " + pkg.stars : "—";

    var carousel = shots.length > 0
        ? renderCarousel(shots) + detailThumbsHtml(shots)
        : '<div class="detail-noshot">' + escapeHtml((pkg.name || "?").charAt(0).toUpperCase()) + '</div>';

    var facts = factRow("Type", '<span class="card-badge">' + escapeHtml(type) + '</span>') +
        factRow("Author", escapeHtml(pkg.author || "—")) +
        factRow("License", escapeHtml(pkg.license || "—")) +
        factRow("Version", escapeHtml(versionStr)) +
        (installedVer ? factRow("Installed", "v" + escapeHtml(installedVer)) : "") +
        factRow("Requires", "SciQLop " + escapeHtml(compatStr)) +
        factRow("Stars", escapeHtml(starsHtml)) +
        factRow("Tags", escapeHtml(tagsHtml));

    document.getElementById("detail-content").innerHTML =
        '<div class="detail-grid">' +
            '<div class="detail-media">' + carousel + '</div>' +
            '<div class="detail-side">' +
                '<h2>' + escapeHtml(pkg.name) + '</h2>' +
                '<div class="detail-author">by ' + escapeHtml(pkg.author || "—") + '</div>' +
                '<div class="detail-actions">' + detailActionsHtml(pkg, status, latest) + '</div>' +
                '<div class="detail-facts">' + facts + '</div>' +
            '</div>' +
            '<div class="detail-desc">' + escapeHtml(pkg.description || "") + '</div>' +
        '</div>';

    wireDetailActions();
    initCarousel(document.getElementById("detail-content"));
    initDetailThumbs();
    openDetailPage();
}

function wireDetailActions() {
    var btn = document.getElementById("install-btn");
    if (btn) {
        btn.addEventListener("click", function() {
            clearInstallError();
            btn.textContent = "Installing...";
            btn.disabled = true;
            backend.install_package(btn.dataset.name);
        });
    }
    var unBtn = document.getElementById("uninstall-btn");
    if (unBtn) {
        unBtn.addEventListener("click", function() {
            clearInstallError();
            unBtn.textContent = "Uninstalling...";
            unBtn.disabled = true;
            backend.uninstall_package(unBtn.dataset.name);
        });
    }
}

function initDetailThumbs() {
    var root = document.getElementById("detail-content");
    var thumbs = root.querySelectorAll(".detail-thumb");
    var slides = root.querySelectorAll(".carousel-slide");
    thumbs.forEach(function(thumb) {
        thumb.addEventListener("click", function() {
            var i = parseInt(thumb.dataset.i, 10);
            slides.forEach(function(s, idx) { s.classList.toggle("active", idx === i); });
            root.querySelectorAll(".carousel-dot").forEach(function(d, idx) { d.classList.toggle("active", idx === i); });
            thumbs.forEach(function(t, idx) { t.classList.toggle("on", idx === i); });
        });
    });
}

function openDetailPage() {
    detailReturnScroll = window.scrollY;
    document.body.classList.add("detail-open");
    document.getElementById("detail-page").classList.remove("hidden");
    window.scrollTo(0, 0);
}

function hideDetails() {
    document.getElementById("detail-page").classList.add("hidden");
    document.body.classList.remove("detail-open");
    window.scrollTo(0, detailReturnScroll);
}
```

Remove the now-unused `selectCard`, `selectedCard`, and `statusLabel` (no longer referenced — tiles and hero call `showPackageDetails` directly). In `createTile` (Task 1), simplify the click handler to:

```javascript
    tile.addEventListener("click", function() { showPackageDetails(pkg); });
```

And in `drawHero` (Task 3), replace `selectCard(null); showPackageDetails(pkg);` with just:

```javascript
        showPackageDetails(pkg);
```

- [ ] **Step 3: Wire the Back button and remove the old close handler in `appstore.js`**

In `DOMContentLoaded`, replace the line wiring `details-close` (line ~440) with:

```javascript
    document.getElementById("detail-back").addEventListener("click", hideDetails);
```

The Escape-key handler (lines ~444-452) already calls `hideDetails()` for the non-lightbox case — leave it. Update its lightbox-vs-detail check to reference the new id where needed: it checks `#lightbox` then calls `hideDetails()`, which is correct unchanged.

- [ ] **Step 4: Swap side-panel CSS for detail-page CSS in `appstore.css`**

Remove the `body.details-open` rule (lines ~17-20) and the entire `/* --- Details panel --- */` block (lines ~231-360, from `#details-panel` through `.details-actions button:disabled`). Keep `.install-error`. Add a new detail-page block before `/* --- Lightbox --- */`:

```css
/* --- Detail page --- */

#detail-page {
    position: absolute;
    inset: 0;
    background: var(--WelcomeBackground, var(--Base));
    padding: 16px;
    overflow-y: auto;
    z-index: 20;
}

#detail-page.hidden { display: none; }
body.detail-open { overflow: hidden; }

.detail-top { margin-bottom: 14px; }

#detail-back {
    font-size: 0.9em;
    color: var(--Text);
    background: var(--Window);
    border: 1px solid var(--Borders);
    border-radius: 6px;
    padding: 6px 14px;
    cursor: pointer;
}

#detail-back:hover { background: var(--AlternateBase); }

.detail-grid {
    display: grid;
    grid-template-columns: 1.6fr 1fr;
    gap: 24px;
    max-width: 1100px;
}

.detail-media .carousel { margin-bottom: 8px; }

.detail-noshot {
    aspect-ratio: 16 / 9;
    display: flex; align-items: center; justify-content: center;
    font-size: 4em; font-weight: 700; color: #cdd9ec;
    background: linear-gradient(135deg, #2a3550, #1d2533);
    border-radius: 8px;
}

.detail-thumbs { display: flex; gap: 8px; flex-wrap: wrap; }
.detail-thumb {
    width: 72px; height: 44px; border-radius: 5px; overflow: hidden;
    border: 1px solid var(--Borders); cursor: pointer; background: var(--AlternateBase);
}
.detail-thumb.on { border-color: var(--Highlight); }
.detail-thumb img { width: 100%; height: 100%; object-fit: cover; }

.detail-side h2 { font-size: 1.5em; }
.detail-author { color: var(--UnselectedText); font-size: 0.9em; margin: 2px 0 14px; }

.detail-actions { display: flex; flex-direction: column; gap: 8px; }
.detail-btn {
    padding: 9px 16px; border: 1px solid var(--Borders); border-radius: 8px;
    background: var(--Button); color: var(--ButtonText); cursor: pointer; font-size: 0.92em;
}
.detail-btn.install, .detail-btn.update { background: var(--Highlight); color: var(--HighlightedText); border-color: var(--Highlight); }
.detail-btn.installed { background: #2ea043; color: #fff; border-color: #2ea043; cursor: default; }
.detail-btn.uninstall { background: #da363490; color: #fff; border-color: #da3634; }
.detail-btn:disabled { opacity: 0.6; cursor: wait; }

.detail-facts { margin-top: 16px; border-top: 1px solid var(--Borders); padding-top: 12px; }
.detail-fact { display: flex; justify-content: space-between; gap: 12px; font-size: 0.85em; padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
.detail-fact label { color: var(--UnselectedText); }
.detail-fact span { text-align: right; }

.detail-desc {
    grid-column: 1 / -1;
    font-size: 0.9em; color: var(--Text); line-height: 1.55;
    border-top: 1px solid var(--Borders); padding-top: 14px;
}
```

- [ ] **Step 5: Launch and verify**

Run: `uv run sciqlop` → Plugin Store.
Expected: clicking any tile (or the hero) opens a full-page view that covers the grid; a "← Back" button returns to the previous page at the prior scroll position; Radio Dynamic Spectra shows a screenshot carousel with a thumbnail strip and clicking a screenshot opens the lightbox; image-less entries show a large initial block; Install / Update / Uninstall buttons work and the success state updates; the install-error box still appears on failure.

- [ ] **Step 6: Run the regression guard**

Run: `uv run pytest --no-xvfb tests/test_appstore_index.py tests/test_appstore_install.py tests/test_web_channel_page.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add SciQLop/components/appstore/resources/appstore.html.j2 SciQLop/components/appstore/resources/appstore.js SciQLop/components/appstore/resources/appstore.css
git commit -m "feat(appstore): full-page app detail view replaces side panel"
```

---

## Task 6: Cleanup, dead-code removal, and final verification

Remove any now-unused code, confirm the whole flow, and ensure the install/uninstall result handlers still re-render correctly into the detail page.

**Files:**
- Modify: `SciQLop/components/appstore/resources/appstore.js` (prune dead code, verify `onInstallFinished`/`onUninstallFinished`)
- Modify: `SciQLop/components/appstore/resources/appstore.css` (drop leftover `.card*` / `.tab*` rules if any remain)

- [ ] **Step 1: Confirm result handlers target the detail page**

In `appstore.js`, verify `onInstallFinished` and `onUninstallFinished` (they re-query `#install-btn` / `#uninstall-btn` by id and call `renderCards()`). They work unchanged because the detail page reuses the same button ids. Confirm `showInstallError` finds `.detail-actions` — it inserts after `.details-actions`. **Update** the selector in `showInstallError` (line ~360) from `.details-actions` to `.detail-actions`:

```javascript
    var actions = document.querySelector(".detail-actions");
```

- [ ] **Step 2: Remove dead code in `appstore.js`**

Grep for and delete anything no longer referenced: `TYPE_ICONS` (replaced by gradient fallback), `createPackageCard` (replaced), `statusLabel`, `selectCard`, `selectedCard`, and the `card-image*`/`card-body`/`card-name`/`card-meta` strings. Run:

```bash
grep -n "TYPE_ICONS\|createPackageCard\|statusLabel\|selectedCard\|selectCard" SciQLop/components/appstore/resources/appstore.js
```
Expected after cleanup: no matches.

- [ ] **Step 3: Remove leftover CSS**

Run:
```bash
grep -n "details-panel\|details-open\|\.tab\b\|card-image\|card-name\|card-meta\|card-body" SciQLop/components/appstore/resources/appstore.css
```
Expected: no matches except `.card-badge` (still used for the Type pill in facts and section badges). Delete any other leftover rules.

- [ ] **Step 4: Full manual verification pass**

Run: `uv run sciqlop` → Plugin Store. Walk the full checklist from the spec:
- Explore: hero rotates through image entries only; sections grouped by type; image-less tiles show gradient-initial.
- Click a tile → full-page detail with working carousel + lightbox; Back restores scroll.
- Install an entry → button shows Installed ✓; Installed page now lists it.
- Updates page lists update-available entries with an Update button and a nav count.
- Search collapses Explore to a flat grid and hides the hero; clearing restores it.
- Toggle light/dark theme → store re-renders and is legible in both.

- [ ] **Step 5: Run the full regression guard**

Run: `uv run pytest --no-xvfb tests/test_appstore_index.py tests/test_appstore_install.py tests/test_web_channel_page.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add SciQLop/components/appstore/resources/appstore.js SciQLop/components/appstore/resources/appstore.css
git commit -m "refactor(appstore): remove dead card/tab code after GNOME redesign"
```

---

## Self-review checklist (completed by plan author)

- **Spec coverage:** page model (Task 4) ✓, hero auto-from-images (Task 3) ✓, type sections (Task 2) ✓, image-forward tile + gradient fallback (Task 1) ✓, full-page detail reusing carousel/lightbox/handlers (Task 5) ✓, search collapse (Task 4/6) ✓, theming via palette vars (all tasks) ✓, backend untouched + regression guard (every task) ✓.
- **Placeholder scan:** no TBD/TODO; every code step shows complete code.
- **Type consistency:** `createTile`/`placeholderTile`/`tileShot`/`tileHue`, `renderHero`/`drawHero`/`featuredPackages`, `renderSection`/`filterPackages`/`sortPackages`/`appendTiles`, `showPackageDetails`/`hideDetails`/`openDetailPage`/`wireDetailActions`/`initDetailThumbs`, `activePage`/`pageSubset`/`updateUpdatesCount` used consistently across tasks. `showInstallError` selector corrected in Task 6.
```
