var backend = null;
var selectedCard = null;
var allPackages = [];
var installedVersions = {};
var activeTags = new Set();
var activeCategory = "";
var activeSort = "stars";
var heroTimer = null;
var heroIndex = 0;

var TYPE_ICONS = {plugin: "\uD83D\uDD0C", workspace: "\uD83D\uDCC1", template: "\uD83D\uDCC4", example: "\uD83D\uDCD6"};

// --- Initialization ---

function init() {
    new QWebChannel(qt.webChannelTransport, function(channel) {
        backend = channel.objects.backend;
        backend.packages_ready.connect(onPackagesReady);
        backend.install_finished.connect(onInstallFinished);
        backend.uninstall_finished.connect(onUninstallFinished);
        backend.fetch_packages();
    });
}

// --- Data loading ---

function onPackagesReady(json_str) {
    allPackages = JSON.parse(json_str);
    document.getElementById("loading").style.display = "none";
    refreshInstalledVersions();
    loadTags();
}

function refreshInstalledVersions() {
    backend.get_installed_versions(function(json_str) {
        installedVersions = JSON.parse(json_str);
        renderCards();
    });
}

function loadTags() {
    backend.list_tags(function(json_str) {
        var tags = JSON.parse(json_str);
        var container = document.getElementById("tag-chips");
        container.innerHTML = "";
        tags.forEach(function(tag) {
            var chip = document.createElement("span");
            chip.className = "tag-chip";
            chip.textContent = tag;
            chip.dataset.tag = tag;
            chip.addEventListener("click", function() {
                if (activeTags.has(tag)) {
                    activeTags.delete(tag);
                    chip.classList.remove("active");
                } else {
                    activeTags.add(tag);
                    chip.classList.add("active");
                }
                renderCards();
            });
            container.appendChild(chip);
        });
    });
}

// --- Install status helpers ---

function installStatus(pkg) {
    var installed = installedVersions[pkg.name];
    if (!installed) return "not-installed";
    var versions = pkg.versions || [];
    if (!versions.length) return "installed";
    var latest = versions[versions.length - 1].version;
    return installed === latest ? "installed" : "update-available";
}

function statusLabel(status, installedVer) {
    if (status === "installed") return "Installed \u2713";
    if (status === "update-available") return "Update (v" + installedVer + " installed)";
    return "";
}

// --- Rendering ---

function latestVersion(pkg) {
    var versions = pkg.versions || [];
    return versions.length > 0 ? versions[versions.length - 1] : null;
}

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

