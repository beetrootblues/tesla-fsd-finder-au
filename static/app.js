/* ==========================================================================
   Tesla FSD Finder Australia v1.2 - Application Logic
   Vanilla ES6+ - No framework dependencies
   ========================================================================== */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  allListings: [],
  filteredListings: [],
  stats: null,
  currentView: 'cards', // 'cards' | 'table' | 'map'
  map: null,
  mapMarkers: [],
  mapInitialized: false,
  compareIds: new Set(),     // IDs selected for comparison
  watchlist: new Set(),       // IDs saved to watchlist
  activeSource: 'all',       // source filter pill
  chartsInitialized: false,
  charts: {},
};

// ---------------------------------------------------------------------------
// DOM
// ---------------------------------------------------------------------------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const dom = {
  loadingState: $('#loadingState'),
  emptyState: $('#emptyState'),
  cardGrid: $('#cardGrid'),
  tableWrapper: $('#tableWrapper'),
  tableBody: $('#tableBody'),
  mapContainer: $('#mapContainer'),
  listingMap: $('#listingMap'),
  statTotal: $('#statTotal'),
  statConfirmed: $('#statConfirmed'),
  statHW4: $('#statHW4'),
  statDrops: $('#statDrops'),
  lastUpdated: $('#lastUpdated'),
  showingCount: $('#showingCount'),
  sourceBadges: $('#sourceBadges'),
  btnCards: $('#btnCards'),
  btnTable: $('#btnTable'),
  btnMap: $('#btnMap'),
  sidebar: $('#sidebar'),
  sidebarToggle: $('#sidebarToggle'),
  sidebarClose: $('#sidebarClose'),
  sidebarOverlay: $('#sidebarOverlay'),
  filterSource: $('#filterSource'),
  filterModel: $('#filterModel'),
  filterState: $('#filterState'),
  filterFSD: $('#filterFSD'),
  filterSellerType: $('#filterSellerType'),
  filterYearMin: $('#filterYearMin'),
  filterYearMax: $('#filterYearMax'),
  filterMinPrice: $('#filterMinPrice'),
  filterMaxPrice: $('#filterMaxPrice'),
  filterMaxKm: $('#filterMaxKm'),
  filterHasImages: $('#filterHasImages'),
  filterPriceDrops: $('#filterPriceDrops'),
  filterSort: $('#filterSort'),
  btnReset: $('#btnReset'),
  btnRefresh: $('#btnRefresh'),
  searchInput: $('#searchInput'),
  searchClear: $('#searchClear'),
  themeToggle: $('#themeToggle'),
  themeIcon: $('#themeIcon'),
  btnCompare: $('#btnCompare'),
  compareBadge: $('#compareBadge'),
  comparePanel: $('#comparePanel'),
  compareBody: $('#compareBody'),
  compareClose: $('#compareClose'),
  btnWatchlist: $('#btnWatchlist'),
  watchlistBadge: $('#watchlistBadge'),
  watchlistPanel: $('#watchlistPanel'),
  watchlistBody: $('#watchlistBody'),
  watchlistClose: $('#watchlistClose'),
  statsDashboard: $('#statsDashboard'),
  mobileNav: $('#mobileNav'),
  fsdBanner: $('#fsdBanner'),
  fsdCountdown: $('#fsdCountdown'),
  fsdBannerClose: $('#fsdBannerClose'),
};

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------
function formatPrice(price) {
  if (!price) return 'POA';
  return '$' + price.toLocaleString('en-AU');
}

function formatKm(km) {
  if (!km) return '--';
  return km.toLocaleString('en-AU') + ' km';
}

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = now - then;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return mins + 'm ago';
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + 'h ago';
  const days = Math.floor(hrs / 24);
  if (days < 7) return days + 'd ago';
  return then.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
}

function isNew(dateStr) {
  if (!dateStr) return false;
  const hrs = (Date.now() - new Date(dateStr).getTime()) / 3600000;
  return hrs < 24;
}

function fsdBadgeClass(status) {
  const map = { confirmed: 'badge-fsd-confirmed', likely: 'badge-fsd-likely', possible: 'badge-fsd-possible' };
  return map[status] || 'badge-fsd-none';
}

function fsdLabel(status) {
  const map = { confirmed: 'FSD Confirmed', likely: 'FSD Likely', possible: 'FSD Possible', none: 'Standard' };
  return map[status] || 'Standard';
}

function fsdIcon(status) {
  const map = { confirmed: 'bi-check-circle-fill', likely: 'bi-check-circle', possible: 'bi-question-circle' };
  return map[status] || 'bi-dash-circle';
}

