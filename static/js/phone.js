/* Escalas — máscara de celular brasileiro (WhatsApp): (DD) 9XXXX-XXXX
   Campos: <input data-phone-br>. Vazio é permitido. O servidor (notify.br_mobile) valida de novo. */
(function () {
  "use strict";
  var DDDS = [11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38,
              41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69,
              71, 73, 74, 75, 77, 79, 81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98, 99];

  function digits(v) {
    var d = (v || "").replace(/\D/g, "");
    if (d.length > 11 && d.indexOf("55") === 0) d = d.slice(2);  // colou com +55
    return d.slice(0, 11);
  }
  function format(d) {
    if (!d) return "";
    if (d.length <= 2) return "(" + d;
    if (d.length <= 7) return "(" + d.slice(0, 2) + ") " + d.slice(2);
    return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
  }
  function problem(d) {
    if (!d) return "";
    if (d.length < 2 || DDDS.indexOf(+d.slice(0, 2)) === -1) return d.length < 2 ? "Digite o DDD." : "DDD " + d.slice(0, 2) + " não existe.";
    if (d.length >= 3 && d[2] !== "9") return "Celular deve começar com 9 depois do DDD (WhatsApp).";
    if (d.length < 11) return "Faltam " + (11 - d.length) + " dígito(s).";
    return "";
  }

  document.querySelectorAll("input[data-phone-br]").forEach(function (inp) {
    var help = inp.parentNode.querySelector("[data-phone-help]");
    var helpText = help ? help.textContent : "";
    function update(showError) {
      var d = digits(inp.value);
      var pos = inp.selectionStart === inp.value.length;
      inp.value = format(d);
      if (pos) inp.setSelectionRange(inp.value.length, inp.value.length);
      var msg = problem(d);
      inp.setCustomValidity(msg ? "Celular inválido: " + msg + " Ex.: (41) 99999-9999" : "");
      var bad = !!msg && showError;
      inp.classList.toggle("is-invalid", bad);
      if (bad) inp.setAttribute("aria-invalid", "true"); else inp.removeAttribute("aria-invalid");
      if (help) { help.textContent = bad ? msg : (d.length === 11 && !msg ? "✓ Celular válido para WhatsApp." : helpText); help.classList.toggle("req", bad); }
    }
    // enquanto digita: avisa logo de DDD errado ou falta do 9; "faltam dígitos" só ao sair do campo
    inp.addEventListener("input", function () {
      var d = digits(inp.value), msg = problem(d);
      update(!!msg && d.length >= 2 && msg.indexOf("Faltam") !== 0);
    });
    inp.addEventListener("blur", function () { update(true); });
    inp.addEventListener("invalid", function () { update(true); });
    update(false);
  });
})();
