/* Escalas — calendário de indisponibilidades (link pessoal).
   Só interface: lê e marca os checkboxes  input[data-date]  do mesmo <form>,
   que continuam sendo exatamente o que o servidor recebe (nao_<id_do_culto>).
   Modos: "Dias separados" (toque liga/desliga o dia) e "Período" (1º toque = início, 2º = fim).
   Marcar um dia marca todos os cultos daquele dia (ex.: domingo manhã e noite). */
(function () {
  "use strict";
  var MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
               "setembro", "outubro", "novembro", "dezembro"];
  var DIAS = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];
  var DIAS_CURTOS = ["D", "S", "T", "Q", "Q", "S", "S"];
  var anyUse = document.querySelector("svg.icon use");
  var ICON = anyUse ? anyUse.getAttribute("href").split("#")[0] : "/static/icons.svg";

  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function iso(y, m, d) { return y + "-" + pad(m + 1) + "-" + pad(d); }
  function fromIso(s) { var p = s.split("-"); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function icon(name) {
    var ns = "http://www.w3.org/2000/svg";
    var s = document.createElementNS(ns, "svg"); s.setAttribute("class", "icon icon--sm"); s.setAttribute("aria-hidden", "true");
    var u = document.createElementNS(ns, "use"); u.setAttribute("href", ICON + "#i-" + name); s.appendChild(u);
    return s;
  }

  document.querySelectorAll("[data-cal]").forEach(init);

  function init(root) {
    var form = root.closest("form");
    var boxes = Array.prototype.slice.call(form.querySelectorAll("input[data-date]"));
    if (!boxes.length) return;
    var byDate = {};
    boxes.forEach(function (b) { (byDate[b.getAttribute("data-date")] = byDate[b.getAttribute("data-date")] || []).push(b); });
    var ym = root.getAttribute("data-ym").split("-");
    var Y = +ym[0], M = +ym[1] - 1;
    var mode = "multi", anchor = null, uid = "cal" + Math.random().toString(36).slice(2, 7);
    var RO = root.hasAttribute("data-readonly");  // prazo encerrado: só consulta

    /* ---------- estrutura ---------- */
    var bar = el("div", "cal__bar");
    var seg = el("div", "segmented segmented--text");
    seg.setAttribute("role", "group");
    seg.setAttribute("aria-label", "Como selecionar");
    var bMulti = el("button", null, "Dias separados"), bRange = el("button", null, "Período");
    [bMulti, bRange].forEach(function (b) { b.type = "button"; seg.appendChild(b); });
    var title = el("div", "cal__title", MESES[M].charAt(0).toUpperCase() + MESES[M].slice(1) + " " + Y);
    // atalhos: marcar/desmarcar todos os sábados (6) ou domingos (0) do mês
    var quick = el("div", "cal__quick");
    quick.setAttribute("role", "group");
    quick.setAttribute("aria-label", "Atalhos");
    var bSat = el("button", "btn btn--outline btn--sm cal__qbtn", "Todos os sábados");
    var bSun = el("button", "btn btn--outline btn--sm cal__qbtn", "Todos os domingos");
    bSat.setAttribute("data-wd", "6"); bSun.setAttribute("data-wd", "0");
    [bSat, bSun].forEach(function (b) { b.type = "button"; quick.appendChild(b); });
    var tools = el("div", "cal__tools");
    tools.appendChild(seg); tools.appendChild(quick);
    bar.appendChild(title); bar.appendChild(tools);

    var hint = el("p", "cal__hint");
    hint.setAttribute("aria-live", "polite");

    var grid = el("div", "cal__grid");
    grid.setAttribute("role", "group");
    grid.setAttribute("aria-label", "Calendário de " + MESES[M] + " de " + Y);
    DIAS_CURTOS.forEach(function (d, i) {
      var h = el("div", "cal__wd", d); h.setAttribute("aria-hidden", "true"); h.title = DIAS[i]; grid.appendChild(h);
    });
    var first = new Date(Y, M, 1).getDay();
    for (var i = 0; i < first; i++) grid.appendChild(el("span", "cal__pad"));
    var cells = {};
    var last = new Date(Y, M + 1, 0).getDate();
    for (var d = 1; d <= last; d++) {
      var key = iso(Y, M, d), has = !!byDate[key];
      var b = el("button", "cal__day" + (has ? " has" : ""));
      b.type = "button";
      b.setAttribute("data-day", key);
      b.appendChild(el("span", "cal__num", String(d)));
      if (has) {
        b.appendChild(el("span", "cal__dot"));
        var turns = byDate[key].map(function (x) { return x.getAttribute("data-turn"); });
        b.setAttribute("data-label", DIAS[new Date(Y, M, d).getDay()] + ", " + d + " de " + MESES[M] +
          ": culto " + turns.join(" e ").toLowerCase());
      } else {
        b.disabled = true;
        b.setAttribute("aria-label", d + " de " + MESES[M] + ", sem culto");
      }
      cells[key] = b;
      grid.appendChild(b);
    }

    var legend = el("div", "cal__legend");
    legend.innerHTML = '<span><i class="cal__key cal__key--has"></i>Tem culto</span>' +
                       '<span><i class="cal__key cal__key--sel"></i>Não posso</span>' +
                       '<span><i class="cal__key cal__key--part"></i>Só um turno</span>';

    var summary = el("div", "cal__summary");
    var sumHead = el("div", "cal__sumhead");
    var count = el("span", "cal__count");
    var clear = el("button", "btn btn--ghost btn--sm", "Limpar");
    clear.type = "button";
    clear.prepend(icon("x"));
    sumHead.appendChild(count); sumHead.appendChild(clear);
    var chips = el("div", "badges");
    summary.appendChild(sumHead); summary.appendChild(chips);

    root.appendChild(bar); root.appendChild(hint); root.appendChild(grid); root.appendChild(legend); root.appendChild(summary);
    root.hidden = false;
    if (RO) {
      tools.hidden = true;
      legend.hidden = true;
      Object.keys(cells).forEach(function (k) { cells[k].disabled = true; });
    }

    /* ---------- confirmação ao salvar (modal de static/js/confirm.js) ---------- */
    var SEM = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
    var mesAno = MESES[M] + " de " + Y;
    form.addEventListener("confirm:prepare", function (e) {
      if (RO) { e.preventDefault(); return; }
      // motivo só com espaços: deixa a validação do motivo agir primeiro (sem abrir a confirmação)
      var ta = form.querySelector("[data-motivo] textarea");
      if (ta && ta.required && !ta.value.trim()) { e.preventDefault(); return; }
      var sel = Object.keys(byDate).sort().filter(function (k) { return state(k) !== "off"; });
      var items = sel.map(function (k) {
        var bs = byDate[k], on = bs.filter(function (b) { return b.checked; });
        var dt = fromIso(k), when = SEM[dt.getDay()] + ", " + fmt(k);
        if (on.length === bs.length) {
          return when + (bs.length > 1 ? ": dia todo (" + bs.map(function (b) { return b.getAttribute("data-turn"); }).join(" e ") + ")"
                                       : ": " + bs[0].getAttribute("data-turn"));
        }
        return when + ": só " + on.map(function (b) { return b.getAttribute("data-turn"); }).join(" e ");
      });
      form.setAttribute("data-confirm", "Tem certeza sobre as datas informadas?");
      form.setAttribute("data-confirm-items", JSON.stringify(items));
      if (items.length) {
        form.setAttribute("data-confirm-text", "Você marcou que NÃO pode participar em " +
          (items.length === 1 ? "1 dia" : items.length + " dias") + " de " + mesAno + ":");
        form.setAttribute("data-confirm-hint", "Lembrando que a sua indisponibilidade pode sobrecarregar outra pessoa.");
      } else {
        form.setAttribute("data-confirm-text", "Você não marcou nenhum dia, então vai ficar disponível para todos os cultos de " + mesAno + ".");
        form.removeAttribute("data-confirm-hint");
      }
    });

    // com o calendário ativo, a lista por culto fica recolhida (continua disponível)
    var det = form.querySelector("[data-cal-details]");
    if (det) det.open = false;

    /* ---------- estado ---------- */
    function state(key) {
      var bs = byDate[key]; if (!bs) return "none";
      var n = bs.filter(function (x) { return x.checked; }).length;
      return n === 0 ? "off" : (n === bs.length ? "on" : "part");
    }
    function setDay(key, on) {
      (byDate[key] || []).forEach(function (x) {
        if (x.checked !== on) { x.checked = on; x.dispatchEvent(new Event("change", { bubbles: true })); }
      });
    }
    function setMode(m) {
      mode = m; anchor = null;
      bMulti.setAttribute("aria-pressed", String(m === "multi"));
      bRange.setAttribute("aria-pressed", String(m === "range"));
      render();
    }
    function weekdayKeys(wd) {
      return Object.keys(byDate).filter(function (k) { return fromIso(k).getDay() === wd; });
    }
    function allOn(keys) { return keys.length > 0 && keys.every(function (k) { return state(k) === "on"; }); }
    function fmt(key) { var dt = fromIso(key); return pad(dt.getDate()) + "/" + pad(dt.getMonth() + 1); }

    function render(preview) {
      Object.keys(cells).forEach(function (key) {
        var c = cells[key], st = state(key);
        c.classList.toggle("is-on", st === "on");
        c.classList.toggle("is-part", st === "part");
        c.classList.toggle("is-anchor", key === anchor);
        var inPrev = preview && anchor && key >= (anchor < preview ? anchor : preview) && key <= (anchor < preview ? preview : anchor);
        c.classList.toggle("is-preview", !!inPrev && !c.disabled);
        if (RO && byDate[key]) {
          c.setAttribute("aria-label", c.getAttribute("data-label") + (st === "on" ? " — você marcou: não posso" : st === "part" ? " — marcado só um turno" : ""));
        }
        if (!c.disabled) {
          c.setAttribute("aria-pressed", String(st === "on"));
          c.setAttribute("aria-label", c.getAttribute("data-label") +
            (st === "on" ? " — marcado: não posso" : st === "part" ? " — marcado só um turno" : ""));
        }
      });
      if (RO) {
        hint.textContent = "Prazo encerrado — somente leitura. Em vermelho, os dias que você marcou.";
      } else if (mode === "range") {
        hint.textContent = anchor ? "Agora toque no último dia do período (" + fmt(anchor) + " até …)."
                                  : "Toque no primeiro dia do período em que você não pode.";
      } else {
        hint.textContent = "Toque em cada dia em que você não pode. Toque de novo para desmarcar.";
      }
      // atalhos sábados/domingos refletem o estado atual
      [bSat, bSun].forEach(function (b) {
        var keys = weekdayKeys(+b.getAttribute("data-wd"));
        var on = allOn(keys);
        b.disabled = !keys.length;
        b.setAttribute("aria-pressed", String(on));
        b.classList.toggle("is-on", on);
        b.title = !keys.length ? "Não há culto neste dia da semana" :
                  on ? "Toque para desmarcar todos" : "Marca " + keys.length + " dia(s) como indisponível";
      });
      // resumo
      var sel =Object.keys(byDate).sort().filter(function (k) { return state(k) !== "off"; });
      count.textContent = sel.length ? (sel.length === 1 ? "1 dia marcado" : sel.length + " dias marcados")
                                     : "Nenhum dia marcado — você pode em todos.";
      clear.hidden = RO || !sel.length;
      chips.textContent = "";
      sel.forEach(function (k) {
        var label = fmt(k) + (state(k) === "part" ? " (1 turno)" : "");
        if (RO) { chips.appendChild(el("span", "badge badge--danger", label)); return; }
        var chip = el("button", "badge badge--danger cal__chip");
        chip.type = "button";
        chip.textContent = label;
        chip.setAttribute("aria-label", "Remover " + fmt(k));
        chip.appendChild(icon("x"));
        chip.addEventListener("click", function () { setDay(k, false); });
        chips.appendChild(chip);
      });
      syncMotivo(form);
    }

    /* ---------- eventos ---------- */
    bMulti.addEventListener("click", function () { setMode("multi"); });
    bRange.addEventListener("click", function () { setMode("range"); });
    [bSat, bSun].forEach(function (b) {
      b.addEventListener("click", function () {
        var keys = weekdayKeys(+b.getAttribute("data-wd"));
        var turnOn = !allOn(keys);
        keys.forEach(function (k) { setDay(k, turnOn); });
        anchor = null;
        render();
      });
    });
    clear.addEventListener("click", function () { Object.keys(byDate).forEach(function (k) { setDay(k, false); }); anchor = null; render(); });

    grid.addEventListener("click", function (e) {
      var c = e.target.closest(".cal__day");
      if (!c || c.disabled) return;
      var key = c.getAttribute("data-day");
      if (mode === "multi") {
        setDay(key, state(key) !== "on");
      } else if (!anchor) {
        anchor = key;
      } else {
        var a = anchor < key ? anchor : key, z = anchor < key ? key : anchor;
        Object.keys(byDate).forEach(function (k) { if (k >= a && k <= z) setDay(k, true); });
        anchor = null;
      }
      render();
    });
    grid.addEventListener("mouseover", function (e) {
      if (mode !== "range" || !anchor) return;
      var c = e.target.closest(".cal__day");
      if (c) render(c.getAttribute("data-day"));
    });
    grid.addEventListener("mouseleave", function () { if (anchor) render(); });
    // setas do teclado navegam entre os dias com culto
    grid.addEventListener("keydown", function (e) {
      var c = e.target.closest(".cal__day");
      if (!c) return;
      var step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 7, ArrowUp: -7 }[e.key];
      if (!step) return;
      var dt = fromIso(c.getAttribute("data-day"));
      for (var n = 0; n < 31; n++) {
        dt.setDate(dt.getDate() + step);
        if (dt.getMonth() !== M) return;
        var t = cells[iso(Y, M, dt.getDate())];
        if (t && !t.disabled) { t.focus(); if (anchor) render(t.getAttribute("data-day")); e.preventDefault(); return; }
      }
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && anchor) { anchor = null; render(); } });
    // se a pessoa ajustar pela lista por culto ("Selecione o período todo ou somente meio período"), o calendário acompanha
    form.addEventListener("change", function (e) { if (e.target.matches("input[data-date]")) render(); });

    setMode("multi");
  }

  /* Motivo obrigatório quando há algum dia marcado (o servidor confere de novo). */
  function syncMotivo(form) {
    var box = form.querySelector("[data-motivo]");
    if (!box) return;
    var ta = box.querySelector("textarea"), req = box.querySelector("[data-motivo-req]");
    if (ta.readOnly) return;
    var any = !!form.querySelector("input[data-date]:checked");
    ta.required = any;
    if (req) req.hidden = !any;
    if (!any || ta.value.trim()) { ta.classList.remove("is-invalid"); ta.removeAttribute("aria-invalid"); }
  }
  document.querySelectorAll("form [data-motivo]").forEach(function (box) {
    var form = box.closest("form");
    syncMotivo(form);
    form.addEventListener("change", function () { syncMotivo(form); });
    box.querySelector("textarea").addEventListener("input", function () { syncMotivo(form); });
    // só espaços não conta como motivo
    form.addEventListener("submit", function (e) {
      var ta = box.querySelector("textarea");
      if (ta.required && !ta.value.trim()) {
        e.preventDefault();
        ta.value = "";
        ta.classList.add("is-invalid");
        ta.setAttribute("aria-invalid", "true");
        ta.focus();
        ta.reportValidity && ta.reportValidity();
        var btn = form.querySelector("[aria-busy]");
        if (btn) btn.removeAttribute("aria-busy");
      }
    });
  });
})();
