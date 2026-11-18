/* Escalas — comportamento da interface (sem dependências).
   Tudo é ativado por atributos data-* e não interfere nos formulários do sistema.
   - Tema:      [data-theme-set="light|dark|system"]
   - Menu:      [data-nav-open] / [data-nav-close]
   - Busca:     <input data-filter="#alvo">, itens com [data-filter-text]
   - Copiar:    [data-copy="texto"]
   - Alertas:   [data-dismiss] remove o .alert pai
   - Modal:     [data-dialog-open="id"] / [data-dialog-close]
   - Abas:      [role=tablist] > [role=tab][aria-controls]
   - Ocupado:   <form data-busy> marca o botão enviado com aria-busy */
(function () {
  "use strict";
  var KEY = "escalas-theme";
  var root = document.documentElement;
  var mq = window.matchMedia("(prefers-color-scheme: dark)");

  /* ---------------- Tema ---------------- */
  function getPref() {
    // padrão do app: tema claro (até a pessoa escolher outro)
    try { return localStorage.getItem(KEY) || "light"; } catch (e) { return "light"; }
  }
  function apply(pref) {
    var dark = pref === "dark" || (pref === "system" && mq.matches);
    root.setAttribute("data-theme", dark ? "dark" : "light");
    root.setAttribute("data-theme-pref", pref);
    document.querySelectorAll("[data-theme-set]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-theme-set") === pref));
    });
  }
  function setPref(pref) {
    try { localStorage.setItem(KEY, pref); } catch (e) { /* modo privado: só nesta página */ }
    apply(pref);
  }
  apply(getPref());
  (mq.addEventListener ? mq.addEventListener.bind(mq, "change") : mq.addListener.bind(mq))(function () {
    if (getPref() === "system") apply("system");
  });
  window.addEventListener("storage", function (e) { if (e.key === KEY) apply(getPref()); });

  /* ---------------- Toast ---------------- */
  function toast(msg) {
    var region = document.querySelector(".toast-region");
    if (!region) {
      region = document.createElement("div");
      region.className = "toast-region";
      region.setAttribute("role", "status");
      region.setAttribute("aria-live", "polite");
      document.body.appendChild(region);
    }
    var t = document.createElement("div");
    t.className = "toast";
    t.textContent = msg;
    region.appendChild(t);
    setTimeout(function () { t.remove(); }, 2400);
  }
  window.EscalasUI = { toast: toast, setTheme: setPref };

  /* ---------------- Menu (drawer no celular) ---------------- */
  var lastFocus = null;
  function openNav() {
    lastFocus = document.activeElement;
    document.body.classList.add("nav-open");
    var bd = document.querySelector(".nav-backdrop");
    if (bd) bd.hidden = false;
    var first = document.querySelector("#sidebar a, #sidebar button");
    if (first) first.focus();
    document.querySelectorAll("[data-nav-open]").forEach(function (b) { b.setAttribute("aria-expanded", "true"); });
  }
  function closeNav() {
    if (!document.body.classList.contains("nav-open")) return;
    document.body.classList.remove("nav-open");
    var bd = document.querySelector(".nav-backdrop");
    if (bd) bd.hidden = true;
    document.querySelectorAll("[data-nav-open]").forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
    if (lastFocus) lastFocus.focus();
  }

  /* ---------------- Delegação de cliques ---------------- */
  document.addEventListener("click", function (e) {
    var el;
    if ((el = e.target.closest("[data-theme-set]"))) { setPref(el.getAttribute("data-theme-set")); return; }
    if (e.target.closest("[data-nav-open]")) { openNav(); return; }
    if (e.target.closest("[data-nav-close]")) { closeNav(); return; }
    if ((el = e.target.closest("[data-dismiss]"))) {
      var box = el.closest(".alert");
      if (box) box.remove();
      return;
    }
    if ((el = e.target.closest("[data-copy]"))) {
      var text = el.getAttribute("data-copy");
      var done = function () { toast(el.getAttribute("data-copy-msg") || "Copiado!"); };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
      } else { fallbackCopy(text); done(); }
      return;
    }
    if ((el = e.target.closest("[data-dialog-open]"))) {
      var dlg = document.getElementById(el.getAttribute("data-dialog-open"));
      if (dlg && dlg.showModal) dlg.showModal();
      return;
    }
    if ((el = e.target.closest("[data-dialog-close]"))) {
      var d = el.closest("dialog");
      if (d) d.close(el.getAttribute("data-dialog-close") || "");
      return;
    }
    // clique fora do conteúdo do dialog fecha
    if (e.target.tagName === "DIALOG" && e.target.open) e.target.close();
  });

  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignora */ }
    ta.remove();
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeNav();
      document.querySelectorAll("details.dropdown[open]").forEach(function (d) { d.open = false; });
    }
  });

  // fecha dropdowns ao clicar fora
  document.addEventListener("click", function (e) {
    document.querySelectorAll("details.dropdown[open]").forEach(function (d) {
      if (!d.contains(e.target)) d.open = false;
    });
  });

  /* ---------------- Busca/filtro em listas ---------------- */
  function norm(s) {
    return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }
  document.addEventListener("input", function (e) {
    var inp = e.target.closest("[data-filter]");
    if (!inp) return;
    var scope = document.querySelector(inp.getAttribute("data-filter"));
    if (!scope) return;
    var q = norm(inp.value.trim());
    var shown = 0;
    scope.querySelectorAll("[data-filter-text]").forEach(function (row) {
      var hit = !q || norm(row.getAttribute("data-filter-text")).indexOf(q) !== -1;
      row.hidden = !hit;
      if (hit) shown++;
    });
    var empty = scope.querySelector("[data-filter-empty]") ||
      document.querySelector('[data-filter-empty="' + inp.getAttribute("data-filter") + '"]');
    if (empty) empty.hidden = shown !== 0;
  });

  /* ---------------- Abas ---------------- */
  function selectTab(tab) {
    var list = tab.closest('[role="tablist"]');
    list.querySelectorAll('[role="tab"]').forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      var p = document.getElementById(t.getAttribute("aria-controls"));
      if (p) p.hidden = !on;
    });
  }
  document.addEventListener("click", function (e) {
    var tab = e.target.closest('[role="tab"]');
    if (tab) selectTab(tab);
  });
  document.addEventListener("keydown", function (e) {
    var tab = e.target.closest && e.target.closest('[role="tab"]');
    if (!tab || (e.key !== "ArrowRight" && e.key !== "ArrowLeft")) return;
    var tabs = Array.prototype.slice.call(tab.closest('[role="tablist"]').querySelectorAll('[role="tab"]'));
    var i = tabs.indexOf(tab) + (e.key === "ArrowRight" ? 1 : -1);
    var next = tabs[(i + tabs.length) % tabs.length];
    selectTab(next);
    next.focus();
    e.preventDefault();
  });

  /* ---------------- Botão "ocupado" ao enviar ---------------- */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (e.defaultPrevented || !form.hasAttribute("data-busy")) return;
    var btn = e.submitter || form.querySelector('button[type="submit"], button:not([type])');
    if (btn) btn.setAttribute("aria-busy", "true");
  });
})();