function sourceClass(source) {
  return 'source-' + (source || 'unknown').toLowerCase().replace(/\s+/g, '-');
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// ---------------------------------------------------------------------------
// Source colours
// ---------------------------------------------------------------------------
const SOURCE_COLOURS = {
  carsales: '#ff5722',
  drive: '#2196f3',
  autotrader: '#4caf50',
  gumtree: '#ff9800',
  carsguide: '#9c27b0',
  pickles: '#607d8b',
  facebook: '#1877f2',
  unknown: '#757575',
};

function getSourceColour(source) {
  return SOURCE_COLOURS[(source || '').toLowerCase()] || SOURCE_COLOURS.unknown;
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------
async function fetchListings() {
  try {
    const resp = await fetch('/api/listings');
    const data = await resp.json();
    state.allListings = data.listings || [];
    return state.allListings;
  } catch (e) {
    console.error('Failed to fetch listings:', e);
    return [];
  }
}

async function fetchStats() {
  try {
    const resp = await fetch('/api/stats');
    state.stats = await resp.json();
    return state.stats;
  } catch (e) {
    console.error('Failed to fetch stats:', e);
    return null;
  }
}

async function triggerRefresh() {
  try {
    dom.btnRefresh.classList.add('spinning');
    const resp = await fetch('/api/refresh', { method: 'POST' });
    const data = await resp.json();
    if (data.status === 'started') {
      // Poll for completion
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        const h = await fetch('/api/health');
        const hd = await h.json();
        if (hd.scrape_status !== 'running' || attempts > 60) {
          clearInterval(poll);
          dom.btnRefresh.classList.remove('spinning');
          await init();
        }
      }, 5000);
    } else {
      dom.btnRefresh.classList.remove('spinning');
    }
  } catch (e) {
    dom.btnRefresh.classList.remove('spinning');
    console.error('Refresh failed:', e);
  }
}

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------
function getCheckedValues(container) {
  if (!container) return [];
  return [...container.querySelectorAll('input[type=checkbox]:checked')].map(cb => cb.value);
}

function getSelectedFilters() {
  return {
    models: getCheckedValues(dom.filterModel),
    states: getCheckedValues(dom.filterState),
    fsdStatuses: getCheckedValues(dom.filterFSD),
    sellerTypes: getCheckedValues(dom.filterSellerType),
    source: state.activeSource,
    yearMin: dom.filterYearMin?.value ? parseInt(dom.filterYearMin.value) : null,
    yearMax: dom.filterYearMax?.value ? parseInt(dom.filterYearMax.value) : null,
    minPrice: dom.filterMinPrice?.value ? parseInt(dom.filterMinPrice.value) : null,
    maxPrice: dom.filterMaxPrice?.value ? parseInt(dom.filterMaxPrice.value) : null,
    maxKm: dom.filterMaxKm?.value ? parseInt(dom.filterMaxKm.value) : null,
    hasImages: dom.filterHasImages?.checked || false,
    priceDrops: dom.filterPriceDrops?.checked || false,
    search: dom.searchInput?.value?.trim().toLowerCase() || '',
    sort: dom.filterSort?.value || 'newest',
  };
}

function applyFilters() {
  const f = getSelectedFilters();
  let results = [...state.allListings];

  if (f.models.length && f.models.length < 5)
    results = results.filter(r => f.models.includes(r.model));
  if (f.states.length && f.states.length < 8)
    results = results.filter(r => f.states.includes(r.state));
  if (f.fsdStatuses.length && f.fsdStatuses.length < 4)
    results = results.filter(r => f.fsdStatuses.includes(r.fsd_status));
  if (f.sellerTypes.length && f.sellerTypes.length < 3)
    results = results.filter(r => f.sellerTypes.map(s=>s.toLowerCase()).includes((r.seller_type||'').toLowerCase()));
  if (f.source !== 'all')
    results = results.filter(r => (r.source || '').toLowerCase() === f.source);
  if (f.yearMin) results = results.filter(r => (r.year || 0) >= f.yearMin);
  if (f.yearMax) results = results.filter(r => (r.year || 9999) <= f.yearMax);
  if (f.minPrice) results = results.filter(r => (r.price || 0) >= f.minPrice);
  if (f.maxPrice) results = results.filter(r => (r.price || 999999999) <= f.maxPrice);
  if (f.maxKm) results = results.filter(r => (r.odometer || 0) <= f.maxKm);
  if (f.hasImages) results = results.filter(r => r.image_url);
  if (f.priceDrops) results = results.filter(r => r.price_dropped);
  if (f.search) {
    const q = f.search;
    results = results.filter(r =>
      (r.title || '').toLowerCase().includes(q) ||
      (r.description || '').toLowerCase().includes(q) ||
      (r.location || '').toLowerCase().includes(q) ||
      (r.variant || '').toLowerCase().includes(q)
    );
  }

  results = sortListings(results, f.sort);
  state.filteredListings = results;
  render();
}

