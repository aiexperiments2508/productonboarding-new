/* Vendor Portal.
 *
 * No build step and no framework. Three of these applications ship in this
 * repository and giving each one a bundler would be three more node_modules,
 * three more things to install on a machine that has to work in a room, and -
 * because they would end up sharing the platform's tokens - three applications
 * that look like the platform.
 *
 * Every fetch here goes to this portal's own server, which turns it into an
 * MCP tool call and has no other way of reaching anything.
 */

const $ = (id) => document.getElementById(id);
const state = { system: null, supplier: "", product: null, spec: null };

/* --- plumbing ----------------------------------------------------------- */

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (body && body.error) throw new Error(body.error);
  return body;
}

const post = (path, body) =>
  api(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

function toast(message, bad = false) {
  const node = document.createElement("div");
  node.className = "toast" + (bad ? " bad" : "");
  node.textContent = message;
  $("toasts").append(node);
  setTimeout(() => node.remove(), 7000);
}

const b64 = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });

/* --- sign in ------------------------------------------------------------ */

async function boot() {
  const { systems, platform } = await api("/portal-api/systems");
  $("footLink").textContent = `connected to ${platform} over MCP`;

  $("systems").innerHTML = systems
    .map(
      (s) => `<button data-id="${s.id}">
        <b>${s.title}</b><span>${s.blurb}</span>
        <code>/mcp/intake/${s.id}/</code></button>`
    )
    .join("");

  $("systems").querySelectorAll("button").forEach((button) => {
    button.onclick = () => chooseSystem(button.dataset.id, button);
  });

  chooseSystem(systems[0].id, $("systems").querySelector("button"));
}

async function chooseSystem(id, button) {
  state.system = id;
  $("systems").querySelectorAll("button").forEach((b) => b.classList.remove("on"));
  if (button) button.classList.add("on");

  $("supplier").innerHTML = `<option value="">Asking the endpoint…</option>`;
  $("go").disabled = true;
  try {
    // The endpoint says who it will serve. Asking it rather than holding a
    // list here means the portal cannot get out of step with the catalog.
    const described = await api(`/portal-api/intake/${id}`);
    $("supplier").innerHTML =
      `<option value="">Choose an account</option>` +
      (described.suppliers || [])
        .map((s) => `<option value="${s}">${s}</option>`)
        .join("");
    $("signInNote").textContent =
      `${described.title} accepts ${(described.accepts || []).join(", ")}. ` +
      described.note;
  } catch (error) {
    $("supplier").innerHTML = `<option value="">unavailable</option>`;
    $("signInNote").textContent =
      "The retailer's platform is not answering. Nothing can be sent until it is.";
  }
}

$("supplier").onchange = (event) => {
  $("go").disabled = !event.target.value;
};

$("go").onclick = () => {
  state.supplier = $("supplier").value;
  $("whoSupplier").textContent = `${state.supplier} · ${state.system}`;
  $("systemName").textContent = state.system;
  $("who").hidden = false;
  $("signIn").hidden = true;
  loadProducts();
};

$("signOut").onclick = () => location.reload();

/* --- products ----------------------------------------------------------- */

async function loadProducts(query = "") {
  $("catalogue").hidden = false;
  $("detail").hidden = true;
  $("products").innerHTML = `<p class="lede">Loading…</p>`;

  const data = await api(
    `/portal-api/${state.system}/products?supplier=${state.supplier}` +
      `&q=${encodeURIComponent(query)}`
  );
  const products = data.products || [];
  if (!products.length) {
    $("products").innerHTML = `<p class="lede">Nothing matches.</p>`;
    return;
  }

  $("products").innerHTML = products
    .map(
      (p) => `<div class="card">
        <div>
          <b>${p.name}</b>
          <div class="meta">${p.category}${p.regulated ? " · regulated" : ""}</div>
          <div class="skus">${(p.variants || [])
            .map((v) => `<code>${v.sku}</code>`)
            .join("")}</div>
          ${p.last_sent
            ? `<div class="meta">last sent ${p.last_sent.doc_ref || ""} on ${
                (p.last_sent.at || "").slice(0, 10)}</div>`
            : `<div class="meta">nothing sent yet</div>`}
        </div>
        <button class="ghost tiny" data-open="${p.product_id}">Open</button>
      </div>`
    )
    .join("");

  $("products").querySelectorAll("[data-open]").forEach((button) => {
    button.onclick = () => openProduct(button.dataset.open);
  });
}

