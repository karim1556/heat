"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Map as MapLibreMap, Popup } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Feature, FeatureCollection, MultiPolygon, Point, Polygon } from "geojson";
import bbox from "@turf/bbox";
import interpolate from "@turf/interpolate";
import intersect from "@turf/intersect";
import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
import { featureCollection } from "@turf/helpers";
import { ApiError, getHeatmap, getStateBoundary, getStates, resolveLocation } from "@/lib/api";
import type { HeatmapResponse, StateBoundary, StateListEntry } from "@/lib/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import Link from "next/link";
import {
  Flame,
  Globe,
  Zap,
  CheckCircle2,
  Calendar,
  MapPin,
  Sliders,
  ArrowRight,
  TrendingUp,
  Thermometer,
  ShieldCheck,
  Cpu,
  Layers,
  Sparkles,
  Droplets,
} from "lucide-react";

// 5-step colorblind-safe sequential scale (ColorBrewer OrRd)
const HEAT_COLORS = ["#fef0d9", "#fdcc8a", "#fc8d59", "#e34a33", "#b30000"];
const DEFAULT_STATE_KEY = "IN-Gujarat";
const OSM_ATTRIBUTION = "© OpenStreetMap contributors";
const CELLS_ACROSS = 90;
const NASA_POWER_LAG_DAYS = 4;

function latestRealDate(): string {
  const d = new Date();
  d.setDate(d.getDate() - NASA_POWER_LAG_DAYS);
  return d.toISOString().slice(0, 10);
}

