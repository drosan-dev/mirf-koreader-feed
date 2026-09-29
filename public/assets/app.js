const STORAGE_KEY = "reed-discover.library.v1";
const ACCESS_HASH = "75c3b974218468a82111469efd1ecb1d1ae8ae2495ac1bb832d411f837344c78";

function readLibrary(storage = localStorage) {
  try {
    const value = JSON.parse(storage.getItem(STORAGE_KEY) || "{}");
    return value && value.version === 1 && value.items ? { ...value, dismissed: value.dismissed || {} } : { version: 1, items: {}, dismissed: {} };
  } catch { return { version: 1, items: {}, dismissed: {} }; }
}

function updateItem(library, id, change) {
  const items = { ...library.items };
  if (change === null) delete items[id];
  else items[id] = { ...(items[id] || {}), ...change };
  return { version: 1, items };
}

function formatMinutes(value) {
  return value ? `${Math.max(1, Number(value))} мин` : "внешняя ссылка";
}

const state = { articles: [], library: null, route: "discover", category: "" };

function saveLibrary() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.library));
}

function escapeHtml(value = "") {
  return value.replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

async function discoverTitle(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(6000) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const document = new DOMParser().parseFromString(await response.text(), "text/html");
    const title = document.querySelector('meta[property="og:title"]')?.content || document.querySelector("title")?.textContent;
    if (title?.trim()) return title.trim().replace(/\s+/g, " ");
  } catch { /* Most cross-origin sites require the optional extraction backend. */ }
  const slug = decodeURIComponent(url.pathname.split("/").filter(Boolean).at(-1) || "").replace(/[-_]+/g, " ").replace(/\.[a-z0-9]{2,5}$/i, "").trim();
  return slug ? slug.charAt(0).toLocaleUpperCase("ru") + slug.slice(1) : url.hostname.replace(/^www\./, "");
}

function articleCard(article) {
  const saved = state.library.items[article.id];
  const selected = Boolean(saved);
  const read = Boolean(saved?.read);
  const published = new Intl.DateTimeFormat("ru", { day: "numeric", month: "short" }).format(new Date(article.published));
  const readingUrl = article.readerUrl || article.url;
  const external = !article.readerUrl ? ' target="_blank" rel="noreferrer"' : "";
  const saveButton = `<button class="save ${selected ? "saved" : ""}" data-action="save" data-id="${article.id}">${selected ? "✓ В подборке" : "+ Почитать позже"}</button>`;
  const primary = state.route === "saved"
    ? `<button class="read ${read ? "saved" : ""}" data-action="read" data-id="${article.id}">${read ? "✓ Прочитано" : "Отметить прочитанным"}</button><button class="remove" data-action="remove" data-id="${article.id}">Удалить</button>`
    : state.route === "today" ? `${saveButton}<button class="remove" data-action="dismiss" data-id="${article.id}">Не читать</button>` : saveButton;
  return `<article class="card${read ? " is-read" : ""}">
    <div class="meta"><span class="source">${escapeHtml(article.source)}</span><span>·</span><span>${published}</span><span>·</span><span>${formatMinutes(article.readingMinutes)}</span></div>
    <h3><a href="${escapeHtml(readingUrl)}"${external}>${escapeHtml(article.title)}</a></h3>
    <p class="summary">${escapeHtml(article.summary || "Описание появится после следующего обновления источника.")}</p>
    <div class="actions"><a href="${escapeHtml(readingUrl)}"${external}>Читать</a>${primary}</div>
  </article>`;
}

function render() {
  const feed = document.querySelector("#feed");
  const empty = document.querySelector("#empty");
  const savedIds = new Set(Object.keys(state.library.items));
  const dismissedIds = new Set(Object.keys(state.library.dismissed));
  const today = new Date().toLocaleDateString("sv-SE");
  const base = state.route === "saved" ? state.articles.filter(a => savedIds.has(a.id)) : state.route === "today" ? state.articles.filter(a => !a.custom && !dismissedIds.has(a.id) && new Date(a.published).toLocaleDateString("sv-SE") === today) : state.articles.filter(a => !a.custom && !dismissedIds.has(a.id));
  const articles = state.category ? base.filter(a => a.category === state.category) : base;
  document.querySelector("#saved-count").textContent = savedIds.size;
  document.querySelector("#view-title").textContent = state.route === "saved" ? "Моя подборка" : state.route === "today" ? "Сегодня" : "Новые рекомендации";
  document.querySelector("#view-subtitle").textContent = state.route === "saved" ? `${base.length} ${base.length === 1 ? "материал" : "материалов"} · хранится в этом браузере` : state.route === "today" ? `${base.length} свежих материалов из ваших источников` : "Все проверенные источники";
  document.querySelectorAll("[data-route]").forEach(a => a.classList.toggle("active", a.dataset.route === state.route));
  feed.innerHTML = articles.map(articleCard).join("");
  empty.hidden = articles.length > 0;
  feed.hidden = articles.length === 0;
  document.querySelector("#status").hidden = true;
  let exportButton = document.querySelector("#export-epub");
  if (state.route === "saved" && base.length) {
    if (!exportButton) {
      exportButton = document.createElement("button"); exportButton.id = "export-epub"; exportButton.className = "primary-link"; exportButton.textContent = "Скачать EPUB";
      exportButton.addEventListener("click", () => exportEpub(base, exportButton));
      document.querySelector(".toolbar").append(exportButton);
    }
  } else exportButton?.remove();
}