function renderCards() {
    var query = (document.getElementById("search-input").value || "").toLowerCase();
    var container = document.getElementById("package-cards");
    container.innerHTML = "";
    renderHero();
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
    var starsHtml = pkg.stars != null ? "\u2605 " + pkg.stars : "\u2605 \u2014";
    var footer = [starsHtml, pkg.license || "\u2014", versionStr ? "v" + versionStr : ""]
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

// --- Carousel ---

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

    function dropSlide(slide) {
        slide.remove();
        // Dots are positional indicators; drop one (the last) to keep dot
        // count == slide count, robust to any number/order of failures.
        var allDots = carousel.querySelectorAll(".carousel-dot");
        if (allDots.length > 0) allDots[allDots.length - 1].remove();
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
    slides.forEach(function(slide) {
        slide.addEventListener("click", function() { openLightbox(slide.src); });
        slide.addEventListener("error", function() { dropSlide(slide); });
    });
}

// --- Details panel ---

function showPackageDetails(pkg) {
    var panel = document.getElementById("details-panel");
    document.getElementById("details-title").textContent = pkg.name;

    var type = pkg.type || "plugin";
    var latest = latestVersion(pkg);
    var versionStr = latest ? latest.version : "\u2014";
    var compatStr = latest ? latest.sciqlop : "\u2014";
    var status = installStatus(pkg);
    var installedVer = installedVersions[pkg.name] || null;

    var tagsHtml = (pkg.tags || []).map(function(t) {
        return '<span class="card-badge">' + escapeHtml(t) + '</span>';
    }).join(" ");

    var starsHtml = pkg.stars != null ? '\u2B50 ' + pkg.stars : "\u2014";

    var installedHtml = "";
    if (installedVer) {
        installedHtml = '<div class="details-field"><label>Installed</label><span>v' + escapeHtml(installedVer) + '</span></div>';
    }

    var buttonHtml = "";
    if (latest) {
        if (status === "installed") {
            buttonHtml = '<button class="install installed" disabled>Installed \u2713</button>' +
                '<button class="install uninstall" id="uninstall-btn" data-name="' + escapeHtml(pkg.name) + '">Uninstall</button>';
        } else if (status === "update-available") {
            buttonHtml = '<button class="install update" id="install-btn" data-name="' + escapeHtml(pkg.name) + '">Update to v' + escapeHtml(versionStr) + '</button>' +
                '<button class="install uninstall" id="uninstall-btn" data-name="' + escapeHtml(pkg.name) + '">Uninstall</button>';
        } else {
            buttonHtml = '<button class="install" id="install-btn" data-name="' + escapeHtml(pkg.name) + '">Install</button>';
        }
    }

    var content = document.getElementById("details-content");
    content.innerHTML =
        renderCarousel(screenshotUrls(pkg)) +
        '<div class="details-field"><label>Type</label><span><span class="card-badge">' + escapeHtml(type) + '</span></span></div>' +
        '<div class="details-field"><label>Author</label><span>' + escapeHtml(pkg.author) + '</span></div>' +
        '<div class="details-field"><label>License</label><span>' + escapeHtml(pkg.license || "\u2014") + '</span></div>' +
        '<div class="details-field"><label>Version</label><span>' + escapeHtml(versionStr) + '</span></div>' +
        installedHtml +
        (latest ? '<div class="details-field"><label>Requires</label><span>SciQLop ' + escapeHtml(compatStr) + '</span></div>' : '') +
        '<div class="details-field"><label>Description</label><span>' + escapeHtml(pkg.description) + '</span></div>' +
        '<div class="details-field"><label>Tags</label><span>' + tagsHtml + '</span></div>' +
        '<div class="details-field"><label>Stars</label><span>' + starsHtml + '</span></div>' +
        '<div class="details-actions">' + buttonHtml + '</div>';

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

    initCarousel(content);

    panel.classList.remove("hidden");
    panel.classList.add("visible");
    document.body.classList.add("details-open");
}

function onInstallFinished(json_str) {
    var result = JSON.parse(json_str);
    if (result.ok && result.version) {
        installedVersions[result.name] = result.version;
    }
    renderCards();
    var btn = document.getElementById("install-btn");
    if (!btn) return;
    if (result.ok) {
        btn.textContent = "Installed \u2713";
        btn.className = "install installed";
        btn.disabled = true;
        clearInstallError();
    } else {
        btn.textContent = "Failed";
        btn.disabled = false;
        showInstallError(result.error);
    }
}

function clearInstallError() {
    var box = document.getElementById("install-error");
    if (box) box.remove();
}

function showInstallError(message) {
    clearInstallError();
    if (!message) return;
    var actions = document.querySelector(".details-actions");
    if (!actions) return;
    var box = document.createElement("pre");
    box.id = "install-error";
    box.className = "install-error";
    box.textContent = message;
    actions.parentNode.insertBefore(box, actions.nextSibling);
}

function onUninstallFinished(json_str) {
    var result = JSON.parse(json_str);
    if (result.ok) {
        delete installedVersions[result.name];
    }
    renderCards();
    var unBtn = document.getElementById("uninstall-btn");
    if (!unBtn) return;
    if (result.ok) {
        unBtn.textContent = "Uninstalled";
        unBtn.disabled = true;
        clearInstallError();
    } else {
        unBtn.textContent = "Failed";
        unBtn.disabled = false;
        showInstallError(result.error);
    }
}

function hideDetails() {
    var panel = document.getElementById("details-panel");
    panel.classList.remove("visible");
    panel.classList.add("hidden");
    document.body.classList.remove("details-open");
    if (selectedCard) {
        selectedCard.classList.remove("selected");
        selectedCard = null;
    }
}

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

// --- Selection ---

function selectCard(card) {
    if (selectedCard) selectedCard.classList.remove("selected");
    selectedCard = card;
    if (card) card.classList.add("selected");
}

// --- Event listeners ---

document.addEventListener("DOMContentLoaded", function() {
    document.querySelectorAll(".tab").forEach(function(tab) {
        tab.addEventListener("click", function() {
            document.querySelector(".tab.active").classList.remove("active");
            tab.classList.add("active");
            activeCategory = tab.dataset.category;
            renderCards();
        });
    });

    document.getElementById("search-input").addEventListener("input", function() {
        renderCards();
    });

    document.getElementById("sort-select").addEventListener("change", function() {
        activeSort = this.value;
        renderCards();
    });

    document.getElementById("details-close").addEventListener("click", hideDetails);

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

    document.body.addEventListener("click", function(e) {
        if (!e.target.closest(".tile, #details-panel, #lightbox, .tag-chip, .tab, #toolbar")) {
            hideDetails();
        }
    });
});

// --- Utilities ---

function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

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

// --- Start ---
init();