function subDays(isoDate: string, days: number): string {
  try {
    const d = new Date(`${isoDate}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() - days);
    return d.toISOString().slice(0, 10);
  } catch {
    return isoDate;
  }
}

function buildHeatSurface(
  points: FeatureCollection<Point>,
  boundary: StateBoundary,
): { surface: FeatureCollection; cellCount: number; ms: number } {
  const t0 = performance.now();
  const [nxmin, nymin, nxmax, nymax] = bbox(points);
  const [sxmin, symin, sxmax, symax] = bbox(boundary);

  const lats = [...new Set(points.features.map((f) => (f.geometry as Point).coordinates[1]))].sort(
    (a, b) => a - b,
  );
  let spacing = Infinity;
  for (let i = 1; i < lats.length; i += 1) spacing = Math.min(spacing, lats[i] - lats[i - 1]);
  if (!Number.isFinite(spacing) || spacing <= 0) spacing = 0.5;

  const cb: [number, number, number, number] = [sxmin, symin, sxmax, symax];
  if (cb[0] >= cb[2] || cb[1] >= cb[3]) {
    return { surface: featureCollection([]), cellCount: 0, ms: performance.now() - t0 };
  }

  const cellSize = Math.max(cb[2] - cb[0], cb[3] - cb[1]) / CELLS_ACROSS;
  const grid = interpolate(points, cellSize, {
    gridType: "square",
    property: "heat_index",
    weight: 2,
    units: "degrees",
    bbox: cb,
  });

  const clipped: Feature[] = [];
  const boundaryPoly = boundary as Feature<Polygon | MultiPolygon>;
  for (const cell of grid.features) {
    const cellPoly = cell as Feature<Polygon>;
    const heat = (cell.properties as { heat_index: number }).heat_index;
    const ring = cellPoly.geometry.coordinates[0];
    let inside = 0;
    for (let i = 0; i < 4; i += 1) {
      if (booleanPointInPolygon(ring[i] as [number, number], boundaryPoly)) inside += 1;
    }
    if (inside === 4) {
      cellPoly.properties = { heat_index: heat };
      clipped.push(cellPoly);
      continue;
    }
    if (inside === 0) {
      const cx = (ring[0][0] + ring[2][0]) / 2;
      const cy = (ring[0][1] + ring[2][1]) / 2;
      if (!booleanPointInPolygon([cx, cy] as [number, number], boundaryPoly)) continue;
    }
    try {
      const inter = intersect(
        featureCollection([cellPoly, boundaryPoly]) as FeatureCollection<Polygon | MultiPolygon>,
        { properties: { heat_index: heat } },
      );
      if (inter) clipped.push(inter);
    } catch {
      // clip fallback
    }
  }
  return { surface: featureCollection(clipped), cellCount: clipped.length, ms: performance.now() - t0 };
}

function groupByCountry(states: StateListEntry[]): Map<string, StateListEntry[]> {
  const groups = new Map<string, StateListEntry[]>();
  const sorted = [...states].sort((a, b) => a.state.localeCompare(b.state));
  for (const s of sorted) {
    const key = s.country === "IN" ? "India" : s.country === "US" ? "United States" : s.country;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(s);
  }
  return groups;
}

export default function HeatmapPage() {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const glRef = useRef<{ Popup: typeof Popup } | null>(null);
  const popupRef = useRef<Popup | null>(null);
  const lastFittedKey = useRef<string | null>(null);
  const mapSectionRef = useRef<HTMLDivElement | null>(null);

  const [mapReady, setMapReady] = useState(false);
  const [tileWarning, setTileWarning] = useState<string | null>(null);

  const [states, setStates] = useState<StateListEntry[] | null>(null);
  const [statesError, setStatesError] = useState<string | null>(null);
  const [stateKey, setStateKey] = useState<string>(DEFAULT_STATE_KEY);

  const [date, setDate] = useState(latestRealDate);
  const [data, setData] = useState<HeatmapResponse | null>(null);
  const [boundary, setBoundary] = useState<StateBoundary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [boundaryError, setBoundaryError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [colorScale, setColorScale] = useState<"absolute" | "relative">("absolute");
  const [coverage, setCoverage] = useState<"state" | "anchor">("state");

  const userToggledColorScale = useRef(false);

  const stats = useMemo(() => {
    if (!data || !data.features || data.features.length === 0) return null;
    const values = data.features.map((f) => f.properties.heat_index);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    const humidities = data.features
      .map((f) => f.properties.humidity)
      .filter((h): h is number => typeof h === "number");
    const avgHumidity = humidities.length > 0 ? humidities.reduce((a, b) => a + b, 0) / humidities.length : null;
    return { min, max, avg, avgHumidity, count: values.length };
  }, [data]);

  // Auto-default color scale to relative when temperature spread is narrow (< 6°C)
  useEffect(() => {
    if (stats && !userToggledColorScale.current) {
      if (stats.max - stats.min < 6.0) {
        setColorScale("relative");
      }
    }
  }, [stats]);

  const surfaceData = useMemo(() => {
    if (!data || !boundary) return null;
    return buildHeatSurface(data, boundary);
  }, [data, boundary]);

  const groupedStates = useMemo(() => (states ? groupByCountry(states) : new Map()), [states]);

  // Load States list
  useEffect(() => {
    getStates()
      .then(setStates)
      .catch((err: unknown) => {
        setStatesError(err instanceof ApiError ? err.message : "Failed to load state list.");
      });
  }, []);

  const [autoDetected, setAutoDetected] = useState(false);
  const [locationNotice, setLocationNotice] = useState<string | null>(null);

  const autoDetectLocation = useCallback(async () => {
    const handleGeo = async (lat?: number, lon?: number) => {
      try {
        const geo = await resolveLocation(lat !== undefined && lon !== undefined ? { lat, lon } : {});
        if (geo.state_key) {
          setStateKey(geo.state_key);
          setLocationNotice(`Detected: ${geo.state}, ${geo.country}`);
        } else if (geo.message) {
          setLocationNotice(geo.message);
        }
      } catch {
        // fail silently for auto-detect on load
      }
    };

    const getIpLocation = async () => {
      try {
        const res = await fetch("https://ipwho.is/", { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          if (data.success && typeof data.latitude === "number" && typeof data.longitude === "number") {
            return { lat: data.latitude, lon: data.longitude };
          }
        }
      } catch {}

      try {
        const res = await fetch("http://ip-api.com/json/", { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          if (data.status === "success" && typeof data.lat === "number" && typeof data.lon === "number") {
            return { lat: data.lat, lon: data.lon };
          }
        }
      } catch {}

      return null;
    };

    if ("geolocation" in navigator) {
      navigator.geolocation.getCurrentPosition(
        (pos) => handleGeo(pos.coords.latitude, pos.coords.longitude),
        async () => {
          const ipLoc = await getIpLocation();
          if (ipLoc) await handleGeo(ipLoc.lat, ipLoc.lon);
          else await handleGeo();
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }
      );
    } else {
      const ipLoc = await getIpLocation();
      if (ipLoc) await handleGeo(ipLoc.lat, ipLoc.lon);
      else await handleGeo();
    }
  }, []);

  useEffect(() => {
    if (states && states.length > 0 && !autoDetected) {
      setAutoDetected(true);
      autoDetectLocation();
    }
  }, [states, autoDetected, autoDetectLocation]);

  // Initialize MapLibre
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;
    let cancelled = false;

    import("maplibre-gl").then((maplibregl) => {
      if (cancelled || !mapContainer.current) return;
      glRef.current = maplibregl;

      const map = new maplibregl.Map({
        container: mapContainer.current,
        style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        center: [72.5714, 23.0225],
        zoom: 6,
        attributionControl: false,
      });

      map.addControl(
        new maplibregl.AttributionControl({ compact: true, customAttribution: OSM_ATTRIBUTION }),
        "bottom-right",
      );
      map.addControl(new maplibregl.NavigationControl(), "top-right");

      map.on("error", (e) => {
        const msg = String((e as { error?: { message?: string } }).error?.message ?? "");
        if (msg.includes("tile") || msg.includes("404") || msg.includes("Failed to fetch")) {
          setTileWarning("Map basemap tile server slow/unavailable -- heat surface data is fully active.");
        }
      });

      map.on("load", () => {
        map.addSource("state-border", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer({
          id: "state-border-line",
          type: "line",
          source: "state-border",
          paint: {
            "line-color": "#475569",
            "line-width": 2,
            "line-dasharray": [2, 1],
          },
        });

        map.addSource("heat-surface", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer(
          {
            id: "heat-surface-fill",
            type: "fill",
            source: "heat-surface",
            paint: {
              "fill-color": [
                "interpolate",
                ["linear"],
                ["get", "heat_index"],
                15,
                HEAT_COLORS[0],
                21,
                HEAT_COLORS[1],
                27,
                HEAT_COLORS[2],
                33,
                HEAT_COLORS[3],
                39,
                HEAT_COLORS[4],
              ],
              "fill-opacity": 0.65,
            },
          },
          "state-border-line",
        );

        map.addSource("heat-nodes", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer({
          id: "heat-nodes-circle",
          type: "circle",
          source: "heat-nodes",
          paint: {
            "circle-radius": 5,
            "circle-color": "#ffffff",
            "circle-stroke-width": 2,
            "circle-stroke-color": "#0f172a",
          },
        });

        // Hover tooltip on heat surface grid cells
        let surfaceTooltip: Popup | null = null;

        map.on("mousemove", "heat-surface-fill", (e) => {
          const feature = e.features?.[0];
          if (!feature || !glRef.current) return;
          const heatIndex = (feature.properties as { heat_index: number })?.heat_index;
          if (typeof heatIndex !== "number") return;

          map.getCanvas().style.cursor = "crosshair";
          const lngLat = e.lngLat;
          const statusLabel =
            heatIndex >= 35 ? "Severe Heat" : heatIndex >= 30 ? "High Heat" : heatIndex >= 25 ? "Moderate" : "Normal";
          const statusColor =
            heatIndex >= 35 ? "text-red-600" : heatIndex >= 30 ? "text-orange-600" : heatIndex >= 25 ? "text-amber-600" : "text-emerald-600";

          if (!surfaceTooltip) {
            surfaceTooltip = new glRef.current.Popup({
              closeButton: false,
              closeOnClick: false,
              className: "pointer-events-none z-30",
            });
          }

          surfaceTooltip
            .setLngLat(lngLat)
            .setHTML(
              `<div class="p-1 font-sans">
                <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Spot Heat Surface</div>
                <div class="flex items-baseline gap-1.5 mt-0.5">
                  <span class="text-base font-mono font-extrabold text-slate-900">${heatIndex.toFixed(1)}°C</span>
                  <span class="text-[10px] font-bold ${statusColor}">${statusLabel}</span>
                </div>
                <div class="text-[9px] font-mono text-slate-400 mt-0.5">${lngLat.lat.toFixed(3)}°N, ${lngLat.lng.toFixed(3)}°E</div>
              </div>`,
            )
            .addTo(map);
        });

        map.on("mouseleave", "heat-surface-fill", () => {
          map.getCanvas().style.cursor = "";
          if (surfaceTooltip) {
            surfaceTooltip.remove();
            surfaceTooltip = null;
          }
        });

        map.on("mouseenter", "heat-nodes-circle", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "heat-nodes-circle", () => {
          map.getCanvas().style.cursor = "";
        });

        map.on("click", "heat-nodes-circle", (e) => {
          const feature = e.features?.[0];
          if (!feature || !glRef.current) return;
          const coords = (feature.geometry as Point).coordinates.slice() as [number, number];
          const props = feature.properties as { name?: string; heat_index: number; humidity?: number; temperature?: number };

          if (popupRef.current) popupRef.current.remove();
          popupRef.current = new glRef.current.Popup()
            .setLngLat(coords)
            .setHTML(
              `<div class="font-sans text-slate-800 p-1">
                <div class="text-xs font-bold uppercase tracking-wider text-slate-500">${props.name || "Grid Node"}</div>
                <div class="text-lg font-mono font-bold text-orange-600">${props.heat_index.toFixed(1)}°C <span class="text-[10px] text-slate-400">(Shade-WBGT)</span></div>
                ${props.humidity != null ? `<div class="text-xs font-semibold text-blue-600 mt-1 flex items-center gap-1">💧 Humidity: ${props.humidity.toFixed(1)}% RH</div>` : ""}
                ${props.temperature != null ? `<div class="text-xs font-semibold text-amber-600 mt-0.5 flex items-center gap-1">🌡️ Temp: ${props.temperature.toFixed(1)}°C</div>` : ""}
                <div class="text-[10px] text-slate-400 mt-1.5 border-t border-slate-100 pt-1">Shade-WBGT GNN Forecast</div>
              </div>`,
            )
            .addTo(map);
        });

        setMapReady(true);
      });

      mapRef.current = map;
    });

    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // Fetch heatmap & boundary
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setBoundaryError(null);

    const pHeat = getHeatmap(stateKey, date, coverage);
    const pBound = getStateBoundary(stateKey);

    pHeat
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Couldn't fetch heat map data.");
          setData(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    pBound
      .then((res) => {
        if (!cancelled) setBoundary(res);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setBoundaryError(err instanceof ApiError ? err.message : "State border unavailable.");
          setBoundary(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [stateKey, date, coverage]);

  // Update map features
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const surfSource = map.getSource("heat-surface") as { setData: (d: unknown) => void } | undefined;
    if (surfSource) surfSource.setData(surfaceData?.surface ?? featureCollection([]));

    const nodeSource = map.getSource("heat-nodes") as { setData: (d: unknown) => void } | undefined;
    if (nodeSource) nodeSource.setData(data ?? featureCollection([]));

    const boundSource = map.getSource("state-border") as { setData: (d: unknown) => void } | undefined;
    if (boundSource) boundSource.setData(boundary ?? featureCollection([]));

    if (colorScale === "relative" && stats) {
      map.setPaintProperty("heat-surface-fill", "fill-color", [
        "interpolate",
        ["linear"],
        ["get", "heat_index"],
        stats.min,
        HEAT_COLORS[0],
        stats.min + (stats.max - stats.min) * 0.25,
        HEAT_COLORS[1],
        stats.min + (stats.max - stats.min) * 0.5,
        HEAT_COLORS[2],
        stats.min + (stats.max - stats.min) * 0.75,
        HEAT_COLORS[3],
        stats.max,
        HEAT_COLORS[4],
      ]);
    } else {
      map.setPaintProperty("heat-surface-fill", "fill-color", [
        "interpolate",
        ["linear"],
        ["get", "heat_index"],
        15,
        HEAT_COLORS[0],
        21,
        HEAT_COLORS[1],
        27,
        HEAT_COLORS[2],
        33,
        HEAT_COLORS[3],
        39,
        HEAT_COLORS[4],
      ]);
    }

    if (lastFittedKey.current !== stateKey) {
      let targetBbox: [number, number, number, number] | null = null;
      if (boundary) targetBbox = bbox(boundary) as [number, number, number, number];
      else if (data && data.features.length > 0) targetBbox = bbox(data) as [number, number, number, number];

      if (targetBbox) {
        map.fitBounds(targetBbox, { padding: 40, maxZoom: 9, duration: 1200 });
        lastFittedKey.current = stateKey;
      }
    }
  }, [mapReady, data, boundary, surfaceData, colorScale, stats, stateKey]);

  function scrollToMap() {
    mapSectionRef.current?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <main className="min-h-screen pb-16 space-y-12">
      {/* Hero Landing Section */}
      <section className="relative overflow-hidden bg-gradient-to-b from-amber-500/10 via-orange-500/5 to-transparent pt-12 pb-16 border-b border-slate-200/60">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 relative z-10">
          <div className="max-w-3xl space-y-6">
            
            {/* Pill Ticker */}
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/90 border border-amber-200 shadow-sm text-xs font-medium text-amber-900">
              <Sparkles className="w-3.5 h-3.5 text-amber-500" />
              <span>STGCN Graph Neural Network • Live NASA POWER API</span>
            </div>

            {/* Main Headline */}
            <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight text-slate-900 leading-[1.1]">
              Parametric Heat Insurance,{" "}
              <span className="text-gradient-solar">Priced by Real AI</span>
            </h1>

            {/* Subtitle */}
            <p className="text-lg text-slate-600 leading-relaxed">
              Real full-state heat forecasts derived from spatio-temporal graph neural networks with a state-level mu-TEVI index, fused with worker wage-loss reinforcement learning models across 79 states.
            </p>

            {/* Key Value Badges Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-2">
              <div className="flex items-center gap-2 bg-white/80 p-2.5 rounded-xl border border-slate-200/80 text-xs font-semibold text-slate-700 shadow-xs">
                <Globe className="w-4 h-4 text-orange-500 shrink-0" />
                <span>79 States Covered</span>
              </div>
              <div className="flex items-center gap-2 bg-white/80 p-2.5 rounded-xl border border-slate-200/80 text-xs font-semibold text-slate-700 shadow-xs">
                <Flame className="w-4 h-4 text-red-500 shrink-0" />
                <span>NASA POWER Live</span>
              </div>
              <div className="flex items-center gap-2 bg-white/80 p-2.5 rounded-xl border border-slate-200/80 text-xs font-semibold text-slate-700 shadow-xs">
                <Droplets className="w-4 h-4 text-blue-500 shrink-0" />
                <span>RH2M Humidity Factored</span>
              </div>
              <div className="flex items-center gap-2 bg-white/80 p-2.5 rounded-xl border border-slate-200/80 text-xs font-semibold text-slate-700 shadow-xs">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                <span>0% Synthetic Data</span>
              </div>
              <div className="flex items-center gap-2 bg-white/80 p-2.5 rounded-xl border border-slate-200/80 text-xs font-semibold text-slate-700 shadow-xs">
                <Zap className="w-4 h-4 text-amber-500 shrink-0" />
                <span>Instant Payouts</span>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-wrap items-center gap-4 pt-2">
              <button
                onClick={scrollToMap}
                className="inline-flex items-center gap-2 px-6 py-3.5 rounded-xl bg-gradient-to-r from-amber-500 via-orange-500 to-red-500 text-white font-semibold text-sm shadow-md shadow-orange-500/20 hover:shadow-lg hover:shadow-orange-500/30 hover:scale-[1.02] active:scale-95 transition-all duration-200"
              >
                <Flame className="w-4 h-4" />
                <span>Explore Live Heat Map</span>
              </button>
              <Link
                href="/simulate"
                className="inline-flex items-center gap-2 px-6 py-3.5 rounded-xl bg-white text-slate-800 font-semibold text-sm border border-slate-200/90 shadow-xs hover:bg-slate-50 hover:border-slate-300 transition-all duration-200"
              >
                <span>Simulate a Policy</span>
                <ArrowRight className="w-4 h-4 text-slate-400" />
              </Link>
            </div>

          </div>
        </div>
      </section>

      {/* Main Heat Map Interactive Section */}
      <section ref={mapSectionRef} className="max-w-7xl mx-auto px-4 sm:px-6 space-y-6">
        
        {/* Section Title */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-orange-600 mb-1">
              <Layers className="w-3.5 h-3.5" />
              <span>Real-time Severity Field</span>
            </div>
            <h2 className="text-2xl font-bold text-slate-900">Real-time Heat Severity Map</h2>
          </div>
          <div className="text-xs text-slate-500 max-w-md">
            STGCN surface clipped to state border. Shade-WBGT values mapped across node extents.
          </div>
        </div>

        {/* Global Error Banners */}
        {statesError && <ErrorBanner message={statesError} />}
        {error && (
          <div className="space-y-2">
            <ErrorBanner message={error} />
            <div className="flex flex-wrap items-center gap-2 text-xs bg-amber-50/90 p-3 rounded-xl border border-amber-200 shadow-xs">
              <span className="font-semibold text-amber-900">NASA POWER Weather Fallbacks:</span>
              <button
                type="button"
                onClick={() => setDate(subDays(date, 1))}
                className="px-3 py-1 rounded-lg bg-white border border-amber-300 font-semibold text-amber-900 shadow-xs hover:bg-amber-100 transition-all"
              >
                Try Previous Day ({subDays(date, 1)})
              </button>
              <button
                type="button"
                onClick={() => setDate(subDays(date, 3))}
                className="px-3 py-1 rounded-lg bg-white border border-amber-300 font-semibold text-amber-900 shadow-xs hover:bg-amber-100 transition-all"
              >
                Try 5-Day Lag ({subDays(date, 3)})
              </button>
              <button
                type="button"
                onClick={() => setDate(latestRealDate())}
                className="px-3 py-1 rounded-lg bg-slate-900 font-semibold text-white shadow-xs hover:bg-slate-800 transition-all"
              >
                Reset to Published Date ({latestRealDate()})
              </button>
            </div>
          </div>
        )}
        {boundaryError && <ErrorBanner message={boundaryError} />}
        {tileWarning && <ErrorBanner message={tileWarning} />}

        {/* KPI Stat Cards Row */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div className="glass-card glass-card-hover p-4 rounded-2xl border-l-4 border-l-emerald-500">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-500 mb-1">
              <span>MIN SHADE-WBGT</span>
              <Thermometer className="w-4 h-4 text-emerald-500" />
            </div>
            <div className="font-mono text-2xl font-bold text-slate-900">
              {stats ? `${stats.min.toFixed(1)}°C` : "--"}
            </div>
            <div className="text-[11px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded w-max mt-2 font-medium">
              Coolest Region Node
            </div>
          </div>

          <div className="glass-card glass-card-hover p-4 rounded-2xl border-l-4 border-l-amber-500">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-500 mb-1">
              <span>STATE AVERAGE</span>
              <TrendingUp className="w-4 h-4 text-amber-500" />
            </div>
            <div className="font-mono text-2xl font-bold text-slate-900">
              {stats ? `${stats.avg.toFixed(1)}°C` : "--"}
            </div>
            <div className="text-[11px] text-amber-800 bg-amber-50 px-2 py-0.5 rounded w-max mt-2 font-medium">
              Weighted Regional Mean
            </div>
          </div>

          <div className="glass-card glass-card-hover p-4 rounded-2xl border-l-4 border-l-red-500">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-500 mb-1">
              <span>MAX PEAK</span>
              <Flame className="w-4 h-4 text-red-500" />
            </div>
            <div className="font-mono text-2xl font-bold text-slate-900 text-red-600">
              {stats ? `${stats.max.toFixed(1)}°C` : "--"}
            </div>
            <div className="text-[11px] text-red-700 bg-red-50 px-2 py-0.5 rounded w-max mt-2 font-medium">
              Peak Danger Threshold
            </div>
          </div>

          <div className="glass-card glass-card-hover p-4 rounded-2xl border-l-4 border-l-blue-500">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-500 mb-1">
              <span>AVG HUMIDITY</span>
              <Droplets className="w-4 h-4 text-blue-500" />
            </div>
            <div className="font-mono text-2xl font-bold text-slate-900 text-blue-600">
              {stats?.avgHumidity != null ? `${stats.avgHumidity.toFixed(1)}%` : "RH2M Active"}
            </div>
            <div className="text-[11px] text-blue-700 bg-blue-50 px-2 py-0.5 rounded w-max mt-2 font-medium">
              NASA POWER RH2M Metric
            </div>
          </div>
        </div>

        {/* Control Toolbar */}
        <div className="glass-card p-4 rounded-2xl space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 items-end">
            
            {/* State Picker */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label htmlFor="main-state-select" className="block text-xs font-bold text-slate-700">
                  State & Territory ({states?.length || 0})
                </label>
                <button
                  type="button"
                  onClick={autoDetectLocation}
                  aria-label="Use my location"
                  title="Auto-Detect My Location"
                  className="text-[11px] text-amber-700 hover:text-amber-800 font-semibold flex items-center gap-1 bg-amber-50 hover:bg-amber-100 px-2 py-0.5 rounded transition-all"
                >
                  <MapPin className="w-3 h-3 text-orange-500" />
                  <span>Auto-Detect</span>
                </button>
              </div>
              <select
                id="main-state-select"
                value={stateKey}
                onChange={(e) => setStateKey(e.target.value)}
                disabled={!states}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-medium text-slate-800 focus:ring-2 focus:ring-amber-500 focus:bg-white transition-all outline-none"
              >
                {states === null && <option>Loading states...</option>}
                {[...groupedStates.entries()].map(([country, rows]) => (
                  <optgroup key={country} label={country}>
                    {rows.map((s: StateListEntry) => (
                      <option key={s.state_key} value={s.state_key}>
                        {s.state} {s.mode === "excluded" ? "(Excluded)" : s.mode === "unpriced" ? "(Unpriced)" : ""}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>

            {/* Date Selector */}
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1 flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5 text-amber-500" />
                <span>Forecast Date</span>
              </label>
              <input
                type="date"
                value={date}
                max={todayDate()}
                onChange={(e) => setDate(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-mono font-medium text-slate-800 focus:ring-2 focus:ring-amber-500 focus:bg-white transition-all outline-none"
              />
            </div>

            {/* Coverage Scope Switch */}
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1 flex items-center gap-1">
                <Globe className="w-3.5 h-3.5 text-emerald-500" />
                <span>Coverage Extent</span>
              </label>
              <div className="flex bg-slate-100 p-1 rounded-xl border border-slate-200">
                <button
                  onClick={() => setCoverage("state")}
                  className={`flex-1 py-1 text-xs font-semibold rounded-lg transition-all ${
                    coverage === "state" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Whole State
                </button>
                <button
                  onClick={() => setCoverage("anchor")}
                  className={`flex-1 py-1 text-xs font-semibold rounded-lg transition-all ${
                    coverage === "anchor" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Anchor Metro
                </button>
              </div>
            </div>

            {/* Anchor Metro Tag */}
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1 flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-red-500" />
                <span>Anchor Metro Grid</span>
              </label>
              <div className="bg-slate-100 border border-slate-200 rounded-xl px-3 py-2 text-xs font-semibold text-slate-700">
                {states?.find((s) => s.state_key === stateKey)?.metro || data?.metadata?.state || "Selected Region"}
              </div>
            </div>

            {/* Color Scale Pill Switch */}
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1 flex items-center gap-1">
                <Sliders className="w-3.5 h-3.5 text-orange-500" />
                <span>Color Scale Mode</span>
              </label>
              <div className="flex bg-slate-100 p-1 rounded-xl border border-slate-200">
                <button
                  onClick={() => {
                    userToggledColorScale.current = true;
                    setColorScale("absolute");
                  }}
                  className={`flex-1 py-1 text-xs font-semibold rounded-lg transition-all ${
                    colorScale === "absolute" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Absolute (15-39°C)
                </button>
                <button
                  onClick={() => {
                    userToggledColorScale.current = true;
                    setColorScale("relative");
                  }}
                  className={`flex-1 py-1 text-xs font-semibold rounded-lg transition-all ${
                    colorScale === "relative" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Day Relative
                </button>
              </div>
            </div>

          </div>
        </div>

        {/* Map Canvas Frame */}
        <div className="relative glass-card rounded-2xl overflow-hidden border border-slate-200/90 shadow-xl">
          {loading && (
            <div className="absolute inset-0 z-20 bg-white/70 backdrop-blur-xs flex items-center justify-center">
              <div className="flex items-center gap-3 bg-white px-5 py-3 rounded-full shadow-lg border border-slate-200">
                <div className="w-4 h-4 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
                <span className="text-xs font-bold text-slate-700">Interpolating Heat Surface...</span>
              </div>
            </div>
          )}

          <div ref={mapContainer} className="w-full h-[520px]" />

          {/* Visual Legend Bar Overlay */}
          <div className="absolute bottom-5 left-5 z-10 bg-white/95 backdrop-blur-md p-3.5 rounded-2xl border border-slate-200/90 shadow-xl text-xs space-y-2.5 w-72 sm:w-80">
            <div className="flex justify-between items-center text-[11px] font-bold text-slate-800 border-b border-slate-100 pb-1.5">
              <span className="flex items-center gap-1.5 text-slate-900">
                <Flame className="w-3.5 h-3.5 text-orange-500" />
                Shade-WBGT Surface
              </span>
              <span className="font-mono text-[10px] font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200/60">
                {colorScale === "absolute" ? "Absolute Scale" : "Day Relative"}
              </span>
            </div>

            {/* Gradient Bar */}
            <div className="h-3 w-full rounded-md overflow-hidden flex border border-slate-200/80 shadow-inner">
              {HEAT_COLORS.map((c, i) => (
                <div key={i} className="flex-1 h-full" style={{ backgroundColor: c }} />
              ))}
            </div>

            {/* Endpoint Labels */}
            <div className="flex justify-between items-center font-mono text-[11px] font-bold">
              <span className="text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200/60">
                {colorScale === "absolute" ? "15.0°C (Coolest)" : stats ? `${stats.min.toFixed(1)}°C (Min)` : "Min"}
              </span>
              <span className="text-red-700 bg-red-50 px-1.5 py-0.5 rounded border border-red-200/60">
                {colorScale === "absolute" ? "39.0°C (Hottest)" : stats ? `${stats.max.toFixed(1)}°C (Max)` : "Max"}
              </span>
            </div>

            <div className="text-[10px] text-slate-400 text-center font-medium pt-0.5">
              Live NASA POWER weather • STGCN Interpolated
            </div>
          </div>
        </div>

      </section>

      {/* Feature Showcase Grid */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 pt-8">
        <div className="text-center max-w-2xl mx-auto mb-10 space-y-2">
          <h2 className="text-2xl font-bold text-slate-900">Built on Rigorous Parametric Science</h2>
          <p className="text-sm text-slate-600">
            Three interconnected AI models work together to calculate fair, non-disputable climate insurance.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="glass-card p-6 rounded-2xl space-y-3 border-t-4 border-t-amber-500">
            <div className="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center text-amber-600 font-bold text-sm">
              01
            </div>
            <h3 className="font-bold text-slate-900 text-base">STGCN Heat Forecasting</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Spatio-temporal graph neural networks predict street-level shade-WBGT heat stress across every weather cell without synthetic gaps.
            </p>
          </div>

          <div className="glass-card p-6 rounded-2xl space-y-3 border-t-4 border-t-orange-500">
            <div className="w-10 h-10 rounded-xl bg-orange-50 flex items-center justify-center text-orange-600 font-bold text-sm">
              02
            </div>
            <h3 className="font-bold text-slate-900 text-base">POMDP Worker Wage Loss</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Multi-agent reinforcement learning models actual worker trade-offs between thermal strain and income loss using cited literature elasticity.
            </p>
          </div>

          <div className="glass-card p-6 rounded-2xl space-y-3 border-t-4 border-t-red-500">
            <div className="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center text-red-600 font-bold text-sm">
              03
            </div>
            <h3 className="font-bold text-slate-900 text-base">Copula & LSMC Pricing</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Gumbel copula fuses heat triggers into mu-TEVI indices, priced with Longstaff-Schwartz Monte Carlo option valuation and Wang risk loading.
            </p>
          </div>
        </div>
      </section>

    </main>
  );
}

function todayDate(): string {
  return new Date().toISOString().slice(0, 10);
}
