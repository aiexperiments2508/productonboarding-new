/* Back Office - vanilla, no build step, no framework, no node_modules.
 *
 * Every fetch is relative to this origin. This page cannot see the platform
 * and must not try: its own server holds the MCP session, and a page that knew
 * the platform's address would be a page that could reach past it.
 * `tests/test_app_boundary.py` fails the build on an absolute URL in here.
 *
 * The shape of every screen is the same two calls - list what arrived, then
 * open one - because that is the whole of the protocol these four systems
 * offer. A screen that looked richer than the interface underneath it would be
 * a screen that had stopped telling the truth about the interface.
 */

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

const state = {
  systems: [],
  depot: null,
  market: null,
  cache: {},          // "system/event" -> payload
  deliveries: {},     // system -> rows
};

function say(message, bad) {
  const bar = $("#status");
  bar.textContent = message;
  bar.classList.toggle("bad", !!bad);
}

async function get(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${response.status} ${path}`);
  return response.json();
}

/* --- the protocol, once ---------------------------------------------------
 *
 * A payload is fetched at most once per session. Every screen reads out of
 * `state.cache`, so switching tabs is free and the protocol tab shows the
 * calls that were actually needed rather than one per render.
 */

async function deliveries(systemId, limit) {
  if (state.deliveries[systemId]) return state.deliveries[systemId];
  const body = await get(`/back-api/${systemId}/deliveries?limit=${limit || 60}`);
  if (body.unreachable) {
    say(body.error || "the platform is not answering", true);
    return [];
  }
  state.deliveries[systemId] = body.deliveries || [];
  return state.deliveries[systemId];
}

async function payload(systemId, eventId) {
  const key = `${systemId}/${eventId}`;
  if (state.cache[key]) return state.cache[key];
  const body = await get(`/back-api/${systemId}/payload/${eventId}`);
  const inner = body.payload || {};
  // `fetch_payload` answers with the whole event; the domain data is inside.
  state.cache[key] = inner.payload || inner;
  return state.cache[key];
}

async function payloadsOfType(systemId, type, limit) {
  const rows = await deliveries(systemId, limit);
  const out = [];
  for (const row of rows) {
    const body = await payload(systemId, row.event_id);
    if (!body || Object.keys(body).length === 0) continue;
    if (!type || row.type === type || body.__type === type) out.push(body);
  }
  return out;
}

/* --- stock ---------------------------------------------------------------- */

async function renderStock() {
  const all = await payloadsOfType("wms-inventory", null, 60);
  const snapshots = all.filter((p) => p.warehouse_id);
  if (!snapshots.length) return emptyInto("#stock-lines", "no deliveries yet");

  /* The newest week per depot. Ten weeks of history is what this system holds;
     what an operator wants on opening the page is what is there now. */
  const newest = {};
  for (const snap of snapshots) {
    const held = newest[snap.warehouse_id];
    if (!held || snap.week_start > held.week_start) newest[snap.warehouse_id] = snap;
  }

  const depots = Object.values(newest).sort((a, b) =>
    a.warehouse_id.localeCompare(b.warehouse_id));
  if (!state.depot) state.depot = depots[0].warehouse_id;

  const cards = $("#depots");
  cards.innerHTML = "";
  for (const depot of depots) {
    const onHand = depot.lines.reduce((sum, l) => sum + l.on_hand, 0);
    const card = el("button", `card${depot.warehouse_id === state.depot ? " on" : ""}`);
    card.appendChild(el("h3", null, depot.warehouse_name));
    card.appendChild(el("div", "where",
      `${depot.country} · serves ${depot.serves_markets.join(", ")}`));
    const figs = el("div", "figs");
    for (const [value, label] of [[onHand.toLocaleString(), "units"],
                                  [depot.lines.length, "lines"],
                                  [depot.week_start, "week"]]) {
      const box = el("div");
      box.appendChild(el("b", null, String(value)));
      box.appendChild(el("span", null, label));
      figs.appendChild(box);
    }
    card.appendChild(figs);
    card.onclick = () => { state.depot = depot.warehouse_id; renderStock(); };
    cards.appendChild(card);
  }

  const chosen = newest[state.depot];
  const body = $("#stock-lines tbody");
  body.innerHTML = "";
  for (const line of chosen.lines.slice(0, 200)) {
    const low = line.on_hand < line.reorder_point;
    const row = el("tr");
    row.appendChild(el("td", "k", line.sku));
    row.appendChild(el("td", null, line.variant_id));
    row.appendChild(el("td", "n", line.on_hand.toLocaleString()));
    row.appendChild(el("td", "n", line.allocated.toLocaleString()));
    row.appendChild(el("td", "n", line.reorder_point.toLocaleString()));
    const standing = el("td");
    standing.appendChild(el("span", `tag ${low ? "warn" : "ok"}`,
      low ? "below reorder" : "in stock"));
    row.appendChild(standing);
    body.appendChild(row);
  }
  say(`${chosen.warehouse_name}: ${chosen.lines.length} lines, week of ${chosen.week_start}`);
}

/* --- trading -------------------------------------------------------------- */

async function renderTrading() {
  const all = await payloadsOfType("trading-epos", null, 30);
  const periods = all.filter((p) => p.period_start);
  if (!periods.length) return emptyInto("#sales-lines", "no deliveries yet");

  const markets = [...new Set(periods.map((p) => p.market_id))].sort();
  if (!state.market) state.market = markets[0];

  const picker = $("#market-picker");
  picker.innerHTML = "";
  for (const market of markets) {
    const button = el("button", market === state.market ? "on" : "", market);
    button.onclick = () => { state.market = market; renderTrading(); };
    picker.appendChild(button);
  }

  /* The newest month for the chosen market. */
  const mine = periods.filter((p) => p.market_id === state.market)
    .sort((a, b) => b.period_start.localeCompare(a.period_start));
  const latest = mine[0];
  const lines = [...latest.lines].sort((a, b) => b.units - a.units).slice(0, 25);

  const body = $("#sales-lines tbody");
  body.innerHTML = "";
  for (const line of lines) {
    const row = el("tr");
    row.appendChild(el("td", "n", String(line.rank_in_category)));
    row.appendChild(el("td", "k", line.sku));
    row.appendChild(el("td", null, line.variant_id));
    row.appendChild(el("td", "muted", line.category));
    row.appendChild(el("td", "n", line.units.toLocaleString()));
    row.appendChild(el("td", "n",
      `${latest.currency} ${line.revenue.toLocaleString()}`));
    body.appendChild(row);
  }
  say(`${state.market}: ${latest.period_start} to ${latest.period_end}, top 25 of ${latest.lines.length}`);
}

/* --- campaigns ------------------------------------------------------------ */

async function renderCampaigns() {
  const all = await payloadsOfType("campaign-manager", null, 70);
  /* `objective`, not `campaign_id`: a PROMOTION carries a campaign_id too, and
     has no keywords - so filtering on the shared field puts a promotion into
     the campaign table and the render throws on the first one. */
  const campaigns = all.filter((p) => p.objective)
    .sort((a, b) => a.starts_on.localeCompare(b.starts_on));
  if (!campaigns.length) return emptyInto("#campaigns", "no deliveries yet");

  const body = $("#campaigns tbody");
  body.innerHTML = "";
  for (const campaign of campaigns) {
    const row = el("tr");
    row.appendChild(el("td", null, campaign.name));
    const objective = el("td");
    objective.appendChild(el("span", "tag", campaign.objective));
    row.appendChild(objective);
    row.appendChild(el("td", "k", campaign.market_id));
    row.appendChild(el("td", "muted", `${campaign.starts_on} → ${campaign.ends_on}`));
    row.appendChild(el("td", "n", String(campaign.members.length)));
    row.appendChild(el("td", "muted", campaign.keywords.join(", ")));
    body.appendChild(row);
  }
  say(`${campaigns.length} campaigns`);
}

/* --- compliance ----------------------------------------------------------- */

async function renderCompliance() {
  const all = await payloadsOfType("cert-registry", null, 100);
  const certificates = all.filter((p) => p.certificate_ref);
  if (!certificates.length) return emptyInto("#certificates", "no deliveries yet");

  /* Soonest first. The whole reason to open this tab is to find out what is
     about to lapse, and sorting by reference would bury that. */
  certificates.sort((a, b) => a.expires_on.localeCompare(b.expires_on));

  const today = new Date();
  const body = $("#certificates tbody");
  body.innerHTML = "";
  for (const certificate of certificates) {
    const expires = new Date(certificate.expires_on);
    const days = Math.round((expires - today) / 86400000);
    const row = el("tr");
    row.appendChild(el("td", "k", certificate.certificate_ref));
    row.appendChild(el("td", null, certificate.scheme));
    row.appendChild(el("td", "muted", certificate.issuer));
    row.appendChild(el("td", "k", certificate.expires_on));
    const remaining = el("td", "n");
    remaining.appendChild(el("span",
      `tag ${days < 0 ? "bad" : days <= 90 ? "warn" : "ok"}`,
      days < 0 ? "lapsed" : `${days}d`));
    row.appendChild(remaining);
    row.appendChild(el("td", "k", certificate.scope.join(", ")));
    body.appendChild(row);
  }
  say(`${certificates.length} certificates on the register`);
}

/* --- protocol ------------------------------------------------------------- */

async function renderProtocol() {
  const body = $("#calls tbody");
  body.innerHTML = "";
  const status = await get("/api/mcp");
  for (const call of (status.calls || []).slice(0, 60)) {
    const row = el("tr");
    row.appendChild(el("td", "k", (call.ts || "").slice(11, 19)));
    row.appendChild(el("td", "k", call.endpoint || ""));
    row.appendChild(el("td", null, call.tool || ""));
    row.appendChild(el("td", "n", String(Math.round(call.ms || 0))));
    const result = el("td");
    result.appendChild(el("span", `tag ${call.ok ? "ok" : "bad"}`,
      call.ok ? "ok" : (call.error || "failed").slice(0, 60)));
    row.appendChild(result);
    body.appendChild(row);
  }
  const states = Object.entries(status.endpoints || {})
    .map(([name, info]) => `${name}=${info.state}`).join("  ");
  say(states || "no endpoints dialled yet");
}

function emptyInto(selector, message) {
  const table = $(selector);
  const columns = table.querySelectorAll("thead th").length;
  table.querySelector("tbody").innerHTML =
    `<tr><td class="empty" colspan="${columns}">${message}</td></tr>`;
  say(message);
}

/* --- shell ---------------------------------------------------------------- */

const RENDER = {
  stock: renderStock,
  trading: renderTrading,
  campaigns: renderCampaigns,
  compliance: renderCompliance,
  protocol: renderProtocol,
};

async function show(name) {
  for (const tab of document.querySelectorAll(".view")) {
    const on = tab.dataset.view === name;
    tab.classList.toggle("on", on);
    tab.setAttribute("aria-selected", String(on));
  }
  for (const panel of document.querySelectorAll("main section")) {
    panel.hidden = panel.id !== `v-${name}`;
  }
  say("reading over MCP…");
  try {
    await RENDER[name]();
  } catch (error) {
    say(String(error), true);
  }
}

async function counts() {
  const body = await get("/back-api/systems");
  state.systems = body.systems;
  $("#platform").textContent = body.platform;
  const box = $("#counts");
  box.innerHTML = "";
  for (const system of body.systems) {
    const rows = state.deliveries[system.id];
    const chip = el("span", "c");
    chip.appendChild(el("b", null, system.title));
    chip.append(` ${rows ? rows.length : "–"}`);
    box.appendChild(chip);
  }
}

document.querySelectorAll(".view").forEach((tab) => {
  tab.onclick = () => show(tab.dataset.view);
});
$("#showCalls").onclick = () => show("protocol");

/* A delivery this console has not seen invalidates the cache for that system
   only. Reloading everything on every event would make a busy estate reload
   the page continuously. */
const stream = new EventSource("/api/stream");
stream.onmessage = (event) => {
  try {
    const message = JSON.parse(event.data);
    if (message.kind === "delivered" && message.payload) {
      delete state.deliveries[message.payload.system];
      counts();
    }
  } catch (_) { /* a keepalive is not JSON */ }
};

counts().then(() => show("stock"));
