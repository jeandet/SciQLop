# AppStore Plugin Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render an optional plugin card thumbnail and a GNOME-style screenshot carousel (with click-to-enlarge lightbox) in the SciQLop Plugin Store, driven by optional `image`/`screenshots` URL fields in the appstore `index.json`.

**Architecture:** Front-end only. The store page is a Jinja2-templated HTML/CSS/JS page in a `QWebEngineView`. The backend already passes whole `index.json` dicts through to JS untouched, so the new fields need no backend code — only a guard test. All work is in `SciQLop/components/appstore/resources/{appstore.js,appstore.css,appstore.html.j2}` plus one Python test.

**Tech Stack:** Python 3.13 / PySide6 (QWebEngine + QWebChannel), Jinja2, vanilla ES5-style JS (matches the existing file), pytest.

---

## Background the engineer needs

- The page is loaded with `setHtml(html, file://…base)` (`SciQLop/core/web_channel_page.py:51`). Resources (`appstore.css`, `appstore.js`) load from disk at runtime — **no build/bake step**; edits take effect on next app launch.
- `index.json` is fetched and parsed with plain `json.loads`; `_filter_packages` does `dict(pkg)` and only overrides `versions`, so unknown keys (`image`, `screenshots`) already flow through to JS. **Do not add backend parsing.**
- The JS file ends with a bare `init()` call that needs the Qt `QWebChannel`, so the file cannot be imported/run in Node — only `node --check` (syntax) is available. There is no JS test harness in this repo (consistent with the welcome page). Rendering is confirmed manually in the running app.
- Existing JS conventions in `appstore.js`: ES5 (`var`, `function`), string `innerHTML` building, an `escapeHtml(str)` helper at the bottom, a `TYPE_ICONS` map, `selectedCard` global, `hideDetails()`, and a keydown handler already wired for Escape.
- The resolution rules (apply consistently):
  - **card thumbnail** = `image` → else `screenshots[0]` → else emoji placeholder.
  - **carousel list** = `screenshots` → else `[image]` if only `image` → else no carousel.

---

## Task 1: Backend pass-through guard test

Pins that `_filter_packages` preserves `image`/`screenshots`, so a future refactor can't silently drop them. (No production code changes — these keys already pass through; this is a characterization/guard test that should pass immediately.)

**Files:**
- Create: `tests/test_appstore_index.py`

- [ ] **Step 1: Write the test**

```python
"""The appstore index pass-through must preserve optional media fields.

`image` and `screenshots` are optional URL fields the client renders (card
thumbnail + screenshot carousel). `_filter_packages` only narrows `versions`;
it must keep every other key so the JS can read these. This guards against a
future refactor that whitelists keys and silently drops media.
"""
from SciQLop.components.appstore.backend import _filter_packages


def _entry(**extra):
    base = {
        "name": "Demo",
        "type": "plugin",
        "versions": [{"version": "1.0.0", "sciqlop": ""}],
    }
    base.update(extra)
    return base


def test_image_and_screenshots_preserved():
    pkg = _entry(
        image="https://example.com/card.png",
        screenshots=["https://example.com/01.png", "https://example.com/02.png"],
    )
    out = _filter_packages([pkg])
    assert len(out) == 1
    assert out[0]["image"] == "https://example.com/card.png"
    assert out[0]["screenshots"] == ["https://example.com/01.png", "https://example.com/02.png"]


def test_missing_media_fields_are_simply_absent():
    out = _filter_packages([_entry()])
    assert len(out) == 1
    assert "image" not in out[0]
    assert "screenshots" not in out[0]
```

- [ ] **Step 2: Run the test, verify it passes**

