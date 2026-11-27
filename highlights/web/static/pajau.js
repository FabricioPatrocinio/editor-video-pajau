// Pajau: envio da live com barra de progresso, formato (minutos/segundos), opções do Short e botões de copiar.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("pedido");
  if (form) setupRequest(form);

  document.body.addEventListener("click", (event) => {
    const copy = event.target.closest("[data-copy], [data-copy-from]");
    if (copy) {
      const text = copy.dataset.copy ?? document.querySelector(copy.dataset.copyFrom)?.value ?? "";
      navigator.clipboard.writeText(text).then(() => {
        const old = copy.textContent; copy.textContent = "copiado ✓"; setTimeout(() => (copy.textContent = old), 1500);
      });
    }
    const pick = event.target.closest("[data-select]");
    if (pick) {
      document.querySelectorAll(".clip.sel").forEach((el) => el.classList.remove("sel"));
      pick.closest(".clip")?.classList.add("sel");
    }
  });
});

function setupRequest(form) {
  const drop = document.getElementById("drop"), file = document.getElementById("arquivo");
  const path = document.getElementById("caminho"), button = document.getElementById("analisar");
  const title = document.getElementById("drop-title"), sub = document.getElementById("drop-sub");
  const bar = document.getElementById("drop-bar");

  const send = (chosen) => {
    if (!chosen) return;
    const request = new XMLHttpRequest();
    request.open("PUT", "/enviar?nome=" + encodeURIComponent(chosen.name));
    bar.classList.remove("d-none"); button.disabled = true;
    title.textContent = "Enviando " + chosen.name + "…";
    request.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const pct = Math.round((e.loaded / e.total) * 100);
      bar.firstElementChild.style.width = pct + "%"; sub.textContent = pct + "% de " + (e.total / 1e9).toFixed(2) + " GB";
    };
    request.onload = () => {
      button.disabled = false; bar.classList.add("d-none");
      if (request.status !== 200) { title.textContent = "Não deu para enviar. Tente de novo."; return; }
      const answer = JSON.parse(request.responseText);
      path.value = answer.caminho; drop.classList.add("ok");
      title.textContent = "✅ " + answer.nome; sub.textContent = "Pronta para analisar";
    };
    request.onerror = () => { button.disabled = false; title.textContent = "Falhou o envio. Tente de novo."; };
    request.send(chosen);
  };
  file.addEventListener("change", () => send(file.files[0]));
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => send(e.dataTransfer.files[0]));

  // Formato: a duração muda de unidade e o bloco do Short aparece.
  const duration = document.getElementById("duracao");
  const applyFormat = (radio, keepValue) => {
    document.getElementById("dur-unit").textContent = radio.dataset.unit;
    document.getElementById("dur-hint").textContent = radio.dataset.hint;
    duration.min = radio.dataset.min; duration.max = radio.dataset.max;
    if (!keepValue) duration.value = radio.dataset.value;
    document.getElementById("short-opts").classList.toggle("d-none", radio.value !== "9:16");
  };
  form.querySelectorAll("input[name=formato]").forEach((r) => r.addEventListener("change", () => applyFormat(r, false)));
  applyFormat(form.querySelector("input[name=formato]:checked") || form.querySelector("input[name=formato]"), false);

  const zoom = form.querySelector("input[name=zoom]"), cam = form.querySelector("input[name=camera]");
  zoom?.addEventListener("input", () => (document.getElementById("zoom-val").textContent = zoom.value));
  cam?.addEventListener("input", () => (document.getElementById("cam-val").textContent = cam.value + "%"));
  form.querySelectorAll("input[name=layout]").forEach((r) => r.addEventListener("change", () => {
    const camera = form.querySelector("input[name=layout]:checked").value === "camera";
    form.querySelectorAll(".cam-box").forEach((el) => el.classList.toggle("d-none", !camera));
    document.getElementById("zoom-box").classList.toggle("d-none", camera);
  }));

  form.addEventListener("submit", (e) => {
    if (!path.value.trim()) { e.preventDefault(); title.textContent = "⚠️ Escolha a live primeiro"; drop.classList.add("over"); return; }
    button.disabled = true; button.textContent = "Começando…";
  });
}
