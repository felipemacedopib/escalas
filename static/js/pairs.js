/* Nova dupla: a mesma pessoa não pode ser escolhida nos dois campos.
   Quem já chegou ao limite de duplas (data-full) continua sempre bloqueado. */
(function () {
  var form = document.querySelector("[data-pair-form]");
  if (!form) return;
  var a = form.querySelector("[name=pessoa_a]");
  var b = form.querySelector("[name=pessoa_b]");
  function sync() {
    [[a, b], [b, a]].forEach(function (pair) {
      var self = pair[0], other = pair[1];
      Array.prototype.forEach.call(self.options, function (o) {
        o.disabled = o.hasAttribute("data-full") || (o.value !== "" && o.value === other.value);
      });
    });
    b.setCustomValidity(a.value && a.value === b.value ? "Escolha duas pessoas diferentes." : "");
  }
  a.addEventListener("change", sync);
  b.addEventListener("change", sync);
  sync();
})();
