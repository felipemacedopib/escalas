/* Escalas — filtro de listas (Avisos, Pessoas): por nome (enquanto digita), por função e, se houver,
   por situação. Os filtros se combinam. Só esconde/mostra os itens; nada é enviado ao servidor.

   Marcação:
     <div data-notice-filter data-nf-noun="pessoa|pessoas">
       <input data-nf-name>   <select data-nf-role>   [<select data-nf-status>]
       <span data-nf-count>   <button data-nf-clear>
     itens:  [data-nf-item data-name="…" data-roles="A|B" data-status="…"]
     vazio:  [data-nf-empty]                                                    */
(function () {
  "use strict";
  var box = document.querySelector("[data-notice-filter]");
  if (!box) return;
  var name = box.querySelector("[data-nf-name]");
  var role = box.querySelector("[data-nf-role]");
  var status = box.querySelector("[data-nf-status]");
  var count = box.querySelector("[data-nf-count]");
  var clear = box.querySelector("[data-nf-clear]");
  var empty = document.querySelector("[data-nf-empty]");
  var items = Array.prototype.slice.call(document.querySelectorAll("[data-nf-item]"));
  var noun = (box.getAttribute("data-nf-noun") || "pessoa|pessoas").split("|");

  function norm(s) { return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim(); }

  function apply() {
    var q = norm(name.value), r = role ? role.value : "", st = status ? status.value : "", shown = 0;
    items.forEach(function (it) {
      var okName = !q || norm(it.getAttribute("data-name")).indexOf(q) !== -1;
      var okRole = !r || (it.getAttribute("data-roles") || "").split("|").indexOf(r) !== -1;
      var okSt = !st || it.getAttribute("data-status") === st;
      it.hidden = !(okName && okRole && okSt);
      if (!it.hidden) shown++;
    });
    count.textContent = shown + " de " + items.length + " " + (items.length === 1 ? noun[0] : noun[1]);
    if (empty) empty.hidden = shown !== 0;
    clear.hidden = !(q || r || st);
  }

  name.addEventListener("input", apply);
  if (role) role.addEventListener("change", apply);
  if (status) status.addEventListener("change", apply);
  clear.addEventListener("click", function () {
    name.value = "";
    if (role) role.value = "";
    if (status) status.value = "";
    apply(); name.focus();
  });
  apply();
})();
