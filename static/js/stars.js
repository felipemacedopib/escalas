/* Estrelas da avaliação (link pessoal): tocar de novo na estrela já marcada tira a nota.
   Nesse caso envia o valor "0" (o servidor apaga a nota); escolher outra estrela volta ao normal. */
(function () {
  "use strict";
  document.querySelectorAll("[data-stars]").forEach(function (group) {
    var radios = group.querySelectorAll('input[type="radio"]');
    if (!radios.length) return;
    var name = radios[0].name;
    var clear = document.createElement("input");      // campo "0" usado só quando a nota é retirada
    clear.type = "hidden"; clear.name = name; clear.value = "0"; clear.disabled = true;
    group.appendChild(clear);
    var wasChecked = null;
    group.addEventListener("pointerdown", function (e) {
      var lab = e.target.closest("label");
      wasChecked = lab ? document.getElementById(lab.htmlFor).checked : null;
    });
    group.addEventListener("click", function (e) {
      var lab = e.target.closest("label");
      if (!lab) return;
      var inp = document.getElementById(lab.htmlFor);
      if (wasChecked) {                 // já estava marcada: desmarca
        e.preventDefault();
        inp.checked = false;
        clear.disabled = false;
      }
      wasChecked = null;
    });
    group.addEventListener("change", function () { clear.disabled = true; });
  });
})();