Run: `uv run pytest tests/test_appstore_index.py -v`
Expected: 2 passed. (If it fails, the backend is dropping keys — fix `_filter_packages` to keep them, do not change the test.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_appstore_index.py
git commit -m "test(appstore): guard that index pass-through keeps image/screenshots"
```

---

## Task 2: JS media-URL resolver helpers

Add the pure resolution helpers and an attribute-escaper. No behavior change yet — wired in later tasks.

**Files:**
- Modify: `SciQLop/components/appstore/resources/appstore.js` (add helpers near the bottom, beside `escapeHtml`)

- [ ] **Step 1: Add the helpers**

Find the `escapeHtml` function near the end of the file:

```javascript
function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
```

Add immediately after it:

```javascript
function escapeAttr(str) {
    return escapeHtml(str).replace(/"/g, "&quot;");
}

// Card thumbnail: explicit image, else first screenshot, else null (emoji).
function cardImageUrl(pkg) {
    if (pkg.image) return pkg.image;
    var shots = pkg.screenshots || [];
    return shots.length > 0 ? shots[0] : null;
}

// Carousel list: screenshots if any, else the single image, else empty.
function screenshotUrls(pkg) {
    var shots = pkg.screenshots || [];
    if (shots.length > 0) return shots.slice();
    return pkg.image ? [pkg.image] : [];
}
```

- [ ] **Step 2: Syntax check**

Run: `node --check SciQLop/components/appstore/resources/appstore.js`
Expected: no output (exit 0).

- [ ] **Step 3: Commit**

```bash
git add SciQLop/components/appstore/resources/appstore.js
git commit -m "feat(appstore): add media-url resolver helpers"
```

---

## Task 3: Card thumbnail

Render the plugin image into the card, falling back to the emoji placeholder on missing or broken images.

**Files:**
- Modify: `SciQLop/components/appstore/resources/appstore.js` (`createPackageCard`)

The current function builds the image slot like this:

```javascript
    var type = pkg.type || "plugin";
    var icon = TYPE_ICONS[type] || "📦";
    var latest = latestVersion(pkg);
```

…and later:

```javascript
    card.innerHTML =
        '<div class="card-image-wrapper"><div class="card-image placeholder">' + icon + '</div></div>' +
        '<div class="card-body">' +
```

…and ends with:

```javascript
    card.addEventListener("click", function() {
        // Clicking the already-selected card toggles the details panel closed.
        if (card === selectedCard) {
            hideDetails();
            return;
        }
        selectCard(card);
        showPackageDetails(pkg);
    });
    return card;
```

- [ ] **Step 1: Build the image slot from the resolved URL**

Replace this line:

```javascript
    card.innerHTML =
        '<div class="card-image-wrapper"><div class="card-image placeholder">' + icon + '</div></div>' +
```

with:

```javascript
    var thumbUrl = cardImageUrl(pkg);
    var imageInner = thumbUrl
        ? '<img class="card-image" src="' + escapeAttr(thumbUrl) + '">'
        : '<div class="card-image placeholder">' + icon + '</div>';
    card.innerHTML =
        '<div class="card-image-wrapper">' + imageInner + '</div>' +
```

- [ ] **Step 2: Attach the broken-image fallback**

Immediately before `card.addEventListener("click", …)` (the block shown above), insert:

```javascript
    var thumbEl = card.querySelector("img.card-image");
    if (thumbEl) {
        thumbEl.addEventListener("error", function() {
            var wrap = thumbEl.parentNode;
            if (wrap) wrap.innerHTML = '<div class="card-image placeholder">' + icon + '</div>';
        });
    }

```

- [ ] **Step 3: Syntax check**

Run: `node --check SciQLop/components/appstore/resources/appstore.js`
Expected: no output (exit 0).

- [ ] **Step 4: Commit**

```bash
git add SciQLop/components/appstore/resources/appstore.js
git commit -m "feat(appstore): show plugin image as card thumbnail with emoji fallback"
```

---

## Task 4: Lightbox overlay

A fullscreen overlay that shows a single screenshot enlarged; dismissed by click or Escape. Built before the carousel because carousel slides open it.

**Files:**
- Modify: `SciQLop/components/appstore/resources/appstore.html.j2`
- Modify: `SciQLop/components/appstore/resources/appstore.css`
- Modify: `SciQLop/components/appstore/resources/appstore.js`

- [ ] **Step 1: Add the overlay container to the template**

In `appstore.html.j2`, find:

```html
    <script src="appstore.js"></script>
</body>
```

Replace with:

```html
    <div id="lightbox" class="hidden">
        <img id="lightbox-img" alt="">
    </div>

    <script src="appstore.js"></script>
</body>
```

- [ ] **Step 2: Add the lightbox styles**

Append to the end of `appstore.css`:

```css
/* --- Lightbox --- */

#lightbox {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    cursor: zoom-out;
}

#lightbox.hidden {
    display: none;
}

#lightbox img {
    max-width: 92vw;
    max-height: 92vh;
    object-fit: contain;
    border-radius: 4px;
    box-shadow: 0 6px 30px rgba(0, 0, 0, 0.6);
}
```

- [ ] **Step 3: Add open/close functions**

In `appstore.js`, after the `hideDetails()` function, add:

```javascript
function openLightbox(src) {
    var lb = document.getElementById("lightbox");
    document.getElementById("lightbox-img").src = src;
    lb.classList.remove("hidden");
}

