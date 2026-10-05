(function () {
  "use strict";

  // мобильный сайдбар
  var toggle = document.getElementById("menu-toggle");
  var sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });
    document.addEventListener("click", function (e) {
      if (window.innerWidth > 880) return;
      if (!sidebar.contains(e.target) && e.target !== toggle) {
        sidebar.classList.remove("open");
      }
    });
  }

  // активная заметка — проскроллить к ней в сайдбаре
  var activeLink = sidebar && sidebar.querySelector("a.active");
  if (activeLink) {
    var grp = activeLink.closest("details.nav-group");
    if (grp) grp.open = true;
    activeLink.scrollIntoView({ block: "center" });
  }

  // поиск
  var input = document.getElementById("search");
  var box = document.getElementById("search-results");
  if (!input || !box) return;

  var index = [];
  var loaded = false;
  var selIdx = -1;

  function loadIndex() {
    if (loaded) return Promise.resolve();
    return fetch("assets/search-index.json")
      .then(function (r) { return r.json(); })
      .then(function (data) { index = data; loaded = true; });
  }

  function norm(s) { return (s || "").toLowerCase(); }

  function search(q) {
    var terms = norm(q).split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    var res = [];
    for (var i = 0; i < index.length; i++) {
      var n = index[i];
      var title = norm(n.title);
      var text = norm(n.text);
      var score = 0, ok = true;
      for (var t = 0; t < terms.length; t++) {
        var term = terms[t];
        var inTitle = title.indexOf(term) !== -1;
        var inText = text.indexOf(term) !== -1;
        if (!inTitle && !inText) { ok = false; break; }
        if (inTitle) score += 10;
        if (title.indexOf(term) === 0) score += 5;
        if (inText) score += 1;
      }
      if (ok) res.push({ n: n, score: score });
    }
    res.sort(function (a, b) { return b.score - a.score; });
    return res.slice(0, 25).map(function (x) { return x.n; });
  }

  function snippet(text, q) {
    var terms = norm(q).split(/\s+/).filter(Boolean);
    var lo = norm(text);
    var pos = -1;
    for (var i = 0; i < terms.length; i++) {
      var p = lo.indexOf(terms[i]);
      if (p !== -1 && (pos === -1 || p < pos)) pos = p;
    }
    if (pos === -1) return text.slice(0, 120);
    var start = Math.max(0, pos - 40);
    return (start > 0 ? "…" : "") + text.slice(start, start + 140) + "…";
  }

  function render(results, q) {
    box.innerHTML = "";
    selIdx = -1;
    if (!q.trim()) { box.classList.remove("open"); return; }
    if (!results.length) {
      box.innerHTML = '<div class="sr-empty">Ничего не найдено</div>';
      box.classList.add("open");
      return;
    }
    results.forEach(function (n) {
      var a = document.createElement("a");
      a.href = n.url;
      a.innerHTML =
        '<div class="sr-title"></div>' +
        '<div class="sr-folder"></div>';
      a.querySelector(".sr-title").textContent = n.title;
      a.querySelector(".sr-folder").textContent = n.folder + " · " + snippet(n.text, q);
      box.appendChild(a);
    });
    box.classList.add("open");
  }

  var timer;
  input.addEventListener("input", function () {
    clearTimeout(timer);
    var q = input.value;
    timer = setTimeout(function () {
      loadIndex().then(function () { render(search(q), q); });
    }, 120);
  });

  input.addEventListener("focus", function () { loadIndex(); });

  input.addEventListener("keydown", function (e) {
    var items = box.querySelectorAll("a");
    if (!items.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      selIdx = Math.min(selIdx + 1, items.length - 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      selIdx = Math.max(selIdx - 1, 0);
    } else if (e.key === "Enter") {
      if (selIdx >= 0) { window.location.href = items[selIdx].href; }
      return;
    } else if (e.key === "Escape") {
      box.classList.remove("open"); input.blur(); return;
    } else { return; }
    items.forEach(function (it, i) { it.classList.toggle("sel", i === selIdx); });
    items[selIdx].scrollIntoView({ block: "nearest" });
  });

  document.addEventListener("click", function (e) {
    if (!box.contains(e.target) && e.target !== input) box.classList.remove("open");
  });
})();
