/* Read-only strategy presentation. Source text remains in site-data.json unchanged. */
const MATERIAL_SYMBOLS = 'https://fonts.gstatic.com/s/i/short-term/release/materialsymbolsrounded';
const materialUrl = name => `${MATERIAL_SYMBOLS}/${name}/default/24px.svg`;
const iconForStrategy = strategy => {
  if (/地方债/.test(strategy)) return 'castle';
  if (/利率债|回转售/.test(strategy)) return 'diamond';
  if (/信用债/.test(strategy)) return 'text_increase';
  if (/REIT/.test(strategy)) return 'apartment';
  if (/转债/.test(strategy)) return 'swap_horiz';
  if (/权益|低波/.test(strategy)) return 'trending_up';
  if (/ABS/.test(strategy)) return 'corporate_fare';
  if (/海外/.test(strategy)) return 'directions_boat'; if (/宏观/.test(strategy)) return 'public';
  if (/衍生|指数/.test(strategy)) return 'graph_8';
  if (/黄金|商品/.test(strategy)) return 'account_balance';
  if (/基金|资金/.test(strategy)) return 'savings';
  if (/量化/.test(strategy)) return 'psychology';
  if (/多资产/.test(strategy)) return 'hub';
  return 'verified';
};

const app = { data: null, dateKey: null, activeEntry: null, lockedEntry: null, calendarMonth: '', archiveMonth: '', query: '', knownManagers: new Set(), previewTimer: null, els: {} };
const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#039;', '"': '&quot;' }[char]));
const icon = (name, classes = '') => `<img class="material-icon ${classes}" src="${materialUrl(name)}" alt="" />`;
const strategyIcon = strategy => `<span class="strategy-icon">${icon(iconForStrategy(strategy))}</span>`;
const docByKey = key => app.data.documents.find(item => item.dateKey === key) || app.data.documents[0];
const currentDocument = () => docByKey(app.dateKey);
const currentEntries = () => currentDocument()?.entries || [];
const contentCells = entry => entry.cells.filter(cell => !cell.sourceLabel?.includes('投资经理'));
const managerCell = entry => entry.cells.find(cell => cell.sourceLabel?.includes('投资经理'));
const dateMonth = key => key.slice(0, 4);
const monthLabel = key => `20${key.slice(0, 2)} 年 ${Number(key.slice(2, 4))} 月`;
const sectionNumbers = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十'];
const sectionTitle = (documentData, cell) => `${Number(documentData.date.slice(5, 7))}月${Number(documentData.date.slice(8, 10))}日策略指引（${sectionNumbers[cell.ordinal - 1] || cell.ordinal}）`;

