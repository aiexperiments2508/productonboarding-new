/* Storefront.
 *
 * Every value on the page comes from one call to one channel's publication
 * server. There is no local catalog and nothing cached across a correction:
 * when a field is redacted the next read says so, and the page says so too.
 */

const $ = (id) => document.getElementById(id);
const state = { channel: "ch-web", sku: null, platform: "" };

const api = (path) => fetch(path).then((r) => r.json());

/* Make a non-button behave like one.
 *
 * The shelf tiles and the thumbnail strip are a div and an img carrying click
 * handlers, which works for a mouse and is completely inert for everything
 * else. Pointer, Enter and Space all reach the same place from here, and the
 * markup carries the role and the tab stop that let a keyboard find them at
 * all. Space is preventDefault'd because its default on a focused element is
 * to scroll the page. */
function activate(node, run) {
  node.onclick = run;
  node.onkeydown = (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    run();
  };
}

/* Money is not modelled anywhere in this system, and inventing a price feed
 * would be inventing data. These are the seed pack's own prices, written here
 * because a product page without a price does not read as a product page.
 *
 * Keyed by variant id and not by SKU, which is how the generator keys them
 * too. A SKU is a brand's name for a thing and changes when the brand does -
 * these were keyed by SKU, the assortment was rebranded, and every price
 * silently became blank. A variant id is the catalog's own name for it and
 * does not move. A line with no price here shows none, which is the honest
 * rendering of a price we do not have. */
const PRICES = {
  "VAR-01A": "£149.00",
  "VAR-01B": "£199.00",
  "VAR-02A": "£1.25",
  "VAR-02B": "£6.00",
  "VAR-03A": "£59.00",
  "VAR-04A": "£34.50",
  "VAR-05A": "£3.75",
  "VAR-06A": "£27.00",
};

/** The price for a listing, by the id the catalog knows it by. */
const priceOf = (listing) =>
  PRICES[(listing && listing.variant && listing.variant.id) || ""] || "";

const LABELS = {
  "specs.power_w": "Power",
  "specs.noise_db": "Noise level",
  "specs.coverage_m2": "Room coverage",
  "specs.filter_type": "Filter",
  "energy.class": "Energy class",
  "food.ingredients": "Ingredients",
  "food.allergens.contains": "Allergens",
  "food.allergens.may_contain": "May contain",
  "food.net_weight_g": "Net weight",
  "food.fibre_g": "Fibre",
  "identifiers.gtin": "GTIN",
  claims: "Claims",
};

const label = (path) => LABELS[path] || path;
const show = (value) => (Array.isArray(value) ? value.join(", ") : value);

/* --- boot ---------------------------------------------------------------- */

async function boot() {
  const { channels, platform } = await api("/shop-api/channels");
  state.platform = platform;
  $("footLink").textContent = `serving from ${platform}`;

  $("channels").innerHTML = channels
    .map((c) => `<button data-c="${c.id}" title="${c.kind}">${c.title}</button>`)
    .join("");
  $("channels").querySelectorAll("button").forEach((button) => {
    button.onclick = () => {
      state.channel = button.dataset.c;
      paintChannels();
      state.sku ? openProduct(state.sku) : shelf();
    };
  });

  paintChannels();
  shelf();
}

function paintChannels() {
  $("channels")
    .querySelectorAll("button")
    .forEach((b) => b.classList.toggle("on", b.dataset.c === state.channel));
}

/* --- shelf --------------------------------------------------------------- */

async function shelf() {
  state.sku = null;
  $("pdp").hidden = true;
  $("shelf").hidden = false;
  $("grid").innerHTML = `<p>Loading…</p>`;

  const { products } = await api(`/shop-api/${state.channel}/shelf`);
  if (!products.length) {
    $("grid").innerHTML = `<p>This channel is not carrying any of these lines.</p>`;
    return;
  }

  $("grid").innerHTML = products
    .map((p) => {
      const hero = pickImage(p.media);
      const held = p.withheld || p.redacted_fields.length;
      // A div with an onclick is a div nobody can reach without a mouse.
      return `<div class="tile" role="button" tabindex="0"
                   aria-label="${p.product.name}" data-sku="${p.sku}">
        <div class="shot">${hero ? `<img src="${hero}" alt="">` : ""}</div>
        <b>${p.product.name}</b>
        <div class="p">${priceOf(p)}</div>
        ${held ? `<span class="flag">information being updated</span>` : ""}
      </div>`;
    })
    .join("");

  $("grid").querySelectorAll(".tile").forEach((tile) => {
    activate(tile, () => openProduct(tile.dataset.sku));
  });
}

/* Images are static files served by the platform, on the platform's origin.
 * Resolving them here rather than proxying them through this process is the
 * honest arrangement: the *data* on this page came over MCP, and an <img> tag
 * pointing at another host is a browser fetching a picture, not this
 * application reaching around the protocol for content. Proxying would make
 * the network diagram tidier and the claim weaker. */
const mediaUrl = (uri) =>
  uri && uri.startsWith("/") ? `${state.platform}${uri}` : uri;