function closeLightbox() {
    var lb = document.getElementById("lightbox");
    lb.classList.add("hidden");
    document.getElementById("lightbox-img").src = "";
}
```

- [ ] **Step 4: Wire dismissal (click + Escape)**

In the `DOMContentLoaded` listener, find the Escape handler added previously:

```javascript
    document.addEventListener("keydown", function(e) {
        if (e.key === "Escape") hideDetails();
    });
```

Replace it with:

```javascript
    document.getElementById("lightbox").addEventListener("click", closeLightbox);

    document.addEventListener("keydown", function(e) {
        if (e.key !== "Escape") return;
        var lb = document.getElementById("lightbox");
        if (lb && !lb.classList.contains("hidden")) {
            closeLightbox();
            return;
        }
        hideDetails();
    });
```

- [ ] **Step 5: Syntax check**

Run: `node --check SciQLop/components/appstore/resources/appstore.js`
Expected: no output (exit 0).

- [ ] **Step 6: Commit**

```bash
git add SciQLop/components/appstore/resources/appstore.html.j2 SciQLop/components/appstore/resources/appstore.css SciQLop/components/appstore/resources/appstore.js
git commit -m "feat(appstore): add screenshot lightbox overlay"
```

---

## Task 5: Screenshot carousel in the details panel

Render a carousel at the top of the details content: one image at a time, ‹ › arrows + dots (only when >1), click-to-enlarge via the lightbox, and broken-slide pruning.

**Files:**
- Modify: `SciQLop/components/appstore/resources/appstore.css`
- Modify: `SciQLop/components/appstore/resources/appstore.js` (`renderCarousel`, `initCarousel`, and `showPackageDetails`)

- [ ] **Step 1: Add carousel styles**

Append to the end of `appstore.css`:

```css
/* --- Screenshot carousel --- */

.carousel {
    margin-bottom: 16px;
}

.carousel-viewport {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #000;
    border-radius: 4px;
    overflow: hidden;
}

.carousel-slide {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: none;
    cursor: zoom-in;
}

.carousel-slide.active {
    display: block;
}

.carousel-arrow {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 28px;
    height: 28px;
    border: none;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.5);
    color: #fff;
    font-size: 1.2em;
    line-height: 1;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
}

.carousel-arrow:hover {
    background: rgba(0, 0, 0, 0.78);
}

.carousel-arrow.prev { left: 8px; }
.carousel-arrow.next { right: 8px; }

.carousel-dots {
    display: flex;
    gap: 6px;
    justify-content: center;
    margin-top: 8px;
}

.carousel-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--Borders);
    cursor: pointer;
}

