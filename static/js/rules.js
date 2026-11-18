/* Escalas — formulário "Nova regra" (tela Regras).
   Mostra só os campos do tipo escolhido ([data-kinds]) e escreve uma prévia da regra.
   Sem JS, todos os campos aparecem e o servidor ignora os que não se aplicam. */
(function () {
  "use strict";
  var form = document.querySelector("[data-rule-form]");
  if (!form) return;
  var PLURAL = ["às segundas", "às terças", "às quartas", "às quintas", "às sextas", "aos sábados", "aos domingos"];
  var TURNO = { "": "", "Manhã": " de manhã", "Noite": " à noite" };

  function val(name) {
    var el = form.querySelector('[name="' + name + '"]:checked') || form.querySelector('[name="' + name + '"]');
    return el ? el.value : "";
  }
  function text(name) {
    var el = form.querySelector('select[name="' + name + '"]');
    return el && el.value ? el.options[el.selectedIndex].text : "";
  }

  function update() {
    var kind = val("kind");
    form.querySelectorAll("[data-kinds]").forEach(function (f) {
      f.hidden = f.getAttribute("data-kinds").split(" ").indexOf(kind) === -1;
    });
    var a = text("person_a"), wd = val("weekday"), when = wd !== "" ? PLURAL[+wd] + TURNO[val("turn")] : "";
    var s = "";
    if (a) {
      if (kind === "nunca_juntos" && text("person_b")) s = a + " e " + text("person_b") + " nunca tocam no mesmo culto";
      if (kind === "bloquear_turno" && when) s = a + " não toca " + when;
      if (kind === "fixar" && when && val("role")) s = a + " sempre como " + val("role") + " " + when + " (quando disponível)";
      if (kind === "minimo" && +val("n") > 0) s = a + " toca pelo menos " + val("n") + " culto" + (+val("n") !== 1 ? "s" : "") + " no mês (quando disponível)";
    }
    var box = form.querySelector("[data-rule-preview]");
    if (s) {
      box.querySelector(".alert__body").textContent = s + (val("hard") === "1" ? " — obrigatória." : " — preferência.");
    }
    box.hidden = !s;
  }
  form.addEventListener("change", update);
  form.addEventListener("input", update);
  update();
})();
