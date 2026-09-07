"use client";

import { useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, Marker, Circle, useMapEvents, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Button } from "@/components/ui/Base";

// Ikon marker default Leaflet gagal resolve path-nya lewat bundler Next.js/webpack
// (asset URL berbasis import.meta yang tidak dikenali) — pakai CDN sebagai gantinya,
// pola workaround standar untuk react-leaflet + Next.js.
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
    iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
    shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

// Fallback kalau device belum pernah punya titik lokasi — SMKN 2 Malinau.
const DEFAULT_CENTER: [number, number] = [3.5728, 116.6286];

interface LokasiMapModalProps {
    deviceId: string;
    initialLat: number | null;
    initialLng: number | null;
    initialRadius: number | null;
    onClose: () => void;
    onSave: (lat: number, lng: number, radiusMeter: number) => Promise<void>;
}

function KlikUntukPin({ onPick }: { onPick: (lat: number, lng: number) => void }) {
    useMapEvents({
        click(e) {
            onPick(e.latlng.lat, e.latlng.lng);
        },
    });
    return null;
}

// Menggeser view peta ke koordinat hasil pencarian. `nonce` dinaikkan tiap
// pencarian supaya mencari koordinat yang sama dua kali tetap memindahkan peta.
function PindahKeHasilCari({ target }: { target: { pos: [number, number]; nonce: number } | null }) {
    const map = useMap();
    useEffect(() => {
        if (target) map.setView(target.pos, Math.max(map.getZoom(), 18), { animate: true });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [target?.nonce]);
    return null;
}

/** Ambil dua angka pertama dari teks (mendukung "lat,lng", "lat, lng", atau tempelan Google Maps). */
function parseKoordinat(teks: string): [number, number] | null {
    const m = teks.match(/(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)/);
    if (!m) return null;
    const lat = parseFloat(m[1]);
    const lng = parseFloat(m[2]);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
    return [lat, lng];
}

export default function LokasiMapModal({
    deviceId,
    initialLat,
    initialLng,
    initialRadius,
    onClose,
    onSave,
}: LokasiMapModalProps) {
    const [posisi, setPosisi] = useState<[number, number] | null>(
        initialLat != null && initialLng != null ? [initialLat, initialLng] : null
    );
    const [radius, setRadius] = useState<number>(initialRadius ?? 100);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [cari, setCari] = useState("");
    const [flyKe, setFlyKe] = useState<{ pos: [number, number]; nonce: number } | null>(null);
    const nonceRef = useRef(0);

    const handleCari = () => {
        const koord = parseKoordinat(cari);
        if (!koord) {
            setError("Format koordinat tidak dikenali. Contoh: 3.5748899, 116.6299207");
            return;
        }
        setError(null);
        setPosisi(koord);
        setFlyKe({ pos: koord, nonce: ++nonceRef.current });
    };

    const handleSave = async () => {
        if (!posisi) {
            setError("Klik pada peta dulu untuk menentukan titik lokasi kiosk.");
            return;
        }
        if (!Number.isFinite(radius) || radius <= 0) {
            setError("Radius harus angka lebih dari 0 meter.");
            return;
        }
        setSaving(true);
        setError(null);
        try {
            await onSave(posisi[0], posisi[1], Math.round(radius));
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal menyimpan lokasi");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl p-6 border border-slate-200">
                <h3 className="text-xl font-bold mb-1 text-slate-900">Atur Lokasi Kiosk</h3>
                <p className="text-sm text-slate-500 mb-4">
                    <span className="font-mono">{deviceId}</span> — klik peta untuk pin titik acuan, geser marker
                    untuk koreksi, lalu atur radius toleransi (meter).
                </p>

                {error && (
                    <div className="mb-3 p-3 bg-rose-50 text-rose-700 rounded-lg border border-rose-200 text-sm">
                        {error}
                    </div>
                )}

                <div className="flex gap-2 mb-3">
                    <input
                        type="text"
                        value={cari}
                        onChange={(e) => setCari(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleCari(); } }}
                        placeholder="Cari koordinat — contoh: 3.5748899, 116.6299207"
                        className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <Button variant="secondary" onClick={handleCari}>Cari</Button>
                </div>

                <div className="h-80 w-full rounded-lg overflow-hidden border border-slate-200 mb-4 relative">
                    <button
                        type="button"
                        onClick={(e) => {
                            const el = e.currentTarget.parentElement;
                            if (!el) return;
                            if (document.fullscreenElement) {
                                document.exitFullscreen().catch(() => { });
                            } else {
                                el.requestFullscreen().catch(() => { });
                            }
                        }}
                        className="absolute top-2 right-2 z-[1000] bg-white/90 hover:bg-white text-slate-700 text-xs font-medium px-2.5 py-1.5 rounded-md shadow border border-slate-200"
                        title="Layar penuh"
                    >
                        ⛶ Fullscreen
                    </button>
                    <MapContainer
                        center={posisi ?? DEFAULT_CENTER}
                        zoom={posisi ? 19 : 16}
                        maxZoom={24}
                        style={{ height: "100%", width: "100%" }}
                    >
                        <TileLayer
                            attribution='&copy; <a href="https://www.esri.com">Esri</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                        />
                        <KlikUntukPin onPick={(lat, lng) => setPosisi([lat, lng])} />
                        <PindahKeHasilCari target={flyKe} />
                        {posisi && (
                            <>
                                <Marker
                                    position={posisi}
                                    draggable
                                    eventHandlers={{
                                        dragend: (e) => {
                                            const p = (e.target as L.Marker).getLatLng();
                                            setPosisi([p.lat, p.lng]);
                                        },
                                    }}
                                />
                                <Circle
                                    center={posisi}
                                    radius={radius}
                                    pathOptions={{ color: "#2563eb", fillOpacity: 0.12 }}
                                />
                            </>
                        )}
                    </MapContainer>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">Latitude</label>
                        <input
                            type="text" readOnly
                            value={posisi ? posisi[0].toFixed(6) : ""}
                            placeholder="Klik peta"
                            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-slate-50 text-slate-600 font-mono"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">Longitude</label>
                        <input
                            type="text" readOnly
                            value={posisi ? posisi[1].toFixed(6) : ""}
                            placeholder="Klik peta"
                            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-slate-50 text-slate-600 font-mono"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">Radius (meter)</label>
                        <input
                            type="number" min={1} value={radius}
                            onChange={(e) => setRadius(Number(e.target.value))}
                            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                    </div>
                </div>

                <div className="flex justify-end gap-3">
                    <Button variant="ghost" onClick={onClose} disabled={saving}>Batal</Button>
                    <Button onClick={handleSave} isLoading={saving}>
                        {saving ? "Menyimpan..." : "Simpan Lokasi"}
                    </Button>
                </div>
            </div>
        </div>
    );
}
