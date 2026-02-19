const { useState, useEffect, useRef, useCallback } = React;

// ─── API helpers ─────────────────────────────────────────────────
const api = {
  get: (path) => fetch(`/api${path}`).then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail || 'Error'); })),
  post: (path, body) => fetch(`/api${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()),
  patch: (path, body) => fetch(`/api${path}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail || 'Error'); })),
  delete: (path) => fetch(`/api${path}`, { method: 'DELETE' }).then(r => r.json()),
};

// ─── Marker helpers ───────────────────────────────────────────────
function markerColor(status) {
  if (status === 'pickup_ready') return '#e17055';
  if (status === 'delivered') return '#00b894';
  return '#b2bec3';
}

function createPackageIcon(source, status, num) {
  const color = markerColor(status);
  const emoji = source === 'inpost' ? '📦' : '🛒';
  const inner = num != null
    ? `<div class="map-marker-num">${num}</div>`
    : `<div class="map-marker-inner">${emoji}</div>`;
  return L.divIcon({
    html: `<div class="map-marker" style="background:${color}">${inner}</div>`,
    className: '',
    iconSize: [36, 36],
    iconAnchor: [18, 36],
    popupAnchor: [0, -38],
  });
}

function createUserIcon() {
  return L.divIcon({
    html: `<div class="user-marker">📍</div>`,
    className: '',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function popupHtml(pkg, routeNum) {
  const numBadge = routeNum != null ? `<span style="background:#6c5ce7;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.7rem;font-weight:700;">Przystanek ${routeNum}</span><br/>` : '';
  return `
    <div class="popup-content">
      ${numBadge}
      <h4>${pkg.source === 'inpost' ? '📦 InPost Paczkomat' : '🛒 Amazon'}</h4>
      ${pkg.locker_id ? `<p><strong>Locker:</strong> ${pkg.locker_id}</p>` : ''}
      ${pkg.pickup_code ? `<code class="popup-pickup-code">${pkg.pickup_code}</code>` : ''}
      ${pkg.address_display ? `<p>📍 ${pkg.address_display}</p>` : ''}
      <p class="popup-order" style="font-size:0.7rem;color:#b2bec3;">${pkg.tracking_number}</p>
    </div>
  `;
}

// ─── Toast ────────────────────────────────────────────────────────
function Toast({ toasts }) {
  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast toast-${t.type}`}>{t.msg}</div>
      ))}
    </div>
  );
}

// ─── StatusBadge ─────────────────────────────────────────────────
const STATUS_LABELS = {
  pickup_ready: 'Gotowa do odbioru',
  delivered: 'Dostarczona',
  in_transit: 'W drodze',
  expired: 'Wygasła',
};

function StatusBadge({ status }) {
  return <span className={`status-badge status-${status}`}>{STATUS_LABELS[status] || status}</span>;
}

// ─── PackageCard ──────────────────────────────────────────────────
function PackageCard({ pkg, selected, onSelect, onDelete, routeNum }) {
  const [codeVisible, setCodeVisible] = useState(false);

  const dateStr = pkg.email_date
    ? new Date(pkg.email_date).toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' })
    : null;

  return (
    <div className={`package-card${selected ? ' selected' : ''}`} onClick={onSelect}>
      <div className="card-header">
        <span className="card-source-icon">{pkg.source === 'inpost' ? '📦' : '🛒'}</span>
        <span className="card-title">{pkg.tracking_number}</span>
        {routeNum != null && (
          <span style={{ background: '#6c5ce7', color: '#fff', borderRadius: '10px', padding: '1px 7px', fontSize: '0.7rem', fontWeight: 700 }}>
            #{routeNum}
          </span>
        )}
        <button className="card-delete" title="Usuń" onClick={e => { e.stopPropagation(); onDelete(); }}>✕</button>
      </div>

      <StatusBadge status={pkg.status} />

      {pkg.locker_id && (
        <div className="card-locker">Locker: <strong>{pkg.locker_id}</strong></div>
      )}
      {pkg.address_display && (
        <div className="card-address">📍 {pkg.address_display}</div>
      )}

      {pkg.pickup_code && (
        <div className="card-code-row">
          <span className="code-label">Kod odbioru:</span>
          {codeVisible
            ? <span className="code-value">{pkg.pickup_code}</span>
            : <span className="code-hidden">••••••</span>
          }
          <button className="btn-reveal" onClick={e => { e.stopPropagation(); setCodeVisible(v => !v); }}>
            {codeVisible ? 'Ukryj' : 'Pokaż'}
          </button>
        </div>
      )}

      {dateStr && <div className="card-date">{dateStr}</div>}
    </div>
  );
}

// ─── AccountsPanel ────────────────────────────────────────────────
function AccountsPanel({ onToast }) {
  const [accounts, setAccounts] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [testing, setTesting] = useState(null);
  const [form, setForm] = useState({ label: '', email: '', imap_host: '', imap_port: 993, password: '' });

  const load = () => api.get('/accounts').then(setAccounts).catch(e => onToast(e.message, 'error'));

  useEffect(() => { load(); }, []);

  const handleAdd = async () => {
    if (!form.label || !form.email || !form.imap_host || !form.password) {
      onToast('Wypełnij wszystkie pola', 'error'); return;
    }
    try {
      await api.post('/accounts', form);
      onToast('Konto dodane', 'success');
      setShowForm(false);
      setForm({ label: '', email: '', imap_host: '', imap_port: 993, password: '' });
      load();
    } catch (e) { onToast(e.message, 'error'); }
  };

  const handleDelete = async (id) => {
    if (!confirm('Usunąć to konto?')) return;
    await api.delete(`/accounts/${id}`);
    onToast('Konto usunięte', 'info');
    load();
  };

  const handleToggle = async (acc) => {
    await api.patch(`/accounts/${acc.id}`, { is_active: !acc.is_active });
    load();
  };

  const handleTest = async (acc) => {
    setTesting(acc.id);
    try {
      const r = await api.post(`/accounts/${acc.id}/test`, {});
      onToast(r.ok ? `Połączono z ${acc.email}` : `Błąd: ${r.error}`, r.ok ? 'success' : 'error');
    } finally { setTesting(null); }
  };

  const IMAP_HOSTS = [
    { label: 'Gmail', host: 'imap.gmail.com' },
    { label: 'Outlook/Hotmail', host: 'imap-mail.outlook.com' },
    { label: 'WP.pl', host: 'imap.wp.pl' },
    { label: 'Onet.pl', host: 'imap.poczta.onet.pl' },
    { label: 'o2.pl', host: 'imap.o2.pl' },
    { label: 'Interia.pl', host: 'poczta.interia.pl' },
  ];

  return (
    <div>
      <div className="account-list">
        {accounts.length === 0 && (
          <div className="empty-state">
            <div style={{ fontSize: '2rem' }}>📬</div>
            <p>Brak kont email. Dodaj pierwsze.</p>
          </div>
        )}
        {accounts.map(acc => (
          <div key={acc.id} className={`account-row${!acc.is_active ? ' account-inactive' : ''}`}>
            <div className="account-info">
              <div className="account-label">{acc.label}</div>
              <div className="account-email">{acc.email}</div>
              <div className="account-meta">
                {acc.imap_host}:{acc.imap_port}
                {acc.last_polled_at && ` · Sync: ${new Date(acc.last_polled_at).toLocaleString('pl-PL')}`}
              </div>
            </div>
            <button className="btn btn-sm btn-secondary" onClick={() => handleTest(acc)} disabled={testing === acc.id}>
              {testing === acc.id ? '...' : 'Test'}
            </button>
            <button className="btn btn-sm btn-secondary" onClick={() => handleToggle(acc)}>
              {acc.is_active ? 'Wyłącz' : 'Włącz'}
            </button>
            <button className="btn-icon" onClick={() => handleDelete(acc.id)}>🗑</button>
          </div>
        ))}
      </div>

      {!showForm ? (
        <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>+ Dodaj konto</button>
      ) : (
        <div className="form-card">
          <h3>Nowe konto email</h3>
          <div className="form-field">
            <label>Nazwa</label>
            <input placeholder="Gmail Personal" value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))} />
          </div>
          <div className="form-field">
            <label>Adres email</label>
            <input type="email" placeholder="user@gmail.com" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
          </div>
          <div className="form-field">
            <label>Serwer IMAP</label>
            <select value={form.imap_host} onChange={e => setForm(f => ({ ...f, imap_host: e.target.value }))}>
              <option value="">Wybierz lub wpisz ręcznie...</option>
              {IMAP_HOSTS.map(h => <option key={h.host} value={h.host}>{h.label} ({h.host})</option>)}
            </select>
          </div>
          {!IMAP_HOSTS.find(h => h.host === form.imap_host) && (
            <div className="form-field">
              <label>Własny host IMAP</label>
              <input placeholder="imap.example.com" value={form.imap_host} onChange={e => setForm(f => ({ ...f, imap_host: e.target.value }))} />
            </div>
          )}
          <div className="form-field">
            <label>Port IMAP</label>
            <input type="number" value={form.imap_port} onChange={e => setForm(f => ({ ...f, imap_port: parseInt(e.target.value) || 993 }))} />
          </div>
          <div className="form-field">
            <label>Hasło aplikacji</label>
            <input type="password" placeholder="Hasło aplikacji (nie zwykłe hasło)" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} />
          </div>
          <div className="form-actions">
            <button className="btn btn-primary btn-sm" onClick={handleAdd}>Dodaj</button>
            <button className="btn btn-secondary btn-sm" onClick={() => setShowForm(false)}>Anuluj</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Header ───────────────────────────────────────────────────────
function Header({ syncing, onSync, onLocate, onRoute, routeActive, onClearRoute, canRoute, userLocated }) {
  return (
    <div className="header">
      <h1>Zy<span>lmus</span></h1>
      <div className="header-actions">
        <div className={`sync-dot${syncing ? ' syncing' : ''}`} title={syncing ? 'Synchronizacja...' : 'Zsynchronizowano'} />
        <button className="btn btn-ghost btn-sm" onClick={onSync} disabled={syncing}>
          {syncing ? '⟳ Sync...' : '⟳ Sync'}
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={onLocate}
          title={userLocated ? 'Lokalizacja ustawiona' : 'Ustaw moją lokalizację'}
          style={userLocated ? { borderColor: '#55efc4', color: '#55efc4' } : {}}
        >
          📍 {userLocated ? 'Zlokalizowany' : 'Moja lokalizacja'}
        </button>
        {routeActive ? (
          <button className="btn btn-ghost btn-sm" onClick={onClearRoute} style={{ borderColor: '#ff7675', color: '#ff7675' }}>
            ✕ Wyczyść trasę
          </button>
        ) : (
          <button className="btn btn-ghost btn-sm" onClick={onRoute} disabled={!canRoute}>
            🗺 Wyznacz trasę
          </button>
        )}
      </div>
    </div>
  );
}

// ─── LeafletMap ───────────────────────────────────────────────────
function LeafletMap({ packages, selectedId, onSelectPackage, userLocation, route }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({});
  const userMarkerRef = useRef(null);
  const routeLayerRef = useRef(null);

  // Init map once
  useEffect(() => {
    if (mapRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: true }).setView([52.1, 19.4], 6);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Sync markers when packages or route changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Build route order map: package_id → position number
    const routeOrderMap = {};
    if (route?.ordered_packages) {
      route.ordered_packages.forEach((wp, idx) => {
        routeOrderMap[wp.package_id] = idx + 1;
      });
    }

    // Remove stale markers
    const currentIds = new Set(packages.map(p => p.id));
    Object.keys(markersRef.current).forEach(id => {
      if (!currentIds.has(parseInt(id))) {
        markersRef.current[id].remove();
        delete markersRef.current[id];
      }
    });

    // Add or update markers
    packages.filter(p => p.lat && p.lon).forEach(pkg => {
      const routeNum = routeOrderMap[pkg.id] ?? null;
      const icon = createPackageIcon(pkg.source, pkg.status, routeNum);

      if (markersRef.current[pkg.id]) {
        markersRef.current[pkg.id].setIcon(icon);
        markersRef.current[pkg.id].setPopupContent(popupHtml(pkg, routeNum));
      } else {
        const marker = L.marker([pkg.lat, pkg.lon], { icon })
          .bindPopup(popupHtml(pkg, routeNum))
          .addTo(map);
        marker.on('click', () => onSelectPackage(pkg.id));
        markersRef.current[pkg.id] = marker;
      }
    });
  }, [packages, route]);

  // Pan to selected package
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedId) return;
    const pkg = packages.find(p => p.id === selectedId);
    if (pkg?.lat && pkg?.lon) {
      map.flyTo([pkg.lat, pkg.lon], 16, { duration: 1.0 });
      const marker = markersRef.current[selectedId];
      if (marker) marker.openPopup();
    }
  }, [selectedId]);

  // User location marker
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (userMarkerRef.current) {
      userMarkerRef.current.remove();
      userMarkerRef.current = null;
    }
    if (userLocation) {
      const marker = L.marker([userLocation.lat, userLocation.lon], { icon: createUserIcon(), zIndexOffset: 1000 })
        .bindPopup('<strong>Twoja lokalizacja</strong>')
        .addTo(map);
      userMarkerRef.current = marker;
      map.flyTo([userLocation.lat, userLocation.lon], 13, { duration: 1.2 });
    }
  }, [userLocation]);

  // Route polyline
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (routeLayerRef.current) {
      routeLayerRef.current.remove();
      routeLayerRef.current = null;
    }
    if (route?.geometry) {
      const layer = L.geoJSON(route.geometry, {
        style: { color: '#6c5ce7', weight: 4, opacity: 0.8, dashArray: '8,4' },
      }).addTo(map);
      routeLayerRef.current = layer;
      try { map.fitBounds(layer.getBounds(), { padding: [40, 40] }); } catch (e) {}
    }
  }, [route]);

  return <div id="map" ref={containerRef} style={{ flex: 1 }} />;
}

// ─── Main App ─────────────────────────────────────────────────────
function App() {
  const [packages, setPackages] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [activeTab, setActiveTab] = useState('packages'); // 'packages' | 'accounts'
  const [filters, setFilters] = useState({ status: 'all', source: 'all', search: '' });
  const [syncing, setSyncing] = useState(false);
  const [userLocation, setUserLocation] = useState(() => {
    try { const s = localStorage.getItem('zylmus_user_loc'); return s ? JSON.parse(s) : null; } catch { return null; }
  });
  const [route, setRoute] = useState(null);
  const [routeLoading, setRouteLoading] = useState(false);
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((msg, type = 'info') => {
    const id = Date.now();
    setToasts(t => [...t, { id, msg, type }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4000);
  }, []);

  const loadPackages = useCallback(() => {
    const params = new URLSearchParams();
    if (filters.status !== 'all') params.set('status', filters.status);
    if (filters.source !== 'all') params.set('source', filters.source);
    if (filters.search) params.set('search', filters.search);
    api.get(`/packages?${params}`)
      .then(data => setPackages(data.items || []))
      .catch(e => addToast(e.message, 'error'));
  }, [filters]);

  useEffect(() => { loadPackages(); }, [loadPackages]);

  // Auto-refresh packages every 30s
  useEffect(() => {
    const timer = setInterval(loadPackages, 30000);
    return () => clearInterval(timer);
  }, [loadPackages]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await api.post('/sync', {});
      addToast('Synchronizacja w toku...', 'info');
      setTimeout(() => { loadPackages(); setSyncing(false); }, 5000);
    } catch (e) {
      addToast(e.message, 'error');
      setSyncing(false);
    }
  };

  const handleLocate = () => {
    if (!navigator.geolocation) { addToast('Geolokalizacja niedostępna w tej przeglądarce', 'error'); return; }
    navigator.geolocation.getCurrentPosition(
      pos => {
        const loc = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        setUserLocation(loc);
        localStorage.setItem('zylmus_user_loc', JSON.stringify(loc));
        addToast('Lokalizacja ustawiona', 'success');
        setRoute(null);
      },
      err => addToast(`Błąd lokalizacji: ${err.message}`, 'error'),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  const handleRoute = async () => {
    if (!userLocation) { addToast('Najpierw ustaw swoją lokalizację', 'error'); return; }
    setRouteLoading(true);
    try {
      const result = await api.post('/route', { user_lat: userLocation.lat, user_lon: userLocation.lon });
      if (result.detail) throw new Error(result.detail);
      setRoute(result);
      addToast(`Trasa: ${result.total_distance_km} km · ~${Math.round(result.total_duration_min)} min · ${result.ordered_packages.length} paczek`, 'success');
    } catch (e) {
      addToast(`Błąd trasy: ${e.message}`, 'error');
    } finally {
      setRouteLoading(false);
    }
  };

  const handleDeletePackage = async (id) => {
    await api.delete(`/packages/${id}`);
    setPackages(p => p.filter(pkg => pkg.id !== id));
    if (selectedId === id) setSelectedId(null);
    addToast('Paczka usunięta', 'info');
  };

  // Build route order map for sidebar badges
  const routeOrderMap = {};
  if (route?.ordered_packages) {
    route.ordered_packages.forEach((wp, idx) => { routeOrderMap[wp.package_id] = idx + 1; });
  }

  // Sort packages by route order when route is active
  const displayPackages = route?.ordered_packages
    ? [...packages].sort((a, b) => {
        const ra = routeOrderMap[a.id] ?? 999;
        const rb = routeOrderMap[b.id] ?? 999;
        return ra - rb;
      })
    : packages;

  const pickupReadyWithCoords = packages.filter(p => p.status === 'pickup_ready' && p.lat && p.lon);

  return (
    <div className="app">
      <Header
        syncing={syncing || routeLoading}
        onSync={handleSync}
        onLocate={handleLocate}
        onRoute={handleRoute}
        onClearRoute={() => setRoute(null)}
        routeActive={!!route}
        canRoute={!!userLocation && pickupReadyWithCoords.length > 0}
        userLocated={!!userLocation}
      />

      <div className="main">
        <div className="sidebar">
          <div className="sidebar-tabs">
            <button className={`sidebar-tab${activeTab === 'packages' ? ' active' : ''}`} onClick={() => setActiveTab('packages')}>
              Paczki ({packages.length})
            </button>
            <button className={`sidebar-tab${activeTab === 'accounts' ? ' active' : ''}`} onClick={() => setActiveTab('accounts')}>
              Konta email
            </button>
          </div>

          <div className="sidebar-content">
            {activeTab === 'packages' && (
              <>
                <div className="filter-bar">
                  <select value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}>
                    <option value="all">Wszystkie statusy</option>
                    <option value="pickup_ready">Gotowe do odbioru</option>
                    <option value="in_transit">W drodze</option>
                    <option value="delivered">Dostarczone</option>
                    <option value="expired">Wygasłe</option>
                  </select>
                  <select value={filters.source} onChange={e => setFilters(f => ({ ...f, source: e.target.value }))}>
                    <option value="all">Wszyscy dostawcy</option>
                    <option value="inpost">InPost</option>
                    <option value="amazon">Amazon</option>
                  </select>
                  <input
                    placeholder="Szukaj..."
                    value={filters.search}
                    onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
                  />
                </div>

                {displayPackages.length === 0 ? (
                  <div className="empty-state">
                    <div style={{ fontSize: '2.5rem' }}>📭</div>
                    <p>Brak paczek. Dodaj konto email i zsynchronizuj.</p>
                  </div>
                ) : (
                  <div className="package-list">
                    {displayPackages.map(pkg => (
                      <PackageCard
                        key={pkg.id}
                        pkg={pkg}
                        selected={selectedId === pkg.id}
                        routeNum={routeOrderMap[pkg.id] ?? null}
                        onSelect={() => setSelectedId(selectedId === pkg.id ? null : pkg.id)}
                        onDelete={() => handleDeletePackage(pkg.id)}
                      />
                    ))}
                  </div>
                )}
              </>
            )}

            {activeTab === 'accounts' && <AccountsPanel onToast={addToast} />}
          </div>
        </div>

        <div className="map-panel">
          <LeafletMap
            packages={packages}
            selectedId={selectedId}
            onSelectPackage={id => setSelectedId(selectedId === id ? null : id)}
            userLocation={userLocation}
            route={route}
          />

          {route && (
            <div className="route-info-bar">
              🗺 Trasa: <span>{route.total_distance_km} km</span>
              · <span>~{Math.round(route.total_duration_min)} min</span>
              · <span>{route.ordered_packages.length} paczkomat{route.ordered_packages.length === 1 ? '' : 'ów'}</span>
              <button className="btn btn-secondary btn-sm" onClick={() => setRoute(null)}>Wyczyść</button>
            </div>
          )}
        </div>
      </div>

      <Toast toasts={toasts} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