function route() {
  state.route = location.hash === "#saved" ? "saved" : location.hash === "#today" ? "today" : "discover";
  state.category = ""; document.querySelector("#category-filter").value = ""; render();
}

function bytes(value) { return new TextEncoder().encode(value); }
function crc32(data) {
  let crc = -1;
  for (const byte of data) { crc ^= byte; for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1)); }
  return (crc ^ -1) >>> 0;
}
function u16(n) { return new Uint8Array([n & 255, n >>> 8 & 255]); }
function u32(n) { return new Uint8Array([n & 255, n >>> 8 & 255, n >>> 16 & 255, n >>> 24 & 255]); }
function zip(files) {
  const local = [], central = []; let offset = 0;
  for (const file of files) {
    const name = bytes(file.name), data = typeof file.data === "string" ? bytes(file.data) : file.data, crc = crc32(data);
    const header = new Uint8Array([...u32(0x04034b50), ...u16(20), ...u16(0x800), ...u16(0), ...u16(0), ...u16(0), ...u32(crc), ...u32(data.length), ...u32(data.length), ...u16(name.length), ...u16(0), ...name]);
    local.push(header, data);
    central.push(new Uint8Array([...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0x800), ...u16(0), ...u16(0), ...u16(0), ...u32(crc), ...u32(data.length), ...u32(data.length), ...u16(name.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(offset), ...name]));
    offset += header.length + data.length;
  }
  const centralSize = central.reduce((n, part) => n + part.length, 0);
  return new Blob([...local, ...central, new Uint8Array([...u32(0x06054b50), ...u16(0), ...u16(0), ...u16(files.length), ...u16(files.length), ...u32(centralSize), ...u32(offset), ...u16(0)])], { type: "application/epub+zip" });
}

