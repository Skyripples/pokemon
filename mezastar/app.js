const CONFIG = window.MEZASTAR_MAP_CONFIG || {};
const DATA_URL = "./data/mezastar_locations.json";
const GEO_CACHE_KEY = "mezastar_geo_cache_v1";

const els = {
  statusText: document.getElementById("status-text"),
  storeCount: document.getElementById("store-count"),
  geocodedCount: document.getElementById("geocoded-count"),
  storeList: document.getElementById("store-list"),
  searchInput: document.getElementById("search-input"),
  btnLocate: document.getElementById("btn-locate"),
  btnReload: document.getElementById("btn-reload")
};

let map;
let geocoder;
let infoWindow;
let userMarker = null;
let storeMarkers = [];
let allStores = [];
let filteredStores = [];
let geoCache = loadGeoCache();
let googleMapsPromise = null;
let isInitializing = false;

function setStatus(text) {
  els.statusText.textContent = text;
}

function loadGeoCache() {
  try {
    const raw = localStorage.getItem(GEO_CACHE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (error) {
    console.error("Failed to load geo cache:", error);
    return {};
  }
}

function saveGeoCache() {
  try {
    localStorage.setItem(GEO_CACHE_KEY, JSON.stringify(geoCache));
  } catch (error) {
    console.error("Failed to save geo cache:", error);
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function loadGoogleMapsScript(apiKey) {
  if (window.google && window.google.maps && window.google.maps.Map) {
    return Promise.resolve();
  }

  if (googleMapsPromise) {
    return googleMapsPromise;
  }

  googleMapsPromise = new Promise((resolve, reject) => {
    const callbackName = "__initMezastarGoogleMaps";
    window[callbackName] = () => {
      resolve();
      delete window[callbackName];
    };

    const script = document.createElement("script");
    const params = new URLSearchParams({
      key: apiKey,
      callback: callbackName,
      loading: "async",
      v: "weekly"
    });
    script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
    script.async = true;
    script.defer = true;
    script.dataset.googleMaps = "1";
    script.onerror = () => {
      googleMapsPromise = null;
      delete window[callbackName];
      reject(new Error("Google Maps 載入失敗"));
    };
    document.head.appendChild(script);
  });

  return googleMapsPromise;
}

function createMap() {
  map = new google.maps.Map(document.getElementById("map"), {
    center: { lat: 23.6978, lng: 120.9605 },
    zoom: 7,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: true
  });

  geocoder = new google.maps.Geocoder();
  infoWindow = new google.maps.InfoWindow();
}

async function fetchStoreData() {
  const response = await fetch(DATA_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`讀取資料失敗：${response.status}`);
  }
  return response.json();
}

function normalizeText(text) {
  return String(text || "").trim().toLowerCase();
}

function renderStoreList(stores) {
  els.storeList.innerHTML = "";

  stores.forEach((store, index) => {
    const item = document.createElement("li");
    item.className = "store-item";

    const title = document.createElement("h3");
    title.textContent = store.name || `未命名店家 ${index + 1}`;

    const address = document.createElement("p");
    address.textContent = `地址：${store.address || "無"}`;

    const phone = document.createElement("p");
    phone.textContent = `電話：${store.phone || "無"}`;

    const actions = document.createElement("div");
    actions.className = "actions";

    const btnFocus = document.createElement("button");
    btnFocus.type = "button";
    btnFocus.textContent = "查看地圖";
    btnFocus.addEventListener("click", () => {
      if (store.lat != null && store.lng != null) {
        map.panTo({ lat: store.lat, lng: store.lng });
        map.setZoom(16);
      }
    });

    const btnNav = document.createElement("button");
    btnNav.type = "button";
    btnNav.textContent = "Google Maps";
    btnNav.addEventListener("click", () => {
      const url = store.google_maps_url && store.google_maps_url.trim()
        ? store.google_maps_url
        : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(store.address || store.name)}`;
      window.open(url, "_blank");
    });

    actions.append(btnFocus, btnNav);
    item.append(title, address, phone, actions);
    els.storeList.appendChild(item);
  });
}

function clearStoreMarkers() {
  storeMarkers.forEach(marker => marker.setMap(null));
  storeMarkers = [];
}

function createMarkerForStore(store) {
  if (store.lat == null || store.lng == null) {
    return;
  }

  const marker = new google.maps.Marker({
    position: { lat: store.lat, lng: store.lng },
    map,
    title: store.name
  });

  const googleMapsUrl = store.google_maps_url && store.google_maps_url.trim()
    ? store.google_maps_url
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(store.address || store.name)}`;

  const content = `
    <div style="min-width:220px;">
      <div style="font-weight:700;font-size:16px;margin-bottom:6px;">${escapeHtml(store.name || "")}</div>
      <div style="margin-bottom:6px;">${escapeHtml(store.address || "")}</div>
      <div style="margin-bottom:10px;">${escapeHtml(store.phone || "")}</div>
      <a href="${googleMapsUrl}" target="_blank" rel="noopener noreferrer">用 Google Maps 開啟</a>
    </div>
  `;

  marker.addListener("click", () => {
    infoWindow.setContent(content);
    infoWindow.open(map, marker);
  });

  storeMarkers.push(marker);
}

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function geocodeAddress(address) {
  return new Promise((resolve, reject) => {
    geocoder.geocode({ address }, (results, status) => {
      if (status === "OK" && results && results.length > 0) {
        const location = results[0].geometry.location;
        resolve({
          lat: location.lat(),
          lng: location.lng()
        });
      } else {
        reject(new Error(`Geocode failed: ${status}`));
      }
    });
  });
}

async function ensureStoreCoordinates(stores) {
  let successCount = 0;

  for (const store of stores) {
    const cacheKey = `${store.name}__${store.address}`;

    if (store.lat != null && store.lng != null) {
      successCount += 1;
      els.geocodedCount.textContent = String(successCount);
      continue;
    }

    if (geoCache[cacheKey]) {
      store.lat = geoCache[cacheKey].lat;
      store.lng = geoCache[cacheKey].lng;
      successCount += 1;
      els.geocodedCount.textContent = String(successCount);
      continue;
    }

    if (!store.address) {
      continue;
    }

    try {
      const geo = await geocodeAddress(store.address);
      store.lat = geo.lat;
      store.lng = geo.lng;
      geoCache[cacheKey] = geo;
      successCount += 1;
      els.geocodedCount.textContent = String(successCount);
      saveGeoCache();

      await sleep(120);
    } catch (error) {
      console.warn(`Geocode failed for ${store.name}:`, error);
    }
  }
}

function updateMarkersAndList() {
  clearStoreMarkers();
  renderStoreList(filteredStores);

  filteredStores.forEach(store => {
    createMarkerForStore(store);
  });
}

function applySearch() {
  const keyword = normalizeText(els.searchInput.value);

  filteredStores = allStores.filter(store => {
    const name = normalizeText(store.name);
    const address = normalizeText(store.address);
    return keyword === "" || name.includes(keyword) || address.includes(keyword);
  });

  updateMarkersAndList();
}

function fitMarkersBounds() {
  const storesWithCoords = allStores.filter(store => store.lat != null && store.lng != null);
  if (storesWithCoords.length === 0) {
    return;
  }

  const bounds = new google.maps.LatLngBounds();
  storesWithCoords.forEach(store => {
    bounds.extend({ lat: store.lat, lng: store.lng });
  });

  if (userMarker) {
    bounds.extend(userMarker.getPosition());
  }

  map.fitBounds(bounds);
}

function locateUser() {
  if (!navigator.geolocation) {
    setStatus("此瀏覽器不支援定位。");
    return;
  }

  setStatus("正在取得你的位置...");

  navigator.geolocation.getCurrentPosition(
    position => {
      const userPos = {
        lat: position.coords.latitude,
        lng: position.coords.longitude
      };

      if (userMarker) {
        userMarker.setMap(null);
      }

      userMarker = new google.maps.Marker({
        position: userPos,
        map,
        title: "目前位置",
        label: "我"
      });

      map.panTo(userPos);
      map.setZoom(14);
      setStatus("已定位到目前位置。");
    },
    error => {
      console.error(error);
      setStatus("定位失敗，請確認瀏覽器已允許位置權限。");
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0
    }
  );
}

async function initialize() {
  if (isInitializing) {
    return;
  }

  if (!CONFIG.googleMapsApiKey || CONFIG.googleMapsApiKey === "YOUR_GOOGLE_MAPS_API_KEY") {
    setStatus("缺少 Google Maps API Key，請先更新 config.js。");
    return;
  }

  isInitializing = true;
  els.btnReload.disabled = true;

  try {
    setStatus("正在載入 Google Maps...");
    await loadGoogleMapsScript(CONFIG.googleMapsApiKey);

    createMap();

    setStatus("正在讀取店家資料...");
    const payload = await fetchStoreData();

    allStores = Array.isArray(payload.stores) ? payload.stores : [];
    filteredStores = [...allStores];
    els.storeCount.textContent = String(allStores.length);
    els.geocodedCount.textContent = "0";

    setStatus("正在確認座標資料...");
    await ensureStoreCoordinates(allStores);

    applySearch();
    fitMarkersBounds();
    setStatus(`載入完成，共 ${allStores.length} 筆店家。`);
  } catch (error) {
    console.error(error);
    setStatus(`初始化失敗：${error.message}`);
  } finally {
    isInitializing = false;
    els.btnReload.disabled = false;
  }
}

els.searchInput.addEventListener("input", applySearch);
els.btnLocate.addEventListener("click", locateUser);
els.btnReload.addEventListener("click", initialize);

initialize();