function hydrateIcons(scope = document) { scope.querySelectorAll('[data-icon]').forEach(node => { node.src = materialUrl(node.dataset.icon); }); }
function highlight(value, query) {
  const safe = esc(value); const normalized = query.trim();
  if (!normalized) return safe;
  return safe.replace(new RegExp(`(${normalized.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'), '<mark>$1</mark>');
}
function contextualExcerpt(value, query, limit = 178) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  const index = text.toLocaleLowerCase().indexOf(query.trim().toLocaleLowerCase());
  if (index < 0 || text.length <= limit) return text;
  const start = Math.max(0, index - 58); const end = Math.min(text.length, index + query.length + 102);
  return `${start ? '…' : ''}${text.slice(start, end)}${end < text.length ? '…' : ''}`;
}
function collectKnownManagers(data) {
  const names = new Set();
  data.documents.forEach(documentData => documentData.entries.forEach(entry => managerCell(entry)?.text?.split(/[、，,\n]/).map(item => item.trim()).filter(item => /^[\u4e00-\u9fff]{2,5}$/.test(item)).forEach(item => names.add(item))));
  return names;
}
function splitAuthor(value, roster = new Set()) {
  const text = String(value ?? '');
  const match = text.match(/^\s*([^\n：:]{1,32})[：:]\s*(?:\r?\n)?/);
  if (!match || !roster.has(match[1].trim())) return { author: '', text };
  return { author: match[1].trim(), text: text.slice(match[0].length) };
}
function findHits(query) {
  const needle = query.trim().toLocaleLowerCase(); if (!needle) return [];
  const hits = [];
  app.data.documents.forEach(documentData => documentData.entries.forEach(entry => contentCells(entry).forEach(cell => {
    if (`${entry.strategy} ${sectionTitle(documentData, cell)} ${cell.text}`.toLocaleLowerCase().includes(needle)) hits.push({ documentData, entry, cell });
  })));
  return hits;
}
function monthKeys() { return [...new Set(app.data.documents.map(documentData => dateMonth(documentData.dateKey)))].sort().reverse(); }

function calendarMarkup(monthKey, selectedKey, id, extraClass = '') {
  const keys = monthKeys(); const year = 2000 + Number(monthKey.slice(0, 2)); const month = Number(monthKey.slice(2, 4));
  const firstWeekday = (new Date(year, month - 1, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month, 0).getDate();
  const documents = new Map(app.data.documents.filter(documentData => dateMonth(documentData.dateKey) === monthKey).map(documentData => [Number(documentData.dateKey.slice(4, 6)), documentData]));
  const cells = [];
  for (let empty = 0; empty < firstWeekday; empty += 1) cells.push('<span class="calendar-blank" aria-hidden="true"></span>');
  for (let day = 1; day <= daysInMonth; day += 1) {
    const documentData = documents.get(day);
    cells.push(documentData
      ? `<button class="calendar-day${documentData.dateKey === selectedKey ? ' is-selected' : ''}" data-date-key="${documentData.dateKey}" aria-label="${documentData.date}，${documentData.entries.length} 项策略"><span>${day}</span><i></i></button>`
      : `<span class="calendar-day is-disabled" aria-label="${year}年${month}月${day}日，无策略">${day}</span>`);
  }
  const monthOptions = keys.map(key => `<button type="button" class="custom-select-option${key === monthKey ? ' is-selected' : ''}" data-value="${key}">${monthLabel(key)}</button>`).join('');
  return `<div id="${id}" class="calendar-panel ${extraClass}"><div class="calendar-head"><div class="custom-select calendar-month-select"><button type="button" class="custom-select-trigger" aria-expanded="false"><span>${monthLabel(monthKey)}</span>${icon('expand_more')}</button><div class="custom-select-menu" hidden>${monthOptions}</div></div><span>${documents.size} 日已归档</span></div><div class="calendar-weekdays"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div><div class="calendar-days">${cells.join('')}</div></div>`;
}
function bindCalendar(container, onDate, onMonth) {
  container.querySelectorAll('[data-date-key]').forEach(button => button.addEventListener('click', () => onDate(button.dataset.dateKey)));
  bindCustomSelect(container.querySelector('.calendar-month-select'), onMonth);
}
function bindCustomSelect(root, onChange) {
  if (!root) return;
  const trigger = root.querySelector('.custom-select-trigger'); const menu = root.querySelector('.custom-select-menu');
  trigger?.addEventListener('click', event => { event.stopPropagation(); const open = root.classList.toggle('is-open'); trigger.setAttribute('aria-expanded', String(open)); menu.hidden = !open; });
  root.querySelectorAll('.custom-select-option').forEach(option => option.addEventListener('click', event => { event.stopPropagation(); root.querySelector('.custom-select-trigger span').textContent = option.textContent; root.querySelectorAll('.custom-select-option').forEach(item => item.classList.toggle('is-selected', item === option)); root.classList.remove('is-open'); trigger.setAttribute('aria-expanded', 'false'); menu.hidden = true; onChange(option.dataset.value); }));
}

function renderDailyCard() {
  const documentData = currentDocument();
  app.els.heroDate.textContent = `${documentData.date.replaceAll('.', ' / ')} · 当日完整底稿`;
  app.els.heroCoverage.textContent = currentEntries().length;
  app.els.dateCalendarLabel.textContent = documentData.date;
}
function renderDateCalendar() {
  app.els.dateCalendarPopover.innerHTML = calendarMarkup(app.calendarMonth, app.dateKey, 'date-calendar-panel', 'calendar-compact');
  bindCalendar(app.els.dateCalendarPopover, dateKey => { app.els.dateCalendarPopover.hidden = true; app.els.dateCalendarTrigger.setAttribute('aria-expanded', 'false'); selectDate(dateKey, false); }, month => { app.calendarMonth = month; renderDateCalendar(); });
}
function renderAtlas() {
  const entries = currentEntries();
  if (!entries.includes(app.activeEntry)) app.activeEntry = entries[0] || null;
  if (!entries.includes(app.lockedEntry)) app.lockedEntry = null;
  app.els.atlasGrid.innerHTML = entries.map((entry, index) => `<button class="atlas-tile${entry === app.activeEntry ? ' is-active' : ''}${entry === app.lockedEntry ? ' is-locked' : ''}" data-entry="${index}"><span class="tile-top"><span>${String(index + 1).padStart(2, '0')}</span></span>${strategyIcon(entry.strategy)}<span class="tile-lock" role="button" tabindex="0" aria-pressed="${entry === app.lockedEntry}" aria-label="${entry === app.lockedEntry ? '解锁观点预览' : '锁定观点预览'}">${icon(entry === app.lockedEntry ? 'lock' : 'lock_open')}</span><strong>${esc(entry.strategy)}</strong><small>${contentCells(entry).length} 段原始内容</small><span class="tile-jump-label">点击跳转到「${esc(entry.strategy)}」历史策略</span><span class="tile-arrow">${icon('arrow_forward')}</span></button>`).join('') || '<p class="empty-state">该日期暂无可展示的策略内容。</p>';
  app.els.atlasGrid.querySelectorAll('[data-entry]').forEach(tile => {
    const entry = entries[Number(tile.dataset.entry)];
    tile.addEventListener('mouseenter', () => { if (app.lockedEntry && app.lockedEntry !== entry) return; window.clearTimeout(app.previewTimer); app.previewTimer = window.setTimeout(() => previewEntry(entry), 220); });
    tile.addEventListener('mouseleave', () => window.clearTimeout(app.previewTimer));
    tile.addEventListener('focus', () => { if (!app.lockedEntry || app.lockedEntry === entry) previewEntry(entry); });
    const lockNode = tile.querySelector('.tile-lock');
    const toggleLock = event => {
      event.preventDefault();
      event.stopPropagation();
      app.lockedEntry = app.lockedEntry === entry ? null : entry;
      tile.classList.toggle('is-locked', app.lockedEntry === entry);
      lockNode.setAttribute('aria-pressed', String(app.lockedEntry === entry));
      lockNode.setAttribute('aria-label', app.lockedEntry === entry ? '解锁观点预览' : '锁定观点预览');
      const lockIcon = lockNode.querySelector('.material-icon');
      if (lockIcon) lockIcon.src = materialUrl(app.lockedEntry === entry ? 'lock' : 'lock_open');
    };
    lockNode?.addEventListener('click', toggleLock);
    lockNode?.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') toggleLock(event); });
    tile.addEventListener('click', () => { window.location.href = `./archive.html?mode=strategy&strategy=${encodeURIComponent(entry.strategy)}&date=${encodeURIComponent(currentDocument().dateKey)}`; });
  });
  renderReaderDock(app.activeEntry);
  animateAtlas();
}
function previewEntry(entry) {
  app.activeEntry = entry;
  app.els.atlasGrid.querySelectorAll('.atlas-tile').forEach(tile => tile.classList.toggle('is-active', currentEntries()[Number(tile.dataset.entry)] === entry));
  renderReaderDock(entry);
}
function strategySections(documentData, entry) {
  const manager = managerCell(entry)?.text?.trim();
  return contentCells(entry).map(cell => {
    const byline = splitAuthor(cell.text, app.knownManagers);
    return `<section>${manager ? '' : `<h4>${esc(sectionTitle(documentData, cell))}</h4>`}${byline.author ? `<div class="cell-author">${esc(byline.author)}</div>` : ''}<p>${esc(byline.text)}</p><span class="cell-quote" aria-hidden="true">“</span></section>`;
  }).join('');
}
function renderReaderDock(entry) {
  if (!entry) { app.els.readerDock.innerHTML = '<p class="reader-empty">选择一项策略查看原文。</p>'; return; }
  const documentData = currentDocument();
  const managers = managerCell(entry)?.text?.trim();
  app.els.readerDock.innerHTML = `<div class="reader-dock-head"><span>${esc(documentData.date)}</span><span>原始观点</span></div><div class="reader-strategy-head">${strategyIcon(entry.strategy)}<div><h3>${esc(entry.strategy)}</h3>${managers ? `<p>投资经理 · ${esc(managers)}</p>` : ''}</div></div><div class="reader-dock-body">${strategySections(documentData, entry)}</div>`;
}
function renderArchive() {
  const docs = app.data.documents;
  app.els.archiveCount.textContent = docs.length;
  app.els.footerMeta.textContent = `${docs.length} 份原始日表 · ${app.data.strategies.length} 类策略`;
  app.els.archiveMini.innerHTML = docs.slice(0, 4).map(documentData => `<button data-date-key="${documentData.dateKey}">${documentData.date.slice(5)}<small>${documentData.entries.length}</small></button>`).join('');
  app.els.archiveMini.querySelectorAll('[data-date-key]').forEach(button => button.addEventListener('click', () => selectDate(button.dataset.dateKey, true)));
  app.els.archiveCalendar.innerHTML = calendarMarkup(app.archiveMonth, app.dateKey, 'archive-calendar-panel', 'archive-calendar-panel');
  bindCalendar(app.els.archiveCalendar, dateKey => selectDate(dateKey, true), month => { app.archiveMonth = month; renderArchive(); });
}
function selectDate(dateKey, shouldScroll) {
  app.dateKey = dateKey; app.calendarMonth = dateMonth(dateKey); app.archiveMonth = dateMonth(dateKey);
  renderDailyCard(); renderDateCalendar(); renderAtlas(); renderArchive();
  if (shouldScroll) document.querySelector('#atlas').getBoundingClientRect() && window.scrollTo({ top: document.querySelector('#atlas').offsetTop - 82, behavior: 'smooth' });
}

function renderSuggestions(query) {
  const hits = findHits(query).slice(0, 6); const box = app.els.suggestions;
  if (!query.trim()) { box.hidden = true; box.innerHTML = ''; return; }
  box.innerHTML = hits.map((hit, index) => `<button data-suggestion="${index}"><span>${highlight(`${hit.documentData.date} · ${hit.entry.strategy}`, query)}</span><strong>${highlight(sectionTitle(hit.documentData, hit.cell), query)}</strong><p>${highlight(contextualExcerpt(hit.cell.text, query), query)}</p></button>`).join('') || '<p>没有匹配的原文</p>';
  box.hidden = false;
  box.querySelectorAll('[data-suggestion]').forEach(button => button.addEventListener('click', () => openSearchPage(query, hits[Number(button.dataset.suggestion)])));
}
function openSearchPage(query, selectedHit = null) {
  app.query = query.trim(); if (!app.query) return;
  const hits = findHits(app.query); app.els.home.hidden = true; app.els.searchPage.hidden = false; app.els.suggestions.hidden = true;
  app.els.searchTitle.textContent = `“${app.query}”`;
  app.els.searchSummary.textContent = `找到 ${hits.length} 条原文匹配`;
  app.els.searchResults.innerHTML = hits.slice(0, 120).map((hit, index) => `<button class="search-result${hit === selectedHit ? ' is-selected' : ''}" data-result="${index}"><span>${highlight(`${hit.documentData.date} · ${hit.entry.strategy}`, app.query)}</span><strong>${highlight(sectionTitle(hit.documentData, hit.cell), app.query)}</strong><p>${highlight(contextualExcerpt(hit.cell.text, app.query), app.query)}</p></button>`).join('') || '<p class="empty-state">没有匹配的原文。可尝试更短的关键词。</p>';
  app.els.searchResults.querySelectorAll('[data-result]').forEach(button => button.addEventListener('click', () => { const hit = hits[Number(button.dataset.result)]; app.activeEntry = hit.entry; closeSearchPage(); selectDate(hit.documentData.dateKey, true); }));
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function closeSearchPage() { app.els.searchPage.hidden = true; app.els.home.hidden = false; app.els.navInput.value = ''; app.query = ''; }
function animateAtlas() { if (window.gsap) gsap.fromTo(app.els.atlasGrid.querySelectorAll('.atlas-tile'), { y: 18, opacity: 0 }, { y: 0, opacity: 1, stagger: .028, duration: .58, ease: 'power3.out', clearProps: 'transform' }); }
function setupMotion() { if (!window.gsap || !window.ScrollTrigger) return; gsap.registerPlugin(ScrollTrigger); gsap.from('.daily-layout > *', { y: 24, opacity: 0, duration: .86, stagger: .11, ease: 'power4.out' }); gsap.from('.archive-section > *', { scrollTrigger: { trigger: '#archive', start: 'top 80%' }, y: 30, opacity: 0, duration: .72, stagger: .1, ease: 'power3.out' }); }

async function start() {
  app.els = { home: document.querySelector('#home-view'), heroDate: document.querySelector('#hero-date'), heroCoverage: document.querySelector('#hero-coverage'), atlasGrid: document.querySelector('#atlas-grid'), readerDock: document.querySelector('#reader-dock'), archiveCount: document.querySelector('#archive-count'), archiveMini: document.querySelector('#archive-mini'), archiveCalendar: document.querySelector('#archive-calendar'), footerMeta: document.querySelector('#footer-meta'), navInput: document.querySelector('#nav-search-input'), navOpen: document.querySelector('#nav-search-open'), navSubmit: document.querySelector('#nav-search-submit'), suggestions: document.querySelector('#search-suggestions'), searchPage: document.querySelector('#search-page'), searchTitle: document.querySelector('#search-page-title'), searchSummary: document.querySelector('#search-page-summary'), searchResults: document.querySelector('#search-page-results'), dateCalendarTrigger: document.querySelector('#date-calendar-trigger'), dateCalendarLabel: document.querySelector('#date-calendar-label'), dateCalendarPopover: document.querySelector('#date-calendar-popover') };
  hydrateIcons();
  try {
    const response = await fetch('./site-data.json'); if (!response.ok) throw new Error('未能读取展示数据');
    app.data = await response.json(); app.knownManagers = collectKnownManagers(app.data); app.dateKey = app.data.documents[0]?.dateKey; app.calendarMonth = dateMonth(app.dateKey); app.archiveMonth = app.calendarMonth;
    renderDailyCard(); renderDateCalendar(); renderAtlas(); renderArchive(); setupMotion();
    const initialQuery = new URLSearchParams(window.location.search).get('q');
    if (initialQuery) { app.els.navInput.value = initialQuery; openSearchPage(initialQuery); }
  } catch (error) { app.els.atlasGrid.innerHTML = `<p class="empty-state">展示数据暂不可用：${esc(error.message)}</p>`; }
  app.els.dateCalendarTrigger.addEventListener('click', () => { const open = app.els.dateCalendarPopover.hidden; app.els.dateCalendarPopover.hidden = !open; app.els.dateCalendarTrigger.setAttribute('aria-expanded', String(open)); });
  app.els.navInput.addEventListener('input', event => renderSuggestions(event.target.value));
  app.els.navOpen.addEventListener('click', () => app.els.navInput.focus());
  app.els.navInput.addEventListener('keydown', event => { if (event.key === 'Enter') openSearchPage(event.target.value); if (event.key === 'Escape') app.els.suggestions.hidden = true; });
  app.els.navSubmit.addEventListener('click', () => openSearchPage(app.els.navInput.value));
  document.querySelectorAll('[data-close-search]').forEach(button => button.addEventListener('click', closeSearchPage));
  document.addEventListener('click', event => { if (!event.target.closest('.nav-search')) app.els.suggestions.hidden = true; if (!event.target.closest('.calendar-picker')) { app.els.dateCalendarPopover.hidden = true; app.els.dateCalendarTrigger.setAttribute('aria-expanded', 'false'); } document.querySelectorAll('.custom-select.is-open').forEach(root => { if (!root.contains(event.target)) { root.classList.remove('is-open'); root.querySelector('.custom-select-menu').hidden = true; root.querySelector('.custom-select-trigger').setAttribute('aria-expanded', 'false'); } }); });
}
start();