const pickImage = (media) => {
  const order = ["HERO", "PACK_FRONT", "IN_SITU", "DETAIL", "INGREDIENT_PANEL"];
  for (const role of order) {
    const found = (media || []).find((m) => m.role === role);
    if (found) return mediaUrl(found.uri);
  }
  return null;
};

/* --- product page -------------------------------------------------------- */

async function openProduct(sku) {
  const page = await api(`/shop-api/${state.channel}/product/${sku}`);
  if (!page.found) {
    flash(page.reason || "not carried on this channel");
    return;
  }
  state.sku = sku;
  $("shelf").hidden = true;
  $("pdp").hidden = false;

  $("crumb").textContent = (page.product.category || "").split(".").join(" › ");
  $("title").textContent = page.variant.name || page.product.name;
  $("sku").textContent = sku;
  $("price").textContent = priceOf(page);

  const hero = pickImage(page.media);
  $("hero").src = hero || "";
  $("hero").alt = page.product.name;
  $("thumbs").innerHTML = (page.media || [])
    .map((m, i) => `<img src="${mediaUrl(m.uri)}" alt="${m.alt_text}" data-i="${i}"
                         role="button" tabindex="0"
                         class="${mediaUrl(m.uri) === hero ? "on" : ""}">`)
    .join("");
  $("thumbs").querySelectorAll("img").forEach((thumb) => {
    activate(thumb, () => {
      $("hero").src = thumb.src;
      $("thumbs").querySelectorAll("img").forEach((t) => t.classList.remove("on"));
      thumb.classList.add("on");
    });
  });

  // A listing the retailer has taken off air. The shop says so plainly rather
  // than 404ing: a shopper who had it in a basket needs to know why.
  $("withheld").hidden = !page.withheld;
  $("withheldWhy").textContent = page.notice || "";
  $("buy").disabled = !!page.withheld;
  $("buy").textContent = page.withheld ? "Unavailable" : "Add to basket";

  // Copy that quotes a withheld value is withheld with it. A bullet reading
  // "may contain milk" above a spec row that says the allergen statement is
  // being checked would make the page worse than before it was corrected.
  const copy = Object.fromEntries((page.copy || []).map((c) => [c.field, c]));
  const bullets = copy.bullets;
  $("bullets").innerHTML = !bullets
    ? ""
    : bullets.redacted
    ? `<div class="redacted">Product details are being updated
         <em>${bullets.notice}</em></div>`
    : `<ul>${bullets.text.split("\n").map((l) => `<li>${l}</li>`).join("")}</ul>`;

  const description = copy.description;
  $("description").innerHTML = !description
    ? ""
    : description.redacted
    ? `<span class="redacted">This description is being updated
         <em>${description.notice}</em></span>`
    : escapeHtml(description.text);

  $("specs").innerHTML = Object.entries(page.fields)
    .sort()
    .map(([path, cell]) => {
      const body = cell.redacted
        ? `<span class="redacted">${cell.placeholder || "Temporarily unavailable"}
             <em>${cell.notice || ""}</em></span>`
        : show(cell.value) + (cell.unit ? ` ${cell.unit}` : "");
      return `<tr><td>${label(path)}</td><td>${body}</td></tr>`;
    })
    .join("");
}

$("back").onclick = shelf;
$("home").onclick = (event) => {
  event.preventDefault();
  shelf();
};
$("buy").onclick = () => flash("This is a demonstration shop. Nothing is for sale.");

/* --- the delivery log ----------------------------------------------------- */

$("showLog").onclick = async () => {
  const { entries } = await api(`/shop-api/${state.channel}/log`);
  $("log").innerHTML = (entries || []).length
    ? entries
        .map(
          (e) => `<div>
            <span>${(e.ts || "").slice(11, 19)}</span>
            <b>${e.verb}</b>
            <span class="who">${e.listing_id} · ${e.actor}
              ${e.detail && e.detail.reason ? `— ${e.detail.reason}` : ""}</span>
          </div>`
        )
        .join("")
    : `<div><span></span><b>nothing yet</b><span class="who">this channel has not been told anything</span></div>`;
  $("logDialog").showModal();
};

$("closeLog").onclick = () => $("logDialog").close();

const escapeHtml = (text) =>
  String(text || "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

function flash(message) {
  const node = document.createElement("div");
  node.className = "flash";
  node.textContent = message;
  $("flashes").append(node);
  setTimeout(() => node.remove(), 8000);
}

/* --- live ---------------------------------------------------------------- */

const stream = new EventSource("/api/stream");
stream.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.kind !== "changed" || message.channel !== state.channel) return;

  const verbs = (message.changes || []).map((c) => c.verb);
  if (verbs.includes("REDACT")) flash("A field on this channel has just been withheld.");
  else if (verbs.includes("RESTORE")) flash("A withheld field has been restored.");
  else flash("This channel has just been updated.");

  // Re-read rather than patch. The page is a view of what the channel says it
  // is showing, and a locally applied change would be this shop's own opinion
  // of that - which is the one thing it must never have.
  state.sku ? openProduct(state.sku) : shelf();
};

boot();