function sortListings(listings, sortKey) {
  const sorted = [...listings];
  switch (sortKey) {
    case 'price_asc': sorted.sort((a, b) => (a.price || 0) - (b.price || 0)); break;
    case 'price_desc': sorted.sort((a, b) => (b.price || 0) - (a.price || 0)); break;
    case 'km_asc': sorted.sort((a, b) => (a.odometer || 0) - (b.odometer || 0)); break;
    case 'year_desc': sorted.sort((a, b) => (b.year || 0) - (a.year || 0)); break;
    case 'drops': sorted.sort((a, b) => (b.price_drop_pct || 0) - (a.price_drop_pct || 0)); break;
    default: sorted.sort((a, b) => (b.found_at || '').localeCompare(a.found_at || ''));
  }
  return sorted;
}

function resetFilters() {
  $$('#filterModel input, #filterState input, #filterFSD input, #filterSellerType input')
    .forEach(cb => cb.checked = true);
  if (dom.filterYearMin) dom.filterYearMin.value = '';
  if (dom.filterYearMax) dom.filterYearMax.value = '';
  if (dom.filterMinPrice) dom.filterMinPrice.value = '';
  if (dom.filterMaxPrice) dom.filterMaxPrice.value = '';
  if (dom.filterMaxKm) dom.filterMaxKm.value = '';
  if (dom.filterHasImages) dom.filterHasImages.checked = false;
  if (dom.filterPriceDrops) dom.filterPriceDrops.checked = false;
  if (dom.filterSort) dom.filterSort.value = 'newest';
  if (dom.searchInput) dom.searchInput.value = '';
  if (dom.searchClear) dom.searchClear.classList.add('d-none');
  state.activeSource = 'all';
  $$('.source-pill').forEach(p => p.classList.toggle('active', p.dataset.source === 'all'));
  applyFilters();
}