let searchTimer;
$("search").oninput = (event) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadProducts(event.target.value), 220);
};

$("back").onclick = () => loadProducts($("search").value);

/* --- one product -------------------------------------------------------- */

async function openProduct(productId) {
  const spec = await api(
    `/portal-api/${state.system}/products/${productId}?supplier=${state.supplier}`
  );
  state.product = productId;
  state.spec = spec;

  $("catalogue").hidden = true;
  $("detail").hidden = false;
  $("detailName").textContent = spec.product.name;
  $("detailMeta").textContent =
    `${spec.product.category} · ${spec.variants.length} variant(s) · ` +
    `your documents: ${(spec.documents || []).join(", ") || "none"}`;

  $("specRows").innerHTML = spec.attributes
    .flatMap((row) =>
      Object.entries(row.values).map(
        ([variantId, cell]) => `<tr>
          <td>${row.label}${row.safety_class ? `<span class="safety">safety</span>` : ""}
              <br><code>${row.path}</code></td>
          <td><code>${skuOf(variantId)}</code></td>
          <td><b>${format(cell.value)}</b> ${row.unit || ""}</td>
          <td><code>${cell.doc || "—"}</code>
              <br><span class="${cell.mine ? "mine" : "theirs"}">${
                cell.mine ? "you asserted this" : "from another source"
              }</span></td>
          <td><button class="ghost tiny" data-revise="${row.path}"
                      data-entity="${variantId}"
                      data-safety="${row.safety_class}"
                      data-unit="${row.unit || ""}">Revise</button></td>
        </tr>`
      )
    )
    .join("");

  $("specRows").querySelectorAll("[data-revise]").forEach((button) => {
    button.onclick = () => openSpecDialog(button.dataset);
  });

  $("imgVariant").innerHTML = spec.variants
    .map((v) => `<option value="${v.id}">${v.sku} — ${v.name}</option>`)
    .join("");

  showTab("spec");
  $("history").innerHTML = `<p class="lede">Send something, and what the
    retailer does with it appears here.</p>`;
}

const skuOf = (variantId) =>
  (state.spec.variants.find((v) => v.id === variantId) || {}).sku || variantId;

const format = (value) =>
  Array.isArray(value) ? value.join(", ") : value === null || value === undefined ? "—" : value;

document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => showTab(tab.dataset.tab);
});

function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("on", t.dataset.tab === name)
  );
  ["spec", "files", "history"].forEach((t) => {
    $(`tab-${t}`).hidden = t !== name;
  });
}

/* --- sending ------------------------------------------------------------ */

let pending = null;

function openSpecDialog(data) {
  pending = data;
  const safety = data.safety === "true";
  $("specSubject").textContent =
    `${data.revise} on ${skuOf(data.entity)}${data.unit ? ` (${data.unit})` : ""}`;
  $("specValue").value = "";
  $("specNote").value = "";
  $("specDate").value = "";
  $("noteReq").textContent = safety ? "(required — this is a safety declaration)" : "(optional)";
  $("specWarn").hidden = !safety;
  $("specWarn").textContent = safety
    ? "A safety declaration is checked by a person before anything is published, and a note saying what changed is required."
    : "";
  $("specDialog").showModal();
}

$("specForm").onsubmit = async (event) => {
  if (event.submitter && event.submitter.value !== "send") return;
  event.preventDefault();
  $("specDialog").close();

  try {
    const result = await post(`/portal-api/${state.system}/spec`, {
      supplier: state.supplier,
      entity_id: pending.entity,
      attribute_path: pending.revise,
      new_value: $("specValue").value,
      unit: pending.unit,
      effective_from: $("specDate").value,
      note: $("specNote").value,
      idempotency_key: `${state.supplier}:${pending.entity}:${pending.revise}:${Date.now()}`,
    });
    toast(`Sent. Recorded as ${result.doc_ref}.`);
    watch(result.submission_id);
    openProduct(state.product);
  } catch (error) {
    toast(error.message, true);
  }
};

