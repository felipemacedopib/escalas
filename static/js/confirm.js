/* Confirmação em modal do design system (substitui o confirm() nativo do navegador).

   Uso — no <form> ou no <button> que envia:
     data-confirm="Título da pergunta"            (obrigatório; liga a confirmação)
     data-confirm-text="Explicação"                (opcional)
     data-confirm-items='["1 dupla", "…"]'         (opcional; lista do que será afetado, JSON)
     data-confirm-hint="Dica"                      (opcional; caixa de dica abaixo)
     data-confirm-hint-href="/url" data-confirm-hint-link="Texto do link"  (opcional)
     data-confirm-ok="Excluir"                     (texto do botão; padrão "Confirmar")
     data-confirm-cancel="Revisar"                 (texto do botão de cancelar; padrão "Cancelar")
     data-confirm-tone="danger|warning|primary"    (padrão "danger")
     data-confirm-icon="trash"                     (ícone do sprite; padrão conforme o tom)

   Conteúdo dinâmico: antes de abrir, dispara o evento "confirm:prepare" (bubbles, cancelable) no elemento
   de origem — quem escuta pode reescrever os data-confirm-* ou cancelar a confirmação (preventDefault),
   deixando o envio seguir para as validações normais da página.

   O botão Cancelar recebe o foco (ação destrutiva nunca é a padrão). Esc ou clique fora cancelam.
   Depois de confirmar, o formulário é enviado com o mesmo botão (name/value preservados). */
(function () {
  "use strict";
  var sprite = (function () {
    var u = document.querySelector("svg use");
    var h = u && (u.getAttribute("href") || u.getAttribute("xlink:href"));
    return h ? h.split("#")[0] : "/static/icons.svg";
  })();

  function icon(name, cls) {
    return '<svg class="icon ' + (cls || "") + '" aria-hidden="true" focusable="false"><use href="' +
      sprite + "#i-" + name + '"></use></svg>';
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var dlg, q;
  var ICON = { danger: "trash", warning: "alert", primary: "check-circle" };
  function build() {
    dlg = document.createElement("dialog");
    dlg.className = "modal modal--confirm";
    dlg.setAttribute("role", "alertdialog");
    dlg.setAttribute("aria-labelledby", "confirm-title");
    dlg.setAttribute("aria-describedby", "confirm-body");
    dlg.innerHTML =
      '<div class="confirm">' +
      '  <div class="confirm__icon" data-c-icon></div>' +
      '  <div class="confirm__main">' +
      '    <h2 class="modal__title" id="confirm-title" data-c-title></h2>' +
      '    <div class="confirm__body" id="confirm-body">' +
      '      <p data-c-text></p>' +
      '      <ul class="confirm__items" data-c-items></ul>' +
      "    </div>" +
      '    <div class="confirm__hint" data-c-hint></div>' +
      "  </div>" +
      "</div>" +
      '<div class="modal__footer">' +
      '  <button type="button" class="btn btn--outline" value="cancel" data-c-cancel>Cancelar</button>' +
      '  <button type="button" class="btn" value="ok" data-c-ok></button>' +
      "</div>";
    document.body.appendChild(dlg);
    dlg.querySelector("[data-c-cancel]").addEventListener("click", function () { dlg.close("cancel"); });
    dlg.querySelector("[data-c-ok]").addEventListener("click", function () { dlg.close("ok"); });
  }

  function attr(el, name) {
    return el && el.hasAttribute(name) ? el.getAttribute(name) : null;
  }

  function ask(src, onOk) {
    if (!dlg) build();
    var tone = attr(src, "data-confirm-tone") || "danger";
    q = function (sel) { return dlg.querySelector(sel); };
    q("[data-c-cancel]").textContent = attr(src, "data-confirm-cancel") || "Cancelar";
    dlg.setAttribute("data-tone", tone);
    q("[data-c-icon]").innerHTML = icon(attr(src, "data-confirm-icon") || ICON[tone] || "alert");
    q("[data-c-title]").textContent = attr(src, "data-confirm");
    var text = attr(src, "data-confirm-text");
    q("[data-c-text]").textContent = text || "";
    q("[data-c-text]").hidden = !text;
    var items = [];
    try { items = JSON.parse(attr(src, "data-confirm-items") || "[]"); } catch (e) { items = []; }
    q("[data-c-items]").innerHTML = items.map(function (it) { return "<li>" + esc(it) + "</li>"; }).join("");
    q("[data-c-items]").hidden = !items.length;
    var hint = attr(src, "data-confirm-hint");
    var href = attr(src, "data-confirm-hint-href");
    q("[data-c-hint]").innerHTML = hint ? icon("info", "icon--sm") + "<span>" + esc(hint) +
      (href ? ' <a href="' + esc(href) + '">' + esc(attr(src, "data-confirm-hint-link") || "Abrir") + "</a>" : "") +
      "</span>" : "";
    q("[data-c-hint]").hidden = !hint;
    var ok = q("[data-c-ok]");
    ok.textContent = attr(src, "data-confirm-ok") || "Confirmar";
    ok.className = "btn " + (tone === "danger" ? "btn--danger-solid" : "btn--primary");

    dlg.returnValue = "";
    dlg.onclose = function () {
      dlg.onclose = null;
      if (dlg.returnValue === "ok") onOk();
    };
    if (dlg.showModal) {
      dlg.showModal();
      q("[data-c-cancel]").focus();
    } else if (window.confirm(attr(src, "data-confirm"))) {  // navegador muito antigo, sem <dialog>
      onOk();
    }
  }

  // fase de captura: roda antes do data-busy (ui.js) e de qualquer outro submit
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form.__confirmed) { form.__confirmed = false; return; }
    var btn = e.submitter && e.submitter.hasAttribute("data-confirm") ? e.submitter : null;
    var src = btn || (form.hasAttribute("data-confirm") ? form : null);
    if (!src) return;
    var prep = new CustomEvent("confirm:prepare", { bubbles: true, cancelable: true });
    if (!src.dispatchEvent(prep)) return;   // a página pediu para não confirmar agora (ex.: validação própria)
    e.preventDefault();
    e.stopImmediatePropagation();
    var submitter = e.submitter;
    ask(src, function () {
      form.__confirmed = true;
      if (form.requestSubmit) {
        form.requestSubmit(submitter || undefined);
      } else {  // sem requestSubmit: preserva o name/value do botão num campo oculto
        if (submitter && submitter.name) {
          var h = document.createElement("input");
          h.type = "hidden"; h.name = submitter.name; h.value = submitter.value;
          form.appendChild(h);
        }
        form.submit();
      }
    });
  }, true);
})();
