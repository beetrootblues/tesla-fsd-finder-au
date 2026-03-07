/* ==========================================================================
   Tesla FSD Finder Australia - Application Logic
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
  currentView: 'cards', // 'cards' | 'map'
  map: null,
  mapMarkers: [],
  mapInitialized: false,
};

// ---------------------------------------------------------------------------
// DOM References
// ---------------------------------------------------------------------------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const dom = {
  // Views
  loadingState: $('#loadingState'),
  emptyState: $('#emptyState'),
  cardGrid: $('#cardGrid'),
  mapContainer: $('#mapContainer'),
  listingMap: $('#listingMap'),

  // Header
  statTotal: $('#statTotal'),
  statConfirmed: $('#statConfirmed'),
  statHW4: $('#statHW4'),
  lastUpdated: $('#lastUpdated'),
  showingCount: $('#showingCount'),

  // View toggle
  btnCards: $('#btnCards'),
  btnMap: $('#btnMap'),

  // Sidebar
  sidebar: $('#sidebar'),
  sidebarToggle: $('#sidebarToggle'),
  sidebarClose: $('#sidebarClose'),
  sidebarOverlay: $('#sidebarOverlay'),

  // Filters
  filterModel: $('#filterModel'),
  filterState: $('#filterState'),
  filterFSD: $('#filterFSD'),
  filterMinPrice: $('#filterMinPrice'),
  filterMaxPrice: $('#filterMaxPrice'),
  filterMaxKm: $('#filterMaxKm'),
  filterSort: $('#filterSort'),

  // Buttons
  btnApply: $('#btnApply'),
  btnReset: $('#btnReset'),
  btnResetEmpty: $('#btnResetEmpty'),

  // Footer
  appFooter: $('#appFooter'),
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatPrice(price) {
  if (!price && price !== 0) return 'POA';
  return '$' + Number(price).toLocaleString('en-AU');
}

function formatKm(km) {
  if (!km && km !== 0) return 'N/A';
  return Number(km).toLocaleString('en-AU') + ' km';
}

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return diffMin + 'm ago';
  if (diffHr < 24) return diffHr + 'h ago';
  if (diffDay < 7) return diffDay + 'd ago';
  if (diffDay < 30) return Math.floor(diffDay / 7) + 'w ago';
  return date.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
}

function isNew(dateStr) {
  if (!dateStr) return false;
  const now = new Date();
  const date = new Date(dateStr);
  return (now - date) < 86400000; // 24 hours
}

function fsdBadgeClass(status) {
  switch (status) {
    case 'confirmed': return 'badge-confirmed';
    case 'likely': return 'badge-likely';
    case 'possible': return 'badge-possible';
    default: return 'badge-possible';
  }
}

function fsdLabel(status) {
  switch (status) {
    case 'confirmed': return 'FSD Confirmed';
    case 'likely': return 'FSD Likely';
    case 'possible': return 'FSD Possible';
    default: return 'FSD Unknown';
  }
}

function fsdIcon(status) {
  switch (status) {
    case 'confirmed': return 'bi-shield-fill-check';
    case 'likely': return 'bi-shield-fill-exclamation';
    case 'possible': return 'bi-shield-fill';
    default: return 'bi-shield';
  }
}

function sourceClass(source) {
  if (!source) return '';
  const s = source.toLowerCase();
  if (s.includes('drive')) return 'drive';
  if (s.includes('gumtree')) return 'gumtree';
  if (s.includes('autotrader') || s.includes('auto trader')) return 'autotrader';
  return '';
}

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

async function fetchListings() {
  try {
    const res = await fetch('/api/listings');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.listings || [];
  } catch (err) {
    console.error('Failed to fetch listings:', err);
    return [];
  }
}

async function fetchStats() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('Failed to fetch stats:', err);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Filtering (client-side)
// ---------------------------------------------------------------------------

function getCheckedValues(container) {
  return $$(
    `#${container.id} input[type="checkbox"]:checked`
  ).map((cb) => cb.value);
}

function getSelectedFilters() {
  const models = getCheckedValues(dom.filterModel);
  const states = getCheckedValues(dom.filterState);
  const fsdStatuses = getCheckedValues(dom.filterFSD);
  const minPrice = dom.filterMinPrice.value ? parseInt(dom.filterMinPrice.value) : null;
  const maxPrice = dom.filterMaxPrice.value ? parseInt(dom.filterMaxPrice.value) : null;
  const maxKm = dom.filterMaxKm.value ? parseInt(dom.filterMaxKm.value) : null;
  const sort = dom.filterSort.value;

  return { models, states, fsdStatuses, minPrice, maxPrice, maxKm, sort };
}

function applyFilters() {
  const { models, states, fsdStatuses, minPrice, maxPrice, maxKm, sort } = getSelectedFilters();

  let results = state.allListings.filter((listing) => {
    // Model filter
    if (models.length > 0 && !models.includes(listing.model)) return false;

    // State filter
    if (states.length > 0 && !states.includes(listing.state)) return false;

    // FSD Status filter
    if (fsdStatuses.length > 0 && !fsdStatuses.includes(listing.fsd_status)) return false;

    // Price filter
    const price = listing.price || 0;
    if (minPrice !== null && price < minPrice) return false;
    if (maxPrice !== null && price > maxPrice) return false;

    // KM filter
    const km = listing.odometer || 0;
    if (maxKm !== null && km > maxKm) return false;

    return true;
  });

  // Sort
  results = sortListings(results, sort);

  state.filteredListings = results;
  render();
}

function sortListings(listings, sortKey) {
  const sorted = [...listings];
  switch (sortKey) {
    case 'price_asc':
      sorted.sort((a, b) => (a.price || 0) - (b.price || 0));
      break;
    case 'price_desc':
      sorted.sort((a, b) => (b.price || 0) - (a.price || 0));
      break;
    case 'km_asc':
      sorted.sort((a, b) => (a.odometer || 0) - (b.odometer || 0));
      break;
    case 'year_desc':
      sorted.sort((a, b) => (b.year || 0) - (a.year || 0));
      break;
    case 'newest':
    default:
      sorted.sort((a, b) => {
        const da = a.found_at ? new Date(a.found_at) : new Date(0);
        const db = b.found_at ? new Date(b.found_at) : new Date(0);
        return db - da;
      });
  }
  return sorted;
}

function resetFilters() {
  // Check all model checkboxes
  $$('#filterModel input[type="checkbox"]').forEach((cb) => (cb.checked = true));
  $$('#filterState input[type="checkbox"]').forEach((cb) => (cb.checked = true));
  $$('#filterFSD input[type="checkbox"]').forEach((cb) => (cb.checked = true));

  dom.filterMinPrice.value = '';
  dom.filterMaxPrice.value = '';
  dom.filterMaxKm.value = '';
  dom.filterSort.value = 'newest';

  applyFilters();
}

// ---------------------------------------------------------------------------
// Rendering - Cards
// ---------------------------------------------------------------------------

function renderCards(listings) {
  if (listings.length === 0) {
    dom.cardGrid.classList.add('hidden');
    dom.emptyState.classList.remove('hidden');
    return;
  }

  dom.emptyState.classList.add('hidden');
  dom.cardGrid.classList.remove('hidden');

  const html = listings.map((listing, idx) => {
    const newBadge = isNew(listing.found_at)
      ? `<span class="badge-new">NEW</span>`
      : '';

    const hwBadge = listing.hw_version
      ? `<span class="badge-hw">${escapeHtml(listing.hw_version)}</span>`
      : '';

    const imageContent = listing.image_url
      ? `<img src="${escapeHtml(listing.image_url)}" alt="${escapeHtml(listing.title)}" loading="lazy" />`
      : `<div class="card-placeholder">
           <i class="bi bi-car-front"></i>
           <span>No image</span>
         </div>`;

    const srcClass = sourceClass(listing.source);

    return `
      <article class="listing-card card-enter" style="animation-delay: ${Math.min(idx * 40, 480)}ms">
        <div class="card-image">
          ${imageContent}
          <div class="card-badges">
            <span class="badge-fsd ${fsdBadgeClass(listing.fsd_status)}">
              <i class="bi ${fsdIcon(listing.fsd_status)}"></i>
              ${fsdLabel(listing.fsd_status)}
            </span>
            ${hwBadge}
          </div>
          <div class="card-badges-left">
            ${newBadge}
          </div>
        </div>
        <div class="card-body">
          <h3 class="card-title">${escapeHtml(listing.title)}</h3>
          <div class="card-price">
            ${formatPrice(listing.price)}
            <span class="currency-label">AUD</span>
          </div>
          <div class="card-meta">
            <div class="card-meta-row">
              <i class="bi bi-speedometer2"></i>
              ${formatKm(listing.odometer)}
            </div>
            <div class="card-meta-row">
              <i class="bi bi-geo-alt"></i>
              ${escapeHtml(listing.location || '')}${listing.state ? ', ' + escapeHtml(listing.state) : ''}
            </div>
          </div>
        </div>
        <div class="card-footer">
          <span class="source-badge ${srcClass}">${escapeHtml(listing.source || 'Unknown')}</span>
          <span class="card-time">${timeAgo(listing.found_at)}</span>
          <a class="btn-view" href="${escapeHtml(listing.source_url || '#')}" target="_blank" rel="noopener noreferrer">
            View <i class="bi bi-box-arrow-up-right"></i>
          </a>
        </div>
      </article>
    `;
  }).join('');

  dom.cardGrid.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Rendering - Map
// ---------------------------------------------------------------------------

function initMap() {
  if (state.mapInitialized) return;

  state.map = L.map('listingMap', {
    center: [-25.2744, 133.7751],
    zoom: 4,
    zoomControl: true,
    attributionControl: true,
  });

  // CARTO dark basemap
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(state.map);

  state.mapInitialized = true;
}

function renderMap(listings) {
  initMap();

  // Clear existing markers
  state.mapMarkers.forEach((m) => m.remove());
  state.mapMarkers = [];

  const markerGroup = [];

  listings.forEach((listing) => {
    const lat = listing.lat;
    const lng = listing.lng;
    if (!lat || !lng) return;

    // Red circle marker
    const marker = L.circleMarker([lat, lng], {
      radius: 8,
      fillColor: '#e82127',
      fillOpacity: 0.85,
      color: '#ff4449',
      weight: 2,
      opacity: 0.6,
    });

    // Determine badge color for popup
    let badgeColor, badgeBg;
    switch (listing.fsd_status) {
      case 'confirmed':
        badgeColor = '#22c55e';
        badgeBg = 'rgba(34,197,94,0.15)';
        break;
      case 'likely':
        badgeColor = '#eab308';
        badgeBg = 'rgba(234,179,8,0.15)';
        break;
      default:
        badgeColor = '#f97316';
        badgeBg = 'rgba(249,115,22,0.15)';
    }

    const popupHtml = `
      <div>
        <span class="popup-badge" style="color:${badgeColor};background:${badgeBg}">${fsdLabel(listing.fsd_status)}</span>
        <div class="popup-title">${escapeHtml(listing.title)}</div>
        <div class="popup-price">${formatPrice(listing.price)} <span style="font-size:0.7rem;color:#aaa">AUD</span></div>
        <div class="popup-meta">${formatKm(listing.odometer)} &bull; ${escapeHtml(listing.location || '')}, ${escapeHtml(listing.state || '')}</div>
        <a class="popup-link" href="${escapeHtml(listing.source_url || '#')}" target="_blank" rel="noopener">
          View on ${escapeHtml(listing.source || 'Source')} <i class="bi bi-box-arrow-up-right"></i>
        </a>
      </div>
    `;

    marker.bindPopup(popupHtml, { maxWidth: 280, minWidth: 200 });
    marker.addTo(state.map);
    state.mapMarkers.push(marker);
    markerGroup.push(marker);
  });

  // Fit bounds if we have markers
  if (markerGroup.length > 0) {
    const group = L.featureGroup(markerGroup);
    state.map.fitBounds(group.getBounds().pad(0.15), { maxZoom: 12 });
  }
}

// ---------------------------------------------------------------------------
// View Switching
// ---------------------------------------------------------------------------

function switchView(view) {
  state.currentView = view;

  // Toggle buttons
  dom.btnCards.classList.toggle('active', view === 'cards');
  dom.btnMap.classList.toggle('active', view === 'map');
  dom.btnCards.setAttribute('aria-selected', view === 'cards');
  dom.btnMap.setAttribute('aria-selected', view === 'map');

  // Toggle content
  dom.cardGrid.classList.toggle('hidden', view !== 'cards');
  dom.mapContainer.classList.toggle('hidden', view !== 'map');

  // Hide empty state in map view
  if (view === 'map') {
    dom.emptyState.classList.add('hidden');
    renderMap(state.filteredListings);
    // Leaflet needs a size recalc after unhide
    setTimeout(() => {
      if (state.map) state.map.invalidateSize();
    }, 100);
  } else {
    renderCards(state.filteredListings);
  }

  // Hide/show footer in map view
  if (dom.appFooter) {
    dom.appFooter.style.display = view === 'map' ? 'none' : '';
  }
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

function updateStats(stats) {
  if (!stats) return;

  dom.statTotal.textContent = stats.total_listings || 0;
  dom.statConfirmed.textContent = stats.confirmed || 0;
  dom.statHW4.textContent = stats.hw4_count || 0;

  if (stats.last_updated) {
    const ago = timeAgo(stats.last_updated);
    dom.lastUpdated.innerHTML = `<i class="bi bi-clock"></i> Last scan: ${ago}`;
  }
}

function updateShowingCount() {
  const total = state.allListings.length;
  const showing = state.filteredListings.length;
  if (showing === total) {
    dom.showingCount.textContent = `Showing all ${total} listings`;
  } else {
    dom.showingCount.textContent = `Showing ${showing} of ${total} listings`;
  }
}

// ---------------------------------------------------------------------------
// Sidebar (mobile)
// ---------------------------------------------------------------------------

function openSidebar() {
  dom.sidebar.classList.add('open');
  dom.sidebarOverlay.classList.add('active');
  document.body.style.overflow = 'hidden';
}

function closeSidebar() {
  dom.sidebar.classList.remove('open');
  dom.sidebarOverlay.classList.remove('active');
  document.body.style.overflow = '';
}

// ---------------------------------------------------------------------------
// Render Orchestrator
// ---------------------------------------------------------------------------

function render() {
  updateShowingCount();

  if (state.currentView === 'cards') {
    renderCards(state.filteredListings);
  } else {
    renderMap(state.filteredListings);
  }
}

function showLoading() {
  dom.loadingState.classList.remove('hidden');
  dom.cardGrid.classList.add('hidden');
  dom.mapContainer.classList.add('hidden');
  dom.emptyState.classList.add('hidden');
}

function hideLoading() {
  dom.loadingState.classList.add('hidden');
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  showLoading();

  // Fetch data in parallel
  const [listings, stats] = await Promise.all([fetchListings(), fetchStats()]);

  state.allListings = listings;
  state.stats = stats;

  // Update header stats
  updateStats(stats);

  // Apply initial filters (all checked = show all)
  applyFilters();

  // Hide loading, show content
  hideLoading();
  switchView('cards');
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------

function bindEvents() {
  // View toggle
  dom.btnCards.addEventListener('click', () => switchView('cards'));
  dom.btnMap.addEventListener('click', () => switchView('map'));

  // Filter apply
  dom.btnApply.addEventListener('click', () => {
    applyFilters();
    closeSidebar();
  });

  // Reset buttons
  dom.btnReset.addEventListener('click', resetFilters);
  dom.btnResetEmpty.addEventListener('click', resetFilters);

  // Sidebar mobile
  dom.sidebarToggle.addEventListener('click', openSidebar);
  dom.sidebarClose.addEventListener('click', closeSidebar);
  dom.sidebarOverlay.addEventListener('click', closeSidebar);

  // Auto-apply on sort change (desktop convenience)
  dom.filterSort.addEventListener('change', debounce(applyFilters, 200));

  // Keyboard: Escape closes sidebar
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSidebar();
  });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  bindEvents();
  init();
});