.carousel-dot.active {
    background: var(--Highlight);
}
```

- [ ] **Step 2: Add the carousel render + init functions**

In `appstore.js`, add these two functions just before `function showPackageDetails(`:

```javascript
function renderCarousel(urls) {
    if (urls.length === 0) return "";
    var slides = urls.map(function(u, i) {
        return '<img class="carousel-slide' + (i === 0 ? ' active' : '') +
               '" src="' + escapeAttr(u) + '">';
    }).join("");
    var nav = "";
    var dots = "";
    if (urls.length > 1) {
        nav = '<button class="carousel-arrow prev" data-dir="-1" aria-label="Previous">‹</button>' +
              '<button class="carousel-arrow next" data-dir="1" aria-label="Next">›</button>';
        dots = '<div class="carousel-dots">' + urls.map(function(u, i) {
            return '<span class="carousel-dot' + (i === 0 ? ' active' : '') + '"></span>';
        }).join("") + '</div>';
    }
    return '<div class="carousel" id="carousel">' +
               '<div class="carousel-viewport">' + slides + nav + '</div>' +
               dots +
           '</div>';
}

function initCarousel(root) {
    var carousel = root.querySelector("#carousel");
    if (!carousel) return;
    var slides = carousel.querySelectorAll(".carousel-slide");
    var dots = carousel.querySelectorAll(".carousel-dot");
    var current = 0;

    function show(i) {
        if (slides.length === 0) return;
        current = (i + slides.length) % slides.length;
        slides.forEach(function(s, idx) { s.classList.toggle("active", idx === current); });
        dots.forEach(function(d, idx) { d.classList.toggle("active", idx === current); });
    }

    function dropSlide(slide, idx) {
        slide.remove();
        if (dots[idx]) dots[idx].remove();
        slides = carousel.querySelectorAll(".carousel-slide");
        dots = carousel.querySelectorAll(".carousel-dot");
        if (slides.length === 0) {
            carousel.style.display = "none";
            return;
        }
        if (slides.length === 1) {
            carousel.querySelectorAll(".carousel-arrow").forEach(function(a) { a.style.display = "none"; });
            var dotsWrap = carousel.querySelector(".carousel-dots");
            if (dotsWrap) dotsWrap.style.display = "none";
        }
        show(Math.min(current, slides.length - 1));
    }

    carousel.querySelectorAll(".carousel-arrow").forEach(function(btn) {
        btn.addEventListener("click", function(e) {
            e.stopPropagation();
            show(current + parseInt(btn.dataset.dir, 10));
        });
    });
    dots.forEach(function(dot, idx) {
        dot.addEventListener("click", function() { show(idx); });
    });
    slides.forEach(function(slide, idx) {
        slide.addEventListener("click", function() { openLightbox(slide.src); });
        slide.addEventListener("error", function() { dropSlide(slide, idx); });
    });
}
```

- [ ] **Step 3: Insert the carousel at the top of the details content**

In `showPackageDetails`, find:

```javascript
    var content = document.getElementById("details-content");
    content.innerHTML =
        '<div class="details-field"><label>Type</label><span><span class="card-badge">' + escapeHtml(type) + '</span></span></div>' +
```

Replace the first two lines (up to and including `content.innerHTML =`) with:

```javascript
    var content = document.getElementById("details-content");
    content.innerHTML =
        renderCarousel(screenshotUrls(pkg)) +
        '<div class="details-field"><label>Type</label><span><span class="card-badge">' + escapeHtml(type) + '</span></span></div>' +
```

- [ ] **Step 4: Initialize the carousel after the content is rendered**

Still in `showPackageDetails`, find the end where the panel is shown:

```javascript
    panel.classList.remove("hidden");
    panel.classList.add("visible");
    document.body.classList.add("details-open");
}
```

Replace with:

```javascript
    initCarousel(content);

    panel.classList.remove("hidden");
    panel.classList.add("visible");
    document.body.classList.add("details-open");
}
```

- [ ] **Step 5: Syntax check**

Run: `node --check SciQLop/components/appstore/resources/appstore.js`
Expected: no output (exit 0).

- [ ] **Step 6: Commit**

```bash
git add SciQLop/components/appstore/resources/appstore.css SciQLop/components/appstore/resources/appstore.js
git commit -m "feat(appstore): screenshot carousel in plugin details panel"
```

---

## Task 6: Full-suite regression + manual verification

- [ ] **Step 1: Run the appstore test files**

Run: `uv run pytest tests/test_appstore_index.py tests/test_appstore_install.py -v`
Expected: all pass.

- [ ] **Step 2: Final JS syntax check**

Run: `node --check SciQLop/components/appstore/resources/appstore.js`
Expected: no output (exit 0).

- [ ] **Step 3: Manual verification in the app**

Launch the app (`uv run sciqlop`), open **Tools → Plugin Store**, and confirm against a registry/test entry carrying `image` + `screenshots`:
  - card shows the thumbnail (not the emoji) when `image`/`screenshots` present;
  - a plugin with no media still shows the emoji card and a details panel with **no** carousel;
  - the details panel shows the carousel at the top; ‹ › arrows and dots navigate; a single screenshot shows no arrows/dots;
  - clicking a screenshot opens the lightbox; click or Esc closes it (and Esc closes the lightbox first, the details panel second);
  - a deliberately broken screenshot URL is pruned (no broken-image glyph); a broken card `image` falls back to the emoji.

No commit (verification only).

---

## Self-review notes

- **Spec coverage:** schema pass-through (Task 1), card thumbnail + fallback (Tasks 2–3), carousel at top + arrows/dots + single-image case + lightbox (Tasks 4–5), failure/degradation (Tasks 3 & 5 onerror handling, Task 6 manual), no backend change (confirmed in Background). All spec sections mapped.
- **No placeholders:** every code step shows complete code.
- **Type/name consistency:** `cardImageUrl`/`screenshotUrls`/`escapeAttr` defined in Task 2 and used in Tasks 3 & 5; `openLightbox`/`closeLightbox` defined in Task 4 and used in Task 5; `#carousel`/`.carousel-slide`/`.carousel-dot`/`.carousel-arrow` consistent between `renderCarousel` (Task 5 Step 2), the CSS (Task 5 Step 1), and `initCarousel` (Task 5 Step 2); `#lightbox`/`#lightbox-img` consistent between template (Task 4 Step 1), CSS (Task 4 Step 2), and JS (Task 4 Steps 3–4).
```
