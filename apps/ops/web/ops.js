/* Ops Console.
 *
 * Reads the whole publication estate, one MCP call per channel. Writes exactly
 * one thing: that an erratum has been published or a reprint confirmed - which
 * is the only fact in this system that nobody but the team that did the work
 * can know.
 */

const $ = (id) => document.getElementById(id);
const state = { channels: [], queues: [], platform: "" };

const api = (path) => fetch(path).then((r) => r.json());
const post = (path, body) =>
  fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

/* --- views --------------------------------------------------------------- */

document.querySelectorAll(".view").forEach((button) => {
  button.onclick = () => {
    document.querySelectorAll(".view").forEach((b) =>
      b.classList.toggle("on", b === button)
    );
    ["estate", "owed", "ledger", "inspect"].forEach((v) => {
      $(`v-${v}`).hidden = v !== button.dataset.view;
    });
    if (button.dataset.view === "ledger") ledger();
    if (button.dataset.view === "owed") owed();
  };
});

/* --- estate -------------------------------------------------------------- */

async function boot() {
  const { channels, platform } = await api("/ops-api/channels");
  state.channels = channels;
  state.platform = platform;
  $("platform").textContent = platform;

  $("ledgerChannel").innerHTML =
    `<option value="">All channels</option>` +
    channels.map((c) => `<option value="${c.id}">${c.title}</option>`).join("");

  await refresh();
}

async function refresh() {
  const { queues } = await api("/ops-api/queues");
  state.queues = queues;
  const byChannel = Object.fromEntries(queues.map((q) => [q.channel, q]));

  $("estate").innerHTML = state.channels
    .map((c) => {
      const q = byChannel[c.id] || {};
      const owed = (q.obligations || []).length;
      const held = (q.withheld || []).length;
      const standing = c.frozen
        ? `<span class="tag bad">frozen</span>`
        : owed
        ? `<span class="tag warn">work owed</span>`
        : held
        ? `<span class="tag warn">holding back a field</span>`
        : `<span class="tag ok">clear</span>`;
      return `<tr>
        <td><b>${c.title}</b>${c.mine ? `<span class="mine">ours</span>` : ""}
            <div class="meta"><code>${c.channel_id || c.id}</code></div></td>
        <td>${c.kind || ""}</td>
        <td>${c.recallable
              ? `<span class="tag ok">recallable</span>`
              : `<span class="tag bad">cannot recall</span>`}</td>
        <td class="mono">${c.freeze_days ? `${c.freeze_days} d` : "—"}</td>
        <td class="mono">${held || "—"}</td>
        <td class="mono">${owed || "—"}</td>
        <td>${standing}</td>
      </tr>`;
    })
    .join("");

  const owedTotal = queues.reduce((n, q) => n + (q.obligations || []).length, 0);
  const heldTotal = queues.reduce((n, q) => n + (q.withheld || []).length, 0);
  $("counts").innerHTML =
    `<span>channels <b>${state.channels.length}</b></span>` +
    `<span class="warn">fields held back <b>${heldTotal}</b></span>` +
    `<span class="bad">work owed <b>${owedTotal}</b></span>`;

  $("estateNote").textContent = state.channels
    .filter((c) => c.why)
    .map((c) => `${c.title}: ${c.why}`)
    .join("  ·  ");

  if (!$("v-owed").hidden) owed();
}

/* --- work owed ------------------------------------------------------------ */

function owed() {
  const all = state.queues.flatMap((q) =>
    (q.obligations || []).map((o) => ({ ...o, channel: q.channel }))
  );
  if (!all.length) {
    $("owed").innerHTML = `<div class="empty">Nothing is owed. Every
      correction that reached a physical channel has been made good.</div>`;
    return;
  }
  $("owed").innerHTML = all
    .map(
      (o) => `<div class="card ${o.kind === "ERRATUM" ? "erratum" : ""}">
        <div>
          <h3>${o.kind === "ERRATUM" ? "Erratum owed" : "Reprint queued"}
            <span class="tag ${o.kind === "ERRATUM" ? "bad" : "warn"}">${o.kind}</span></h3>
          <div class="meta"><code>${o.listing_id}</code> ·
            <code>${o.attribute_path}</code> · ${o.channel_id}</div>
          <div class="why">${(o.detail || {}).reason || ""}</div>
          <div class="due">opened ${(o.opened_at || "").slice(0, 10)} ·
            due ${(o.due_by || "").slice(0, 10)}</div>
        </div>
        <button class="btn primary" data-ob="${o.id}" data-ch="${o.channel}"
                data-kind="${o.kind}">Record it done</button>
      </div>`
    )
    .join("");

  $("owed").querySelectorAll("[data-ob]").forEach((button) => {
    button.onclick = () => openDischarge(button.dataset);
  });
}

let discharging = null;

function openDischarge(data) {
  discharging = data;
  $("dischargeTitle").textContent =
    data.kind === "ERRATUM" ? "Record the erratum as published" : "Confirm the reprint";
  $("dischargeWhat").textContent = data.ob;
  $("dischargeEvidence").value = "";
  $("dischargeDialog").showModal();
}

