(function () {
  "use strict";

  const wizard = document.getElementById("wizard");
  const slug = wizard.dataset.slug;

  const SCALAR_FIELDS = [
    ["asesor_comercial", "Asesor comercial"],
    ["cliente_nombre", "Nombre del cliente"],
    ["cliente_cedula", "Cedula de ciudadania / NIT"],
    ["cliente_direccion", "Direccion"],
    ["cliente_telefono", "Telefono"],
    ["cliente_correo", "Correo electronico"],
    ["destino", "Destino del viaje"],
    ["confirmacion_reserva", "Confirmacion de reserva"],
    ["valor_total", "Valor total ($)"],
    ["fecha_limite_pago", "Fecha limite de pago"],
    ["programa", "Programa"],
    ["fecha_reserva", "Fecha de la reserva"],
    ["hotel", "Hotel"],
    ["check_in", "Check in"],
    ["check_out", "Check out"],
  ];

  const EMPTY_DATA = {
    asesor_comercial: "", cliente_nombre: "", cliente_cedula: "", cliente_direccion: "",
    cliente_telefono: "", cliente_correo: "", destino: "", confirmacion_reserva: "",
    valor_total: "", fecha_limite_pago: "", pagos: [], pasajeros_adicionales: [],
    programa: "", fecha_reserva: "", hotel: "", check_in: "15:00", check_out: "12:00",
    pasajeros_reserva: [], incluye: "", no_incluye: "",
  };

  let state = { data: structuredClone(EMPTY_DATA) };

  // ---------- helpers de navegacion entre pasos ----------
  function showStep(name) {
    document.querySelectorAll(".step-panel").forEach((el) => el.classList.remove("active"));
    document.getElementById("step-" + name).classList.add("active");
    document.querySelectorAll(".step-dot").forEach((el) => {
      el.classList.toggle("active", el.dataset.step === name);
    });
  }

  function setError(boxId, messages) {
    const box = document.getElementById(boxId);
    if (!messages || messages.length === 0) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    box.hidden = false;
    if (Array.isArray(messages)) {
      box.innerHTML =
        "<strong>Faltan datos por completar:</strong><ul>" +
        messages.map((m) => `<li>${escapeHtml(m)}</li>`).join("") +
        "</ul>";
    } else {
      box.textContent = messages;
    }
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  // ---------- PASO 1: pegar y parsear ----------
  const btnContinuar = document.getElementById("btn-continuar");
  btnContinuar.addEventListener("click", async () => {
    const text = document.getElementById("paste-textarea").value.trim();
    setError("paste-error", null);
    if (!text) {
      setError("paste-error", "Pega la informacion del cliente antes de continuar.");
      return;
    }
    toggleSpinner("paste-spinner", true);
    btnContinuar.disabled = true;
    try {
      const res = await fetch(`/api/${slug}/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError("paste-error", body.error || "No se pudo interpretar el texto.");
        return;
      }
      state.data = Object.assign(structuredClone(EMPTY_DATA), body.data);
      showStep("review");
      if (body.missing && body.missing.length > 0) {
        setError("review-error", body.missing);
        enterEditMode();
      } else {
        setError("review-error", null);
        renderPreview();
        enterPreviewMode();
      }
    } catch (err) {
      setError("paste-error", "Error de conexion: " + err.message);
    } finally {
      toggleSpinner("paste-spinner", false);
      btnContinuar.disabled = false;
    }
  });

  function toggleSpinner(id, show) {
    document.getElementById(id).hidden = !show;
  }

  // ---------- PASO 2: vista previa (solo lectura) ----------
  function renderPreview() {
    const d = state.data;
    const rows = (label, value) => `<div class="pv-row"><span class="pv-label">${escapeHtml(label)}</span><span class="pv-value">${escapeHtml(value) || "&mdash;"}</span></div>`;

    let html = "";
    html += `<div class="pv-card"><h2>Contrato</h2>`;
    html += rows("Asesor comercial", d.asesor_comercial);
    html += rows("Cliente", d.cliente_nombre);
    html += rows("Cedula / NIT", d.cliente_cedula);
    html += rows("Direccion", d.cliente_direccion);
    html += rows("Telefono", d.cliente_telefono);
    html += rows("Correo", d.cliente_correo);
    html += rows("Destino", d.destino);
    html += rows("Confirmacion de reserva", d.confirmacion_reserva);
    html += rows("Valor total", "$ " + (d.valor_total || ""));
    html += rows("Fecha limite de pago", d.fecha_limite_pago);
    html += `</div>`;

    html += `<div class="pv-card"><h2>Cronograma de pagos</h2>`;
    if (d.pagos.length === 0) html += `<p class="muted">Sin pagos registrados.</p>`;
    d.pagos.forEach((p) => {
      html += `<div class="pv-row"><span class="pv-label">${escapeHtml(p.fecha)}</span><span class="pv-value">$ ${escapeHtml(p.valor)}</span></div>`;
    });
    html += `</div>`;

    html += `<div class="pv-card"><h2>Viajeros / beneficiarios adicionales</h2>`;
    if (d.pasajeros_adicionales.length === 0) html += `<p class="muted">Ninguno.</p>`;
    d.pasajeros_adicionales.forEach((p) => {
      html += `<div class="pv-row"><span class="pv-label">${escapeHtml(p.nombre)}</span><span class="pv-value">C.C. ${escapeHtml(p.cedula)}</span></div>`;
    });
    html += `</div>`;

    html += `<div class="pv-card"><h2>Confirmacion de reserva</h2>`;
    html += rows("Programa", d.programa);
    html += rows("Fecha", d.fecha_reserva);
    html += rows("Hotel", d.hotel);
    html += rows("Check in", d.check_in);
    html += rows("Check out", d.check_out);
    html += `</div>`;

    html += `<div class="pv-card"><h2>Pasajeros</h2>`;
    if (d.pasajeros_reserva.length === 0) html += `<p class="muted">Sin pasajeros.</p>`;
    d.pasajeros_reserva.forEach((p) => {
      html += `<div class="pv-row"><span class="pv-label">${escapeHtml(p.nombre)}</span><span class="pv-value">${escapeHtml(p.documento)}</span></div>`;
    });
    html += `</div>`;

    html += `<div class="pv-card"><h2>Incluye</h2><p>${escapeHtml(d.incluye).replace(/\n/g, "<br/>") || "&mdash;"}</p></div>`;
    html += `<div class="pv-card"><h2>No incluye</h2><p>${escapeHtml(d.no_incluye).replace(/\n/g, "<br/>") || "&mdash;"}</p></div>`;

    document.getElementById("preview-view").innerHTML = html;
  }

  // ---------- PASO 2: modo edicion ----------
  function renderEditForm() {
    const d = state.data;
    let html = `<div class="edit-card"><h2>Contrato</h2><div class="form-grid">`;
    SCALAR_FIELDS.slice(0, 10).forEach(([key, label]) => {
      html += fieldInput(key, label, d[key]);
    });
    html += `</div></div>`;

    html += `<div class="edit-card"><h2>Cronograma de pagos</h2><div id="dyn-pagos" class="dyn-list"></div>
      <button type="button" class="btn-add" data-add="pagos">+ Agregar pago</button></div>`;

    html += `<div class="edit-card"><h2>Viajeros / beneficiarios adicionales</h2><div id="dyn-adicionales" class="dyn-list"></div>
      <button type="button" class="btn-add" data-add="adicionales">+ Agregar viajero</button></div>`;

    html += `<div class="edit-card"><h2>Confirmacion de reserva</h2><div class="form-grid">`;
    SCALAR_FIELDS.slice(10).forEach(([key, label]) => {
      html += fieldInput(key, label, d[key]);
    });
    html += `</div></div>`;

    html += `<div class="edit-card"><h2>Pasajeros</h2><div id="dyn-pasajeros" class="dyn-list"></div>
      <button type="button" class="btn-add" data-add="pasajeros">+ Agregar pasajero</button></div>`;

    html += `<div class="edit-card"><h2>Incluye</h2><textarea data-field="incluye" rows="4">${escapeHtml(d.incluye)}</textarea></div>`;
    html += `<div class="edit-card"><h2>No incluye</h2><textarea data-field="no_incluye" rows="4">${escapeHtml(d.no_incluye)}</textarea></div>`;

    document.getElementById("edit-view").innerHTML = html;

    renderDynList("dyn-pagos", "tpl-field-row-pago", d.pagos, ["fecha", "valor"], [".inp-fecha", ".inp-valor"]);
    renderDynList("dyn-adicionales", "tpl-field-row-persona", d.pasajeros_adicionales, ["nombre", "cedula"], [".inp-nombre", ".inp-doc"]);
    renderDynList("dyn-pasajeros", "tpl-field-row-persona", d.pasajeros_reserva, ["nombre", "documento"], [".inp-nombre", ".inp-doc"]);

    document.querySelectorAll("[data-add]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kind = btn.dataset.add;
        if (kind === "pagos") addDynRow("dyn-pagos", "tpl-field-row-pago");
        if (kind === "adicionales") addDynRow("dyn-adicionales", "tpl-field-row-persona");
        if (kind === "pasajeros") addDynRow("dyn-pasajeros", "tpl-field-row-persona");
      });
    });
  }

  function fieldInput(key, label, value) {
    return `<label class="form-field">
      <span>${escapeHtml(label)}</span>
      <input type="text" data-field="${key}" value="${escapeHtml(value)}" />
    </label>`;
  }

  function renderDynList(containerId, tplId, items, fieldNames, selectors) {
    const container = document.getElementById(containerId);
    container.innerHTML = "";
    items.forEach((item) => {
      const row = addDynRow(containerId, tplId);
      selectors.forEach((sel, i) => {
        row.querySelector(sel).value = item[fieldNames[i]] || "";
      });
    });
  }

  function addDynRow(containerId, tplId) {
    const tpl = document.getElementById(tplId);
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.querySelector(".btn-remove-row").addEventListener("click", () => node.remove());
    document.getElementById(containerId).appendChild(node);
    return node;
  }

  function collectEditForm() {
    const d = state.data;
    document.querySelectorAll("#edit-view [data-field]").forEach((el) => {
      d[el.dataset.field] = el.value;
    });
    d.pagos = readDynRows("dyn-pagos", ["fecha", "valor"], [".inp-fecha", ".inp-valor"]);
    d.pasajeros_adicionales = readDynRows("dyn-adicionales", ["nombre", "cedula"], [".inp-nombre", ".inp-doc"]);
    d.pasajeros_reserva = readDynRows("dyn-pasajeros", ["nombre", "documento"], [".inp-nombre", ".inp-doc"]);
  }

  function readDynRows(containerId, fieldNames, selectors) {
    const rows = document.querySelectorAll(`#${containerId} .dyn-row`);
    const out = [];
    rows.forEach((row) => {
      const item = {};
      let hasValue = false;
      selectors.forEach((sel, i) => {
        const v = row.querySelector(sel).value.trim();
        item[fieldNames[i]] = v;
        if (v) hasValue = true;
      });
      if (hasValue) out.push(item);
    });
    return out;
  }

  function enterPreviewMode() {
    document.getElementById("preview-view").hidden = false;
    document.getElementById("edit-view").hidden = true;
    document.getElementById("btn-editar").hidden = false;
    document.getElementById("btn-guardar").hidden = true;
  }

  function enterEditMode() {
    renderEditForm();
    document.getElementById("preview-view").hidden = true;
    document.getElementById("edit-view").hidden = false;
    document.getElementById("btn-editar").hidden = true;
    document.getElementById("btn-guardar").hidden = false;
  }

  document.getElementById("btn-editar").addEventListener("click", enterEditMode);

  document.getElementById("btn-guardar").addEventListener("click", () => {
    collectEditForm();
    renderPreview();
    enterPreviewMode();
    setError("review-error", null);
  });

  document.getElementById("btn-volver").addEventListener("click", () => {
    showStep("paste");
  });

  document.getElementById("btn-enviar").addEventListener("click", async () => {
    if (!document.getElementById("edit-view").hidden) {
      collectEditForm();
    }
    setError("review-error", null);
    const spinner = document.getElementById("review-spinner");
    const btn = document.getElementById("btn-enviar");
    spinner.hidden = false;
    btn.disabled = true;
    try {
      const res = await fetch(`/api/${slug}/generar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state.data),
      });
      const body = await res.json();
      if (!res.ok) {
        if (body.missing) {
          setError("review-error", body.missing);
          enterEditMode();
        } else {
          setError("review-error", body.error || "No se pudo enviar el contrato.");
        }
        return;
      }
      showStep("success");
    } catch (err) {
      setError("review-error", "Error de conexion: " + err.message);
    } finally {
      spinner.hidden = true;
      btn.disabled = false;
    }
  });

  document.getElementById("btn-nuevo").addEventListener("click", () => {
    state = { data: structuredClone(EMPTY_DATA) };
    document.getElementById("paste-textarea").value = "";
    setError("paste-error", null);
    setError("review-error", null);
    showStep("paste");
  });
})();