async function exportEpub(articles, button) {
  button.disabled = true; button.textContent = "Собираем EPUB…";
  try {
    const chapters = await Promise.all(articles.map(async (article, index) => {
      let body;
      if (!article.readerUrl) body = `<p>${escapeHtml(article.summary)}</p><p><a href="${escapeHtml(article.url)}">Открыть исходную статью</a></p>`;
      else {
        const response = await fetch(article.readerUrl); const html = await response.text();
        const articleBody = new DOMParser().parseFromString(html, "text/html").querySelector("article");
        body = articleBody ? [...articleBody.childNodes].map(node => new XMLSerializer().serializeToString(node)).join("") : `<p>${escapeHtml(article.summary)}</p>`;
      }
      return { name: `chapter-${index + 1}.xhtml`, title: article.title, body };
    }));
    const nav = chapters.map((c, i) => `<li><a href="${c.name}">${escapeHtml(c.title)}</a></li>`).join("");
    const manifest = chapters.map((c, i) => `<item id="c${i}" href="${c.name}" media-type="application/xhtml+xml"/>`).join("");
    const spine = chapters.map((_, i) => `<itemref idref="c${i}"/>`).join("");
    const files = [
      { name: "mimetype", data: "application/epub+zip" },
      { name: "META-INF/container.xml", data: `<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>` },
      { name: "EPUB/nav.xhtml", data: `<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>Моя подборка</title></head><body><nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops"><h1>Моя подборка</h1><ol>${nav}</ol></nav></body></html>` },
      { name: "EPUB/package.opf", data: `<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:uuid:${crypto.randomUUID()}</dc:identifier><dc:title>Моя подборка · Reed Discover</dc:title><dc:language>ru</dc:language><meta property="dcterms:modified">${new Date().toISOString().replace(/\.\d+Z$/, "Z")}</meta></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>${manifest}</manifest><spine>${spine}</spine></package>` },
      ...chapters.map(c => ({ name: `EPUB/${c.name}`, data: `<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>${escapeHtml(c.title)}</title><style>body{font-family:serif;line-height:1.5}img{max-width:100%}</style></head><body><h1>${escapeHtml(c.title)}</h1>${c.body}</body></html>` }))
    ];
    const url = URL.createObjectURL(zip(files)); const link = document.createElement("a"); link.href = url; link.download = "reed-discover.epub"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { alert(`Не удалось собрать EPUB: ${error.message}`); }
  finally { button.disabled = false; button.textContent = "Скачать EPUB"; }
}

async function start() {
  state.library = readLibrary();
  try {
    if (!globalThis.REED_ARTICLES) await new Promise((resolve,reject) => { const script=document.createElement("script"); script.src="data/articles.js"; script.onload=resolve; script.onerror=()=>reject(new Error("Каталог недоступен")); document.head.append(script); });
    state.articles = globalThis.REED_ARTICLES.articles;
    const customArticles = Object.values(state.library.items).map(item => item.article).filter(Boolean);
    state.articles.push(...customArticles.filter(custom => !state.articles.some(article => article.id === custom.id)));
    const categories = [...new Set(state.articles.filter(a => !a.custom).map(a => a.category).filter(Boolean))].sort();
    document.querySelector("#category-filter").insertAdjacentHTML("beforeend", categories.map(c => `<option>${escapeHtml(c)}</option>`).join(""));
    route();
  } catch (error) { document.querySelector("#status").textContent = `Не удалось загрузить ленту. ${error.message}`; }
  addEventListener("hashchange", route);
  document.querySelector("#category-filter").addEventListener("change", event => { state.category = event.target.value; render(); });
  const panel = document.querySelector("#add-link-panel"), urlInput = document.querySelector("#add-link-url"), error = document.querySelector("#add-link-error");
  document.querySelector("#add-link-toggle").addEventListener("click", () => { panel.hidden = !panel.hidden; if (!panel.hidden) urlInput.focus(); });
  document.querySelector("#add-link-form").addEventListener("submit", async event => {
    event.preventDefault(); error.hidden = true;
    try {
      const url = new URL(urlInput.value.trim());
      if (!/^https?:$/.test(url.protocol)) throw new Error("Нужна ссылка с http:// или https://");
      url.hash = ""; for (const key of [...url.searchParams.keys()]) if (/^(utm_|fbclid$|gclid$)/i.test(key)) url.searchParams.delete(key);
      let hash = 2166136261; for (const char of url.href) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
      const id = `link-${(hash >>> 0).toString(16)}`;
      const submit = event.submitter; submit.disabled = true; submit.textContent = "Получаем заголовок…";
      const title = await discoverTitle(url);
      const article = { id, custom: true, title, source: url.hostname.replace(/^www\./, ""), summary: "Добавлено вручную · полный текст откроется на сайте источника", readingMinutes: null, published: new Date().toISOString(), category: "", url: url.href };
      state.library = updateItem(state.library, id, { savedAt: new Date().toISOString(), read: false, article });
      const existing = state.articles.findIndex(item => item.id === id); if (existing >= 0) state.articles[existing] = article; else state.articles.unshift(article);
      saveLibrary(); event.target.reset(); submit.disabled = false; submit.textContent = "Сохранить"; panel.hidden = true; location.hash = "saved"; route();
    } catch (problem) { error.textContent = problem instanceof Error ? problem.message : "Проверьте ссылку"; error.hidden = false; }
  });
  document.querySelector("#feed").addEventListener("click", event => {
    const button = event.target.closest("button[data-action]"); if (!button) return;
    const { id, action } = button.dataset, current = state.library.items[id];
    if (action === "save") state.library = updateItem(state.library, id, current ? null : { savedAt: new Date().toISOString(), read: false });
    if (action === "remove") state.library = updateItem(state.library, id, null);
    if (action === "read") state.library = updateItem(state.library, id, { read: !current?.read, readAt: current?.read ? null : new Date().toISOString() });
    if (action === "dismiss") { state.library.dismissed[id] = new Date().toISOString(); delete state.library.items[id]; }
    saveLibrary(); render();
  });
}

async function tokenHash(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2,"0")).join("");
}

async function authorize() {
  const supplied = location.hash.startsWith("#token=") ? decodeURIComponent(location.hash.slice(7)) : "";
  const remembered = localStorage.getItem("reed-discover.access") === ACCESS_HASH;
  if (remembered || supplied && await tokenHash(supplied) === ACCESS_HASH) {
    localStorage.setItem("reed-discover.access", ACCESS_HASH); document.body.classList.remove("locked");
    if (supplied) history.replaceState(null,"",`${location.pathname}${location.search}#today`);
    start(); return;
  }
  document.querySelector("#access-form").addEventListener("submit", async event => {
    event.preventDefault(); const valid = await tokenHash(document.querySelector("#access-token").value) === ACCESS_HASH;
    if (!valid) { document.querySelector("#access-error").hidden = false; return; }
    localStorage.setItem("reed-discover.access", ACCESS_HASH); document.body.classList.remove("locked"); location.hash = "today"; start();
  });
}

if (typeof document !== "undefined") authorize();