$("dischargeForm").onsubmit = async (event) => {
  if (event.submitter && event.submitter.value !== "ok") return;
  event.preventDefault();
  $("dischargeDialog").close();
  const result = await post("/ops-api/discharge", {
    channel: discharging.ch,
    obligation_id: discharging.ob,
    actor: $("dischargeWho").value,
    evidence: $("dischargeEvidence").value,
  });
  alertBox(result.discharged ? "Recorded." : result.error || "Refused.",
           !result.discharged);
  await refresh();
  owed();
};

/* --- ledger --------------------------------------------------------------- */

async function ledger() {
  const channel = $("ledgerChannel").value;
  const { entries } = await api(
    `/ops-api/log?limit=80${channel ? `&channel=${channel}` : ""}`
  );
  $("ledger").innerHTML = entries.length
    ? entries
        .map(
          (e) => `<tr>
            <td class="mono">${(e.ts || "").slice(0, 19).replace("T", " ")}</td>
            <td class="mono">${e.channel}</td>
            <td>${verbTag(e.verb)}</td>
            <td class="mono">${e.listing_id}</td>
            <td>${e.actor}</td>
            <td>${(e.detail || {}).reason || (e.detail || {}).attribute_path || ""}</td>
          </tr>`
        )
        .join("")
    : `<tr><td colspan="6" class="mono">nothing recorded yet</td></tr>`;
}

const verbTag = (verb) => {
  const tone =
    verb === "REDACT" || verb === "ERRATUM_OPEN"
      ? "bad"
      : verb === "REPRINT_QUEUE"
      ? "warn"
      : verb === "COMMIT" || verb.endsWith("CONFIRM") || verb.endsWith("DISCHARGE")
      ? "ok"
      : "dim";
  return `<span class="tag ${tone}">${verb}</span>`;
};

$("ledgerChannel").onchange = ledger;

/* --- inspect -------------------------------------------------------------- */

$("inspect").onclick = async () => {
  const sku = $("sku").value.trim();
  $("inspection").innerHTML = `<div class="empty">Asking every channel…</div>`;

  const pages = await Promise.all(
    state.channels.map(async (c) => ({
      channel: c,
      page: await api(`/ops-api/${c.id}/listing/${encodeURIComponent(sku)}`),
    }))
  );

  const carried = pages.filter((p) => p.page && p.page.found);
  if (!carried.length) {
    $("inspection").innerHTML = `<div class="empty">No channel carries ${sku}.</div>`;
    return;
  }

  $("inspection").innerHTML = carried
    .map(({ channel, page }) => {
      const fields = Object.entries(page.fields || {})
        .sort()
        .map(
          ([path, cell]) => `<div class="f ${cell.redacted ? "hidden" : ""}">
            <span class="k">${path}</span>
            <span class="v">${
              cell.redacted
                ? `withheld — ${cell.notice || "being updated"}`
                : Array.isArray(cell.value)
                ? cell.value.join(", ")
                : cell.value
            }</span></div>`
        )
        .join("");
      return `<div class="chan">
        <h3>${channel.title}
          ${page.withheld ? `<span class="tag bad">listing withheld</span>` : ""}
          ${page.redacted_fields.length
            ? `<span class="tag warn">${page.redacted_fields.length} field(s) held back</span>`
            : `<span class="tag ok">complete</span>`}
        </h3>
        <div class="meta mono">${page.listing_id} · ${page.status} ·
          version ${page.published_version || "—"}</div>
        <div class="fields">${fields || `<div class="none">no values</div>`}</div>
      </div>`;
    })
    .join("");
};

/* --- protocol log ---------------------------------------------------------- */

$("showCalls").onclick = async () => {
  const { calls, endpoints } = await api("/api/mcp");
  $("calls").innerHTML =
    endpoints
      .map((e) => `<div><span>${e.state}</span><span>${e.url}</span>
        <span>${e.tools.length}t</span><span></span></div>`)
      .join("") +
    calls
      .map(
        (c) => `<div class="${c.ok ? "" : "bad"}">
          <span>${c.ts.slice(11, 19)}</span>
          <span>${c.endpoint} · ${c.tool}</span>
          <span>${c.ms}ms</span>
          <span>${c.ok ? "ok" : c.error}</span></div>`
      )
      .join("");
  $("callsDialog").showModal();
};

$("closeCalls").onclick = () => $("callsDialog").close();

function alertBox(message, bad = false) {
  const node = document.createElement("div");
  node.className = "alert" + (bad ? " warn" : "");
  node.textContent = message;
  $("alerts").append(node);
  setTimeout(() => node.remove(), 8000);
}

/* --- live ------------------------------------------------------------------ */

const stream = new EventSource("/api/stream");
stream.onmessage = async (event) => {
  const message = JSON.parse(event.data);
  if (message.kind !== "changed") return;
  const verbs = (message.changes || []).map((c) => c.verb);
  alertBox(`${message.channel}: ${verbs.join(", ")}`, verbs.includes("REDACT"));
  await refresh();
  if (!$("v-ledger").hidden) ledger();
};

boot();