$("docForm").onsubmit = async (event) => {
  event.preventDefault();
  const file = $("docFile").files[0];
  if (!file) return;
  try {
    const result = await post(`/portal-api/${state.system}/document`, {
      supplier: state.supplier,
      product_id: state.product,
      filename: file.name,
      media_type: file.type,
      content_base64: await b64(file),
      text: $("docText").value,
      note: $("docNote").value,
    });
    toast(result.extractable
      ? `Sent as ${result.doc_ref}, and it will be read.`
      : `Sent as ${result.doc_ref}. ${result.reason}`);
    watch(result.submission_id);
    $("docForm").reset();
  } catch (error) {
    toast(error.message, true);
  }
};

$("imgForm").onsubmit = async (event) => {
  event.preventDefault();
  const file = $("imgFile").files[0];
  if (!file) return;
  try {
    const result = await post(`/portal-api/${state.system}/image`, {
      supplier: state.supplier,
      entity_id: $("imgVariant").value,
      role: $("imgRole").value,
      filename: file.name,
      media_type: file.type,
      content_base64: await b64(file),
      alt_text: $("imgAlt").value,
    });
    toast(`Image sent as ${result.role}.`);
    watch(result.submission_id);
    $("imgForm").reset();
  } catch (error) {
    toast(error.message, true);
  }
};

$("newProduct").onclick = () => $("draftDialog").showModal();

$("draftForm").onsubmit = async (event) => {
  if (event.submitter && event.submitter.value !== "send") return;
  event.preventDefault();
  $("draftDialog").close();
  try {
    const result = await post(`/portal-api/${state.system}/draft`, {
      supplier: state.supplier,
      name: $("draftName").value,
      category: $("draftCategory").value,
      note: $("draftNote").value,
    });
    toast(result.note);
    watch(result.submission_id);
    $("draftForm").reset();
  } catch (error) {
    toast(error.message, true);
  }
};

/* --- the relay back ----------------------------------------------------- */

const watching = new Set();

async function watch(submissionId) {
  if (!submissionId) return;
  watching.add(submissionId);
  showTab("history");
  render(
    await api(
      `/portal-api/${state.system}/submission/${submissionId}?supplier=${state.supplier}`
    )
  );
}

function render(status) {
  if (!status || status.error) return;
  const stages = (status.stages || [])
    .map(
      (s) => `<div class="stage ${s.done ? "done" : ""}">
        <span class="dot">${s.done ? "●" : "○"}</span>
        <b>${s.stage}</b>
        <span class="say">${s.detail}</span>
      </div>`
    )
    .join("");

  const verdictStage = (status.stages || []).find((s) => s.stage === "verdict");
  const verdicts = ((verdictStage && verdictStage.verdicts) || [])
    .map(
      (v) => `<div class="verdict">
        <span class="word ${v.verdict}">${v.verdict.replace(/_/g, " ")}</span>
        — <code>${v.sku}</code>
        ${v.findings.length
          ? `<ul>${v.findings.map((f) => `<li>${f}</li>`).join("")}</ul>`
          : `<div class="caveat">nothing outstanding</div>`}
        ${v.caveat ? `<div class="caveat">${v.caveat}</div>` : ""}
      </div>`
    )
    .join("");

  $("history").innerHTML =
    `<div class="timeline">${stages}</div>` +
    (verdicts ? `<div class="verdicts"><h2>Is it fit to launch?</h2>${verdicts}</div>` : "");
}

/* Live: the portal's own server polls the platform and pushes here. */
const stream = new EventSource("/api/stream");
stream.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.kind === "progress" && watching.has(message.submission_id)) {
    render(message.status);
  }
};

/* --- the protocol log --------------------------------------------------- */

$("showCalls").onclick = async () => {
  const { calls, endpoints } = await api("/api/mcp");
  $("calls").innerHTML =
    endpoints
      .map(
        (e) => `<div><span>${e.state}</span><span>${e.url}</span>
          <span>${e.tools.length} tools</span><span></span></div>`
      )
      .join("") +
    calls
      .map(
        (c) => `<div class="${c.ok ? "" : "bad"}">
          <span>${c.ts.slice(11, 19)}</span>
          <span>${c.endpoint} · ${c.tool}</span>
          <span>${c.ms} ms</span>
          <span>${c.ok ? "ok" : c.error}</span></div>`
      )
      .join("");
  $("callsDialog").showModal();
};

$("closeCalls").onclick = () => $("callsDialog").close();

boot();
