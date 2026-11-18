/* "Sua escala" (link pessoal): no celular, sempre que a página carrega, todos os cultos começam fechados
   — inclusive ao voltar para a página (o navegador pode restaurar o estado aberto) e depois de salvar
   avaliações. No computador, mantém o culto que estava sendo avaliado aberto. */
(function () {
  "use strict";
  var mobile = window.matchMedia("(max-width: 767px)");
  function closeAll() {
    if (!mobile.matches) return;
    document.querySelectorAll("details.escala-item[open]").forEach(function (d) { d.open = false; });
  }
  closeAll();
  window.addEventListener("pageshow", closeAll);   // também quando a página volta do cache (botão voltar)
})();
