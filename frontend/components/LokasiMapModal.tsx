"use client";

import { useState } from "react";
import { MapContainer, TileLayer, Marker, Circle, useMapEvents } from "react-leaflet";
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
                        zoom={posisi ? 17 : 13}
                        style={{ height: "100%", width: "100%" }}
                    >
                        <TileLayer
                            attribution='&copy; <a href="https://www.esri.com">Esri</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                        />
                        <KlikUntukPin onPick={(lat, lng) => setPosisi([lat, lng])} />
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
