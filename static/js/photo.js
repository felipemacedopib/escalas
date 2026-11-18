/* Foto pessoal (link pessoal): ao escolher a imagem, recorta no centro em quadrado, reduz para 512 px
   e envia como JPG. Assim a foto fica leve, sem os dados escondidos do celular (EXIF/GPS) e já
   na orientação certa. Sem JavaScript, o formulário envia o arquivo como está (o servidor confere). */
(function () {
  "use strict";
  var form = document.querySelector("[data-photo-form]");
  if (!form) return;
  var input = form.querySelector("[data-photo-input]");
  var btn = form.querySelector("[data-photo-btn]");
  var err = document.querySelector("[data-photo-error]");
  var preview = document.querySelector("[data-photo-preview]");
  var SIZE = 512;
  var label = btn.querySelector("span").textContent;

  function fail(msg) {
    err.textContent = msg; err.hidden = false;
    btn.removeAttribute("aria-busy");
    btn.querySelector("span").textContent = label;
    input.value = "";
  }

  function load(file) {
    if (window.createImageBitmap) {
      return createImageBitmap(file, { imageOrientation: "from-image" }).catch(function () { return viaImg(file); });
    }
    return viaImg(file);
  }
  function viaImg(file) {
    return new Promise(function (ok, no) {
      var img = new Image(), url = URL.createObjectURL(file);
      img.onload = function () { ok(img); URL.revokeObjectURL(url); };
      img.onerror = function () { no(); URL.revokeObjectURL(url); };
      img.src = url;
    });
  }

  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file) return;
    err.hidden = true;
    if (!/^image\//.test(file.type) && !/\.(jpe?g|png|webp|gif|heic|heif)$/i.test(file.name)) {
      return fail("Escolha um arquivo de imagem.");
    }
    btn.setAttribute("aria-busy", "true");
    btn.querySelector("span").textContent = "Enviando…";
    load(file).then(function (img) {
      var w = img.width, h = img.height, s = Math.min(w, h);
      var cv = document.createElement("canvas");
      cv.width = cv.height = SIZE;
      var ctx = cv.getContext("2d");
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, SIZE, SIZE);   // PNG transparente vira fundo branco
      ctx.drawImage(img, (w - s) / 2, (h - s) / 2, s, s, 0, 0, SIZE, SIZE);
      return new Promise(function (ok) { cv.toBlob(ok, "image/jpeg", 0.86); }).then(function (blob) {
        if (preview) {
          preview.innerHTML = "";
          var im = document.createElement("img");
          im.className = "avatar avatar--img avatar--xl"; im.alt = "";
          im.src = URL.createObjectURL(blob);
          preview.appendChild(im);
        }
        var fd = new FormData();
        fd.append("foto", blob, "foto.jpg");
        return fetch(form.action, { method: "POST", body: fd, credentials: "same-origin", redirect: "manual" });
      });
    }).then(function () {
      location.reload();          // a mensagem "Foto atualizada." aparece na página recarregada
    }).catch(function () {
      fail("Não consegui ler essa imagem. Tente uma foto JPG ou PNG.");
    });
  });
})();