// ---------------------------------------------------------------------------
// Card rendering
// ---------------------------------------------------------------------------
function renderCards(listings) {
  if (!dom.cardGrid) return;
  if (!listings.length) {
    dom.cardGrid.innerHTML = '';
    return;
  }

  dom.cardGrid.innerHTML = listings.map(l => {
    const isWatched = state.watchlist.has(l.id);
    const isCompared = state.compareIds.has(l.id);
    const priceDrop = l.price_dropped
      ? `<span class="price-drop"><i class="bi bi-arrow-down-short"></i>${l.price_drop_pct}%</span>`
      : '';
    const prevPrice = l.previous_price
      ? `<span class="prev-price">${formatPrice(l.previous_price)}</span>`
      : '';
    const newBadge = isNew(l.found_at)
      ? '<span class="badge-new">NEW</span>'
      : '';

    return `
      <article class="listing-card ${sourceClass(l.source)}" data-id="${l.id}">
        <div class="card-image-wrap">
          ${l.image_url
            ? `<img src="${escapeHtml(l.image_url)}" alt="${escapeHtml(l.title)}" class="card-image" loading="lazy" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 400 300%22><rect fill=%22%23333%22 width=%22400%22 height=%22300%22/><text x=%22200%22 y=%22160%22 fill=%22%23666%22 font-size=%2220%22 text-anchor=%22middle%22>No Image</text></svg>'" />`
            : `<div class="card-image-placeholder"><i class="bi bi-car-front"></i></div>`
          }
          <div class="card-image-overlay">
            ${newBadge}
            <span class="badge-source" style="background:${getSourceColour(l.source)}">${escapeHtml(l.source)}</span>
          </div>
          <button class="card-watch-btn ${isWatched ? 'watched' : ''}" data-action="watch" data-id="${l.id}" title="Add to watchlist">
            <i class="bi ${isWatched ? 'bi-heart-fill' : 'bi-heart'}"></i>
          </button>
        </div>
        <div class="card-body">
          <h3 class="card-title">${escapeHtml(l.title)}</h3>
          <div class="card-meta">
            <span>${l.year || '--'}</span>
            <span class="dot"></span>
            <span>${formatKm(l.odometer)}</span>
            <span class="dot"></span>
            <span>${escapeHtml(l.location || l.state || '--')}</span>
          </div>
          <div class="card-price-row">
            <span class="card-price">${formatPrice(l.price)}</span>
            ${prevPrice}
            ${priceDrop}
          </div>
          <div class="card-badges">
            <span class="badge-fsd ${fsdBadgeClass(l.fsd_status)}">
              <i class="bi ${fsdIcon(l.fsd_status)}"></i> ${fsdLabel(l.fsd_status)}
            </span>
            ${l.hw_version ? `<span class="badge-hw">${l.hw_version}</span>` : ''}
            ${l.seller_type ? `<span class="badge-seller badge-seller-${l.seller_type.toLowerCase()}">${l.seller_type}</span>` : ''}
          </div>
          <div class="card-actions">
            <a href="${escapeHtml(l.source_url)}" target="_blank" rel="noopener" class="btn-view">
              View on ${escapeHtml(l.source)} <i class="bi bi-box-arrow-up-right"></i>
            </a>
            <button class="btn-compare ${isCompared ? 'compared' : ''}" data-action="compare" data-id="${l.id}">
              <i class="bi bi-columns-gap"></i>
            </button>
          </div>
        </div>
        <div class="card-footer">
          <span class="card-time">${timeAgo(l.found_at)}</span>
        </div>
      </article>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Table rendering
// ---------------------------------------------------------------------------
function renderTable(listings) {
  if (!dom.tableBody) return;
  if (!listings.length) {
    dom.tableBody.innerHTML = '<tr><td colspan="9" class="text-center py-4 text-muted">No listings</td></tr>';
    return;
  }

  dom.tableBody.innerHTML = listings.map(l => {
    const drop = l.price_dropped
      ? `<span class="price-drop-sm"><i class="bi bi-arrow-down-short"></i>${l.price_drop_pct}%</span>`
      : '';
    return `
      <tr data-id="${l.id}">
        <td>
          <div class="table-title-cell">
            <strong>${escapeHtml(l.title)}</strong>
            <small class="text-muted">${escapeHtml(l.variant || '')}</small>
          </div>
        </td>
        <td>
          <span class="fw-semibold">${formatPrice(l.price)}</span>
          ${drop}
        </td>
        <td>${l.year || '--'}</td>
        <td>${formatKm(l.odometer)}</td>
        <td><span class="badge-fsd-sm ${fsdBadgeClass(l.fsd_status)}">${fsdLabel(l.fsd_status)}</span></td>
        <td><span class="badge-source-sm" style="background:${getSourceColour(l.source)}">${escapeHtml(l.source)}</span></td>
        <td>${l.state || '--'}</td>
        <td>${l.seller_type || '--'}</td>
        <td>
          <a href="${escapeHtml(l.source_url)}" target="_blank" rel="noopener" class="btn-view-sm">
            <i class="bi bi-box-arrow-up-right"></i>
          </a>
        </td>
      </tr>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Map
// ---------------------------------------------------------------------------
function initMap() {
  if (state.mapInitialized || !dom.listingMap) return;
  state.map = L.map('listingMap', { zoomControl: true }).setView([-25.5, 134], 4);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 18,
  }).addTo(state.map);
  state.mapInitialized = true;
}

function renderMap(listings) {
  if (!state.mapInitialized) initMap();
  if (!state.map) return;

  state.mapMarkers.forEach(m => m.remove());
  state.mapMarkers = [];

  const withCoords = listings.filter(l => l.lat && l.lng);
  if (!withCoords.length) return;

  const bounds = [];
  withCoords.forEach(l => {
    const colour = getSourceColour(l.source);
    const icon = L.divIcon({
      className: 'map-marker-custom',
      html: `<div style="background:${colour};width:12px;height:12px;border-radius:50%;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.3)"></div>`,
      iconSize: [12, 12],
    });

    const marker = L.marker([l.lat, l.lng], { icon }).addTo(state.map);
    marker.bindPopup(`
      <div class="map-popup">
        <strong>${escapeHtml(l.title)}</strong><br/>
        <span style="font-size:1.1em;font-weight:600">${formatPrice(l.price)}</span><br/>
        <span class="badge-fsd-sm ${fsdBadgeClass(l.fsd_status)}">${fsdLabel(l.fsd_status)}</span>
        <span class="badge-source-sm" style="background:${colour}">${escapeHtml(l.source)}</span><br/>
        <a href="${escapeHtml(l.source_url)}" target="_blank">View listing</a>
      </div>
    `);
    state.mapMarkers.push(marker);
    bounds.push([l.lat, l.lng]);
  });

  if (bounds.length) state.map.fitBounds(bounds, { padding: [30, 30] });
}

// ---------------------------------------------------------------------------
// View switching
// ---------------------------------------------------------------------------
function switchView(view) {
  state.currentView = view;

  dom.cardGrid?.classList.toggle('d-none', view !== 'cards');
  dom.tableWrapper?.classList.toggle('d-none', view !== 'table');
  dom.mapContainer?.classList.toggle('d-none', view !== 'map');
  dom.statsDashboard?.classList.add('d-none');
  dom.comparePanel?.classList.add('d-none');
  dom.watchlistPanel?.classList.add('d-none');

  dom.btnCards?.classList.toggle('active', view === 'cards');
  dom.btnTable?.classList.toggle('active', view === 'table');
  dom.btnMap?.classList.toggle('active', view === 'map');

  if (view === 'map') {
    initMap();
    setTimeout(() => {
      state.map?.invalidateSize();
      renderMap(state.filteredListings);
    }, 100);
  }
}

function showPanel(panel) {
  // Hide all views and panels first
  dom.cardGrid?.classList.add('d-none');
  dom.tableWrapper?.classList.add('d-none');
  dom.mapContainer?.classList.add('d-none');
  dom.statsDashboard?.classList.add('d-none');
  dom.comparePanel?.classList.add('d-none');
  dom.watchlistPanel?.classList.add('d-none');

  if (panel === 'stats') {
    dom.statsDashboard?.classList.remove('d-none');
    renderCharts();
  } else if (panel === 'compare') {
    dom.comparePanel?.classList.remove('d-none');
    renderCompare();
  } else if (panel === 'watchlist') {
    dom.watchlistPanel?.classList.remove('d-none');
    renderWatchlist();
  }
}

// ---------------------------------------------------------------------------
// Stats & Charts
// ---------------------------------------------------------------------------
function updateStats(stats) {
  if (!stats) return;
  dom.statTotal.textContent = stats.total_listings || 0;
  dom.statConfirmed.textContent = stats.fsd_total || 0;
  dom.statHW4.textContent = stats.hw4_count || 0;
  if (dom.statDrops) dom.statDrops.textContent = stats.price_drops || 0;
  if (dom.lastUpdated && stats.last_updated) {
    dom.lastUpdated.textContent = 'Updated ' + timeAgo(stats.last_updated);
  }

  // Render source badges in toolbar
  if (dom.sourceBadges && stats.by_source) {
    dom.sourceBadges.innerHTML = Object.entries(stats.by_source)
      .sort((a, b) => b[1] - a[1])
      .map(([src, count]) =>
        `<span class="toolbar-source-badge" style="background:${getSourceColour(src)}">${src} <strong>${count}</strong></span>`
      ).join('');
  }
}

function renderCharts() {
  if (!state.stats) return;
  const s = state.stats;

  // Destroy existing charts
  Object.values(state.charts).forEach(c => c.destroy());
  state.charts = {};

  const chartOpts = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 8, font: { size: 11 } } } },
  };

  // Sources doughnut
  const srcCanvas = $('#chartSources');
  if (srcCanvas && s.by_source) {
    const labels = Object.keys(s.by_source);
    state.charts.sources = new Chart(srcCanvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data: Object.values(s.by_source),
          backgroundColor: labels.map(l => getSourceColour(l)),
        }],
      },
      options: chartOpts,
    });
  }

  // Price distribution bar
  const priceCanvas = $('#chartPrices');
  if (priceCanvas && s.price_distribution) {
    const entries = Object.entries(s.price_distribution).sort((a, b) => a[0].localeCompare(b[0]));
    state.charts.prices = new Chart(priceCanvas, {
      type: 'bar',
      data: {
        labels: entries.map(e => e[0]),
        datasets: [{
          label: 'Listings',
          data: entries.map(e => e[1]),
          backgroundColor: '#e82127',
        }],
      },
      options: { ...chartOpts, plugins: { ...chartOpts.plugins, legend: { display: false } } },
    });
  }

  // Models doughnut
  const modelCanvas = $('#chartModels');
  if (modelCanvas && s.by_model) {
    state.charts.models = new Chart(modelCanvas, {
      type: 'doughnut',
      data: {
        labels: Object.keys(s.by_model),
        datasets: [{
          data: Object.values(s.by_model),
          backgroundColor: ['#e82127', '#ff6384', '#36a2eb', '#ffce56', '#4bc0c0'],
        }],
      },
      options: chartOpts,
    });
  }

  // States bar
  const stateCanvas = $('#chartStates');
  if (stateCanvas && s.by_state) {
    const entries = Object.entries(s.by_state).sort((a, b) => b[1] - a[1]);
    state.charts.states = new Chart(stateCanvas, {
      type: 'bar',
      data: {
        labels: entries.map(e => e[0]),
        datasets: [{
          label: 'Listings',
          data: entries.map(e => e[1]),
          backgroundColor: '#36a2eb',
        }],
      },
      options: { ...chartOpts, indexAxis: 'y', plugins: { ...chartOpts.plugins, legend: { display: false } } },
    });
  }

  state.chartsInitialized = true;
}

// ---------------------------------------------------------------------------
// Compare
// ---------------------------------------------------------------------------
function toggleCompare(id) {
  if (state.compareIds.has(id)) {
    state.compareIds.delete(id);
  } else if (state.compareIds.size < 3) {
    state.compareIds.add(id);
  }
  updateCompareUI();
}

function updateCompareUI() {
  const count = state.compareIds.size;
  dom.btnCompare.disabled = count < 2;
  dom.compareBadge.textContent = count;
  dom.compareBadge.classList.toggle('d-none', count === 0);

  $$('.btn-compare').forEach(btn => {
    btn.classList.toggle('compared', state.compareIds.has(btn.dataset.id));
  });
}

function renderCompare() {
  if (!dom.compareBody) return;
  const items = state.allListings.filter(l => state.compareIds.has(l.id));
  if (!items.length) {
    dom.compareBody.innerHTML = '<p class="text-muted p-3">Select 2-3 listings to compare.</p>';
    return;
  }

  const fields = [
    ['Price', l => formatPrice(l.price)],
    ['Year', l => l.year || '--'],
    ['Model', l => l.model || '--'],
    ['Kilometres', l => formatKm(l.odometer)],
    ['FSD Status', l => fsdLabel(l.fsd_status)],
    ['HW Version', l => l.hw_version || '--'],
    ['Location', l => l.location || l.state || '--'],
    ['Source', l => l.source || '--'],
    ['Seller', l => l.seller_type || '--'],
    ['Colour', l => l.colour || '--'],
  ];

  dom.compareBody.innerHTML = `
    <table class="compare-table">
      <thead><tr><th></th>${items.map(l => `<th>${escapeHtml(l.title)}</th>`).join('')}</tr></thead>
      <tbody>
        ${fields.map(([label, fn]) => `
          <tr><td class="compare-label">${label}</td>${items.map(l => `<td>${fn(l)}</td>`).join('')}</tr>
        `).join('')}
        <tr><td></td>${items.map(l => `
          <td><a href="${escapeHtml(l.source_url)}" target="_blank" class="btn-view-sm">View <i class="bi bi-box-arrow-up-right"></i></a></td>
        `).join('')}</tr>
      </tbody>
    </table>`;
}

// ---------------------------------------------------------------------------
// Watchlist (localStorage)
// ---------------------------------------------------------------------------
function loadWatchlist() {
  try {
    const saved = localStorage.getItem('fsd_watchlist');
    if (saved) state.watchlist = new Set(JSON.parse(saved));
  } catch (e) {}
  updateWatchlistUI();
}

function saveWatchlist() {
  localStorage.setItem('fsd_watchlist', JSON.stringify([...state.watchlist]));
}

function toggleWatch(id) {
  if (state.watchlist.has(id)) {
    state.watchlist.delete(id);
  } else {
    state.watchlist.add(id);
  }
  saveWatchlist();
  updateWatchlistUI();

  // Update heart icon in current view
  const btn = $(`.card-watch-btn[data-id="${id}"]`);
  if (btn) {
    btn.classList.toggle('watched', state.watchlist.has(id));
    const icon = btn.querySelector('i');
    if (icon) {
      icon.className = state.watchlist.has(id) ? 'bi bi-heart-fill' : 'bi bi-heart';
    }
  }
}

function updateWatchlistUI() {
  const count = state.watchlist.size;
  dom.watchlistBadge.textContent = count;
  dom.watchlistBadge.classList.toggle('d-none', count === 0);
}

function renderWatchlist() {
  if (!dom.watchlistBody) return;
  const items = state.allListings.filter(l => state.watchlist.has(l.id));
  if (!items.length) {
    dom.watchlistBody.innerHTML = '<p class="text-muted p-3">No saved listings yet. Tap the heart icon to save.</p>';
    return;
  }

  dom.watchlistBody.innerHTML = items.map(l => `
    <div class="watchlist-item" data-id="${l.id}">
      <div class="watchlist-info">
        <strong>${escapeHtml(l.title)}</strong>
        <span>${formatPrice(l.price)} &middot; ${l.year || '--'} &middot; ${formatKm(l.odometer)}</span>
        <span class="badge-source-sm" style="background:${getSourceColour(l.source)}">${escapeHtml(l.source)}</span>
      </div>
      <div class="watchlist-actions">
        <a href="${escapeHtml(l.source_url)}" target="_blank" class="btn-view-sm"><i class="bi bi-box-arrow-up-right"></i></a>
        <button class="btn-icon-sm" data-action="unwatch" data-id="${l.id}"><i class="bi bi-trash"></i></button>
      </div>
    </div>
  `).join('');
}

// ---------------------------------------------------------------------------
// Showing count
// ---------------------------------------------------------------------------
function updateShowingCount() {
  const total = state.allListings.length;
  const showing = state.filteredListings.length;
  if (dom.showingCount) {
    dom.showingCount.textContent = showing === total
      ? `${total} listings`
      : `${showing} of ${total} listings`;
  }
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------
function openSidebar() {
  dom.sidebar?.classList.add('open');
  dom.sidebarOverlay?.classList.add('visible');
  document.body.classList.add('sidebar-open');
}

function closeSidebar() {
  dom.sidebar?.classList.remove('open');
  dom.sidebarOverlay?.classList.remove('visible');
  document.body.classList.remove('sidebar-open');
}

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------
function initTheme() {
  const saved = localStorage.getItem('fsd_theme') || 'dark';
  document.documentElement.setAttribute('data-bs-theme', saved);
  updateThemeIcon(saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-bs-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-bs-theme', next);
  localStorage.setItem('fsd_theme', next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  if (dom.themeIcon) {
    dom.themeIcon.className = theme === 'dark' ? 'bi bi-moon-fill' : 'bi bi-sun-fill';
  }
}

// ---------------------------------------------------------------------------
// FSD Deadline countdown
// ---------------------------------------------------------------------------
function initFsdBanner() {
  const dismissed = localStorage.getItem('fsd_banner_dismissed');
  if (dismissed === 'true') {
    dom.fsdBanner?.classList.add('d-none');
    return;
  }

  function updateCountdown() {
    const deadline = new Date('2026-03-31T23:59:59+11:00'); // AEDT
    const now = new Date();
    const diff = deadline - now;

    if (diff <= 0) {
      if (dom.fsdCountdown) dom.fsdCountdown.textContent = 'Deadline passed!';
      return;
    }

    const days = Math.floor(diff / 86400000);
    const hours = Math.floor((diff % 86400000) / 3600000);
    if (dom.fsdCountdown) {
      dom.fsdCountdown.textContent = `${days}d ${hours}h remaining`;
    }
  }

  updateCountdown();
  setInterval(updateCountdown, 60000);

  dom.fsdBannerClose?.addEventListener('click', () => {
    dom.fsdBanner?.classList.add('d-none');
    localStorage.setItem('fsd_banner_dismissed', 'true');
  });
}

// ---------------------------------------------------------------------------
// Render orchestrator
// ---------------------------------------------------------------------------
function render() {
  const listings = state.filteredListings;

  if (!listings.length && state.allListings.length) {
    dom.emptyState?.classList.remove('d-none');
    dom.cardGrid?.classList.add('d-none');
    dom.tableWrapper?.classList.add('d-none');
  } else {
    dom.emptyState?.classList.add('d-none');
  }

  if (state.currentView === 'cards') {
    dom.cardGrid?.classList.remove('d-none');
    dom.tableWrapper?.classList.add('d-none');
    dom.mapContainer?.classList.add('d-none');
    renderCards(listings);
  } else if (state.currentView === 'table') {
    dom.tableWrapper?.classList.remove('d-none');
    dom.cardGrid?.classList.add('d-none');
    dom.mapContainer?.classList.add('d-none');
    renderTable(listings);
  } else if (state.currentView === 'map') {
    dom.mapContainer?.classList.remove('d-none');
    dom.cardGrid?.classList.add('d-none');
    dom.tableWrapper?.classList.add('d-none');
    renderMap(listings);
  }

  updateShowingCount();
  updateCompareUI();
}

function showLoading() {
  dom.loadingState?.classList.remove('d-none');
  dom.cardGrid?.classList.add('d-none');
  dom.tableWrapper?.classList.add('d-none');
  dom.emptyState?.classList.add('d-none');
}

function hideLoading() {
  dom.loadingState?.classList.add('d-none');
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
async function init() {
  showLoading();
  initTheme();
  initFsdBanner();
  loadWatchlist();

  const [listings, stats] = await Promise.all([fetchListings(), fetchStats()]);

  hideLoading();

  if (stats) updateStats(stats);
  applyFilters();
}

// ---------------------------------------------------------------------------
// Event binding
// ---------------------------------------------------------------------------
function bindEvents() {
  // Filter changes
  const filterEls = [
    dom.filterModel, dom.filterState, dom.filterFSD, dom.filterSellerType,
  ];
  filterEls.forEach(el => el?.addEventListener('change', applyFilters));

  [dom.filterYearMin, dom.filterYearMax, dom.filterMinPrice, dom.filterMaxPrice, dom.filterMaxKm]
    .forEach(el => el?.addEventListener('input', debounce(applyFilters, 400)));

  dom.filterHasImages?.addEventListener('change', applyFilters);
  dom.filterPriceDrops?.addEventListener('change', applyFilters);
  dom.filterSort?.addEventListener('change', applyFilters);

  // Source pills
  dom.filterSource?.addEventListener('click', (e) => {
    const pill = e.target.closest('.source-pill');
    if (!pill) return;
    state.activeSource = pill.dataset.source;
    $$('.source-pill').forEach(p => p.classList.toggle('active', p === pill));
    applyFilters();
  });

  // Search
  dom.searchInput?.addEventListener('input', debounce(() => {
    dom.searchClear?.classList.toggle('d-none', !dom.searchInput.value);
    applyFilters();
  }, 300));
  dom.searchClear?.addEventListener('click', () => {
    dom.searchInput.value = '';
    dom.searchClear.classList.add('d-none');
    applyFilters();
  });

  // View toggles
  dom.btnCards?.addEventListener('click', () => switchView('cards'));
  dom.btnTable?.addEventListener('click', () => switchView('table'));
  dom.btnMap?.addEventListener('click', () => switchView('map'));

  // Table sort headers
  $$('.th-sortable').forEach(th => {
    th.addEventListener('click', () => {
      if (dom.filterSort) dom.filterSort.value = th.dataset.sort;
      applyFilters();
    });
  });

  // Sidebar
  dom.sidebarToggle?.addEventListener('click', openSidebar);
  dom.sidebarClose?.addEventListener('click', closeSidebar);
  dom.sidebarOverlay?.addEventListener('click', closeSidebar);
  dom.btnReset?.addEventListener('click', resetFilters);

  // Theme
  dom.themeToggle?.addEventListener('click', toggleTheme);

  // Refresh
  dom.btnRefresh?.addEventListener('click', triggerRefresh);

  // Compare
  dom.btnCompare?.addEventListener('click', () => showPanel('compare'));
  dom.compareClose?.addEventListener('click', () => switchView(state.currentView));

  // Watchlist
  dom.btnWatchlist?.addEventListener('click', () => showPanel('watchlist'));
  dom.watchlistClose?.addEventListener('click', () => switchView(state.currentView));

  // Card click delegation (watch, compare)
  document.addEventListener('click', (e) => {
    const watchBtn = e.target.closest('[data-action="watch"]');
    if (watchBtn) {
      e.preventDefault();
      e.stopPropagation();
      toggleWatch(watchBtn.dataset.id);
      return;
    }
    const compareBtn = e.target.closest('[data-action="compare"]');
    if (compareBtn) {
      e.preventDefault();
      toggleCompare(compareBtn.dataset.id);
      return;
    }
    const unwatchBtn = e.target.closest('[data-action="unwatch"]');
    if (unwatchBtn) {
      e.preventDefault();
      toggleWatch(unwatchBtn.dataset.id);
      renderWatchlist();
      return;
    }
  });

  // Mobile nav
  dom.mobileNav?.addEventListener('click', (e) => {
    const item = e.target.closest('.mobile-nav-item');
    if (!item) return;
    const action = item.dataset.action;

    $$('.mobile-nav-item').forEach(i => i.classList.remove('active'));
    item.classList.add('active');

    if (action === 'listings') switchView('cards');
    else if (action === 'filters') openSidebar();
    else if (action === 'map') switchView('map');
    else if (action === 'watchlist') showPanel('watchlist');
    else if (action === 'stats') showPanel('stats');
  });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  bindEvents();
  init();
});
