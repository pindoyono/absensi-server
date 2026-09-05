"use client";

import { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import { format } from "date-fns";
import { id } from "date-fns/locale";
import { Button, Badge, Skeleton } from "@/components/ui/Base";

// Leaflet menyentuh `window` saat modul dievaluasi — harus dimuat client-only,
// SSR Next.js akan crash kalau di-import langsung di top-level.
const LokasiMapModal = dynamic(() => import("@/components/LokasiMapModal"), { ssr: false });

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface Device {
    device_id: string;
    nama_lokasi: string | null;
    platform: string | null;
    aktif: boolean;
    last_seen_at: string | null;
    dibuat_pada: string | null;
    raw_api_key: string | null;
    // PRD-observability-degradasi-offline-first §5.1
    jadwal_jam_lalu: number | null;
    dispensasi_jam_lalu: number | null;
    health_dilaporkan_pada: string | null;
    // Geofencing per device
    lokasi_lat: number | null;
    lokasi_lng: number | null;
    radius_meter: number | null;
    lokasi_valid_terakhir: boolean | null;
    lokasi_alasan_terakhir: string | null;
    lokasi_dicek_pada: string | null;
}

const AMBANG_BASI_JAM = 24;

function formatJamLalu(jam: number | null): string {
    if (jam === null) return "belum pernah sync";
    if (jam < 1) return `${Math.round(jam * 60)} menit lalu`;
    return `${jam.toFixed(1)} jam lalu`;
}

function isBasi(jam: number | null): boolean {
    return jam === null || jam > AMBANG_BASI_JAM;
}

const emptyForm = {
    device_id: "",
    nama_lokasi: "",
    platform: "windows",
};

function formatWaktu(t: string | null): string {
    if (!t) return "-";
    const d = new Date(t);
    if (isNaN(d.getTime())) return t;
    return format(d, "d MMM yyyy, HH:mm", { locale: id });
}

export default function DevicePage() {
    const [token, setToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [devices, setDevices] = useState<Device[]>([]);

    // PRD-observability-degradasi-offline-first §5.2: kesehatan
    const [healthSummary, setHealthSummary] = useState<{
        total_device: number;
        device_online: number;
        device_basi_dan_online: number;
    } | null>(null);

    // Modal daftar device baru
    const [modalOpen, setModalOpen] = useState(false);
    const [form, setForm] = useState({ ...emptyForm });
    const [saving, setSaving] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);

    // Hasil registrasi (api_key tampil sekali)
    const [regResult, setRegResult] = useState<{ device_id: string; api_key: string } | null>(null);
    const [copied, setCopied] = useState(false);
    // ID teks yang sedang disalin di tabel (per-baris, bukan global)
    const [copiedId, setCopiedId] = useState<string | null>(null);

    // Aksi per baris
    const [busyId, setBusyId] = useState<string | null>(null);
    const [regenResult, setRegenResult] = useState<{ device_id: string; api_key: string } | null>(null);

    // Modal atur lokasi (geofencing)
    const [lokasiDevice, setLokasiDevice] = useState<Device | null>(null);

    const loadDevices = useCallback(async (t: string) => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/device`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("token");
                window.location.href = "/login";
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setDevices(Array.isArray(data) ? data : []);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal memuat data");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        const t = localStorage.getItem("token");
        if (!t) {
            setError("Belum login. Silakan login terlebih dahulu.");
            setLoading(false);
            return;
        }
        setToken(t);
        loadDevices(t);
        // PRD-tuntaskan-device-health: ringkasan kesehatan dari /device/status-kesehatan
        fetch(`${API_BASE}/device/status-kesehatan`, { headers: { Authorization: `Bearer ${t}` } })
            .then((res) => res.ok ? res.json() : null)
            .then((data) => {
                if (Array.isArray(data)) {
                    const now = Date.now();
                    const online = data.filter((d) => {
                        if (!d.online_terakhir) return false;
                        const ts = new Date(d.online_terakhir).getTime();
                        return !isNaN(ts) && (now - ts) < 5 * 60 * 1000;
                    });
                    const basiOnline = online.filter(
                        (d) => d.jadwal_bermasalah || d.dispensasi_bermasalah
                    );
                    setHealthSummary({
                        total_device: data.length,
                        device_online: online.length,
                        device_basi_dan_online: basiOnline.length,
                    });
                }
            })
            .catch(() => { /* ringkasan opsional */ });
    }, [loadDevices]);

    const openCreate = () => {
        setForm({ ...emptyForm });
        setFormError(null);
        setRegResult(null);
        setCopied(false);
        setModalOpen(true);
    };

    const handleRegister = async () => {
        if (!token) return;
        if (!form.nama_lokasi.trim()) {
            setFormError("Nama Lokasi wajib diisi.");
            return;
        }
        setSaving(true);
        setFormError(null);
        try {
            const res = await fetch(`${API_BASE}/device/register`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({
                    // kosongkan device_id → server generate otomatis (Opsi B)
                    device_id: form.device_id.trim() || null,
                    nama_lokasi: form.nama_lokasi.trim(),
                    platform: form.platform,
                }),
            });
            const body = await res.json().catch(() => null);
            if (!res.ok) throw new Error(body?.detail ?? `HTTP ${res.status}`);
            setRegResult({ device_id: body.device_id, api_key: body.api_key });
            await loadDevices(token);
        } catch (err) {
            setFormError(err instanceof Error ? err.message : "Gagal mendaftarkan device");
        } finally {
            setSaving(false);
        }
    };

    const handleRegenerate = async (device_id: string) => {
        if (!token) return;
        if (!window.confirm(`Regenerate API key untuk "${device_id}"? Key lama akan hangus.`)) return;
        setBusyId(device_id);
        try {
            const res = await fetch(`${API_BASE}/device/${device_id}/regenerate-key`, {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
            });
            const body = await res.json().catch(() => null);
            if (!res.ok) throw new Error(body?.detail ?? `HTTP ${res.status}`);
            setRegenResult({ device_id: body.device_id, api_key: body.api_key });
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal regenerate key");
        } finally {
            setBusyId(null);
        }
    };

    const handleDeactivate = async (device_id: string) => {
        if (!token) return;
        if (!window.confirm(`Nonaktifkan device "${device_id}"? Device tidak bisa sync lagi.`)) return;
        setBusyId(device_id);
        try {
            const res = await fetch(`${API_BASE}/device/${device_id}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });
            const body = await res.json().catch(() => null);
            if (!res.ok) throw new Error(body?.detail ?? `HTTP ${res.status}`);
            await loadDevices(token);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal menonaktifkan device");
        } finally {
            setBusyId(null);
        }
    };

    const handleHardDelete = async (device_id: string) => {
        if (!token) return;
        if (!window.confirm(`HAPUS PERMANEN device "${device_id}"? Data history device ini akan hilang.`)) return;
        setBusyId(device_id);
        try {
            const res = await fetch(`${API_BASE}/device/${device_id}/hard`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });
            const body = await res.json().catch(() => null);
            if (!res.ok) throw new Error(body?.detail ?? `HTTP ${res.status}`);
            await loadDevices(token);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal menghapus device");
        } finally {
            setBusyId(null);
        }
    };

    const handleSimpanLokasi = async (lat: number, lng: number, radiusMeter: number) => {
        if (!token || !lokasiDevice) return;
        const res = await fetch(`${API_BASE}/device/${lokasiDevice.device_id}/lokasi`, {
            method: "PUT",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
            body: JSON.stringify({ lat, lng, radius_meter: radiusMeter }),
        });
        const body = await res.json().catch(() => null);
        if (!res.ok) throw new Error(body?.detail ?? `HTTP ${res.status}`);
        setLokasiDevice(null);
        await loadDevices(token);
    };

    const copyKey = async (key: string) => {
        try {
            await navigator.clipboard.writeText(key);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            /* clipboard tidak tersedia */
        }
    };

    // Salin teks per-baris di tabel (state terpisah agar "Tersalin!" tidak muncul di semua baris)
    const copyCell = async (id: string, key: string) => {
        try {
            await navigator.clipboard.writeText(key);
            setCopiedId(id);
            setTimeout(() => setCopiedId(null), 2000);
        } catch {
            /* clipboard tidak tersedia */
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Manajemen Device</h1>
                    <p className="text-sm text-slate-500 mt-1">
                        Device kiosk (Windows/Android) yang terdaftar untuk absensi wajah
                    </p>
                </div>
                <Button onClick={openCreate}>+ Daftarkan Device</Button>
            </div>

            {error && (
                <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 text-sm text-rose-700">
                    {error}
                </div>
            )}

            {/* PRD-observability-degradasi-offline-first §5.2: ringkasan kesehatan */}
            {healthSummary && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
                        <p className="text-xs uppercase text-slate-400">Total Device</p>
                        <p className="text-2xl font-bold text-slate-900 mt-1">{healthSummary.total_device}</p>
                    </div>
                    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
                        <p className="text-xs uppercase text-slate-400">Online</p>
                        <p className={`text-2xl font-bold mt-1 ${healthSummary.device_online > 0 ? "text-emerald-600" : "text-slate-400"}`}>
                            {healthSummary.device_online}
                        </p>
                    </div>
                    <div className={`bg-white rounded-xl shadow-sm border p-4 ${healthSummary.device_basi_dan_online > 0 ? "border-rose-300 bg-rose-50" : "border-slate-200"}`}>
                        <p className="text-xs uppercase text-slate-400">Basi tapi Online</p>
                        <p className={`text-2xl font-bold mt-1 ${healthSummary.device_basi_dan_online > 0 ? "text-rose-600" : "text-slate-400"}`}>
                            {healthSummary.device_basi_dan_online}
                        </p>
                        {healthSummary.device_basi_dan_online > 0 && (
                            <p className="text-xs text-rose-600 mt-1">Ada device yang online tapi data jadwal/dispensasinya basi</p>
                        )}
                    </div>
                </div>
            )}

            {/* Tabel device */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                {loading ? (
                    <div className="p-4 space-y-3">
                        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
                    </div>
                ) : devices.length === 0 ? (
                    <div className="py-12 text-center text-slate-500">
                        <p className="font-medium">Belum ada device terdaftar</p>
                        <p className="text-xs mt-1">Klik "+ Daftarkan Device" untuk menambah device kiosk</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                            <thead>
                                <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                                    <th className="py-3 px-4 text-left">Device ID</th>
                                    <th className="py-3 px-4 text-left">Device Key</th>
                                    <th className="py-3 px-4 text-left">Lokasi</th>
                                    <th className="py-3 px-4 text-left">Platform</th>
                                    <th className="py-3 px-4 text-left">Status</th>
                                    <th className="py-3 px-4 text-left">Terakhir Terlihat</th>
                                    <th className="py-3 px-4 text-left">Kesegaran Data</th>
                                    <th className="py-3 px-4 text-left">Geofencing</th>
                                    <th className="py-3 px-4 text-center">Aksi</th>
                                </tr>
                            </thead>
                            <tbody>
                                {devices.map((d) => (
                                    <tr key={d.device_id} className="border-b border-slate-100 hover:bg-slate-50 transition align-top">
                                        <td className="py-3 px-4">
                                            <div className="flex items-center gap-2">
                                                <span className="font-mono text-xs text-slate-700 break-all max-w-[160px]">{d.device_id}</span>
                                                <button
                                                    type="button"
                                                    onClick={() => copyCell(`id-${d.device_id}`, d.device_id)}
                                                    className="text-xs text-blue-600 hover:text-blue-800 hover:underline whitespace-nowrap"
                                                    title="Salin Device ID"
                                                >
                                                    {copiedId === `id-${d.device_id}` ? "Tersalin!" : "Copy"}
                                                </button>
                                            </div>
                                        </td>
                                        <td className="py-3 px-4">
                                            {d.raw_api_key ? (
                                                <div className="flex items-start gap-2">
                                                    <code className="font-mono text-xs text-slate-700 break-all max-w-[200px] line-clamp-3">{d.raw_api_key}</code>
                                                    <button
                                                        type="button"
                                                        onClick={() => copyCell(`key-${d.device_id}`, d.raw_api_key!)}
                                                        className="text-xs text-blue-600 hover:text-blue-800 hover:underline whitespace-nowrap"
                                                        title="Salin Device Key"
                                                    >
                                                        {copiedId === `key-${d.device_id}` ? "Tersalin!" : "Copy"}
                                                    </button>
                                                </div>
                                            ) : (
                                                <span className="text-xs text-slate-400">—</span>
                                            )}
                                        </td>
                                        <td className="py-3 px-4 text-slate-700">{d.nama_lokasi || "-"}</td>
                                        <td className="py-3 px-4">
                                            <Badge variant="default">{d.platform || "-"}</Badge>
                                        </td>
                                        <td className="py-3 px-4">
                                            <Badge variant={d.aktif ? "success" : "danger"}>
                                                {d.aktif ? "Aktif" : "Nonaktif"}
                                            </Badge>
                                        </td>
                                        <td className="py-3 px-4 text-slate-500 text-xs">
                                            {formatWaktu(d.last_seen_at)}
                                        </td>
                                        <td className="py-3 px-4 text-xs">
                                            <div className="space-y-1">
                                                <div className="flex items-center gap-1.5">
                                                    <span className="text-slate-400">Jadwal:</span>
                                                    <span className={isBasi(d.jadwal_jam_lalu) ? "text-rose-600 font-medium" : "text-emerald-600"}>
                                                        {formatJamLalu(d.jadwal_jam_lalu)}
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    <span className="text-slate-400">Dispensasi:</span>
                                                    <span className={isBasi(d.dispensasi_jam_lalu) ? "text-rose-600 font-medium" : "text-emerald-600"}>
                                                        {formatJamLalu(d.dispensasi_jam_lalu)}
                                                    </span>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="py-3 px-4 text-xs">
                                            {d.lokasi_lat == null ? (
                                                <span className="text-slate-400">Belum diatur</span>
                                            ) : (
                                                <div className="space-y-1">
                                                    <Badge variant={d.lokasi_valid_terakhir === false ? "danger" : "success"}>
                                                        {d.lokasi_valid_terakhir === false ? "Di luar lokasi" : d.lokasi_valid_terakhir === null ? "Belum dicek" : "Dalam radius"}
                                                    </Badge>
                                                    <div className="text-slate-400">
                                                        radius {d.radius_meter}m
                                                        {d.lokasi_dicek_pada && <> · dicek {formatWaktu(d.lokasi_dicek_pada)}</>}
                                                    </div>
                                                    {d.lokasi_alasan_terakhir && (
                                                        <div className={d.lokasi_valid_terakhir === false ? "text-rose-600" : "text-slate-400"}>
                                                            {d.lokasi_alasan_terakhir}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </td>
                                        <td className="py-3 px-4">
                                            <div className="flex flex-wrap gap-2 justify-center max-w-[280px]">
                                                <Button
                                                    variant="secondary"
                                                    className="text-xs px-2 py-1"
                                                    onClick={() => setLokasiDevice(d)}
                                                >
                                                    Atur Lokasi
                                                </Button>
                                                <Button
                                                    variant="secondary"
                                                    className="text-xs px-2 py-1"
                                                    disabled={busyId === d.device_id}
                                                    onClick={() => handleRegenerate(d.device_id)}
                                                >
                                                    Regenerate Key
                                                </Button>
                                                {d.aktif && (
                                                    <Button
                                                        variant="danger"
                                                        className="text-xs px-2 py-1"
                                                        disabled={busyId === d.device_id}
                                                        onClick={() => handleDeactivate(d.device_id)}
                                                    >
                                                        Nonaktifkan
                                                    </Button>
                                                )}
                                                <Button
                                                    variant="danger"
                                                    className="text-xs px-2 py-1 bg-rose-700 hover:bg-rose-800"
                                                    disabled={busyId === d.device_id}
                                                    onClick={() => handleHardDelete(d.device_id)}
                                                >
                                                    Hapus
                                                </Button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Modal daftar device */}
            {modalOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 border border-slate-200">
                        <h3 className="text-xl font-bold mb-4 text-slate-900">Daftarkan Device Baru</h3>

                        {regResult ? (
                            <div className="space-y-4">
                                <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
                                    <p className="font-medium text-amber-800 text-sm mb-2">
                                        API key (tampil SEKALI — simpan sekarang):
                                    </p>
                                    <div className="flex items-center gap-2">
                                        <code className="flex-1 bg-white border border-amber-300 rounded px-3 py-2 text-xs font-mono break-all">
                                            {regResult.api_key}
                                        </code>
                                        <Button variant="secondary" className="text-xs px-2 py-1" onClick={() => copyKey(regResult.api_key)}>
                                            {copied ? "Tersalin!" : "Copy"}
                                        </Button>
                                    </div>
                                    <p className="text-xs text-amber-700 mt-2">
                                        Device ID: <b>{regResult.device_id}</b>
                                    </p>
                                </div>
                                <div className="flex justify-end">
                                    <Button onClick={() => setModalOpen(false)}>Selesai</Button>
                                </div>
                            </div>
                        ) : (
                            <>
                                {formError && (
                                    <div className="mb-4 p-3 bg-rose-50 text-rose-700 rounded-lg border border-rose-200 text-sm">
                                        {formError}
                                    </div>
                                )}
                                <div className="space-y-4">
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            Device ID <span className="text-slate-400 font-normal">(opsional)</span>
                                        </label>
                                        <input
                                            type="text"
                                            value={form.device_id}
                                            onChange={(e) => setForm({ ...form, device_id: e.target.value })}
                                            className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                            placeholder="kosongkan → server generate dev-xxxxxxxx"
                                        />
                                        <p className="text-xs text-slate-400 mt-1">
                                            Biarkan kosong untuk generate otomatis, atau isi sendiri (harus unik).
                                        </p>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">Nama Lokasi</label>
                                        <input
                                            type="text"
                                            value={form.nama_lokasi}
                                            onChange={(e) => setForm({ ...form, nama_lokasi: e.target.value })}
                                            className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                            placeholder="mis. Gerbang Depan"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">Platform</label>
                                        <select
                                            value={form.platform}
                                            onChange={(e) => setForm({ ...form, platform: e.target.value })}
                                            className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                        >
                                            <option value="windows">Windows</option>
                                            <option value="android">Android</option>
                                        </select>
                                    </div>
                                </div>
                                <div className="mt-6 flex justify-end space-x-3">
                                    <Button variant="ghost" onClick={() => setModalOpen(false)} disabled={saving}>Batal</Button>
                                    <Button onClick={handleRegister} isLoading={saving}>
                                        {saving ? "Mendaftarkan..." : "Daftarkan"}
                                    </Button>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            )}

            {/* Modal atur lokasi (geofencing) */}
            {lokasiDevice && (
                <LokasiMapModal
                    deviceId={lokasiDevice.device_id}
                    initialLat={lokasiDevice.lokasi_lat}
                    initialLng={lokasiDevice.lokasi_lng}
                    initialRadius={lokasiDevice.radius_meter}
                    onClose={() => setLokasiDevice(null)}
                    onSave={handleSimpanLokasi}
                />
            )}

            {/* Modal hasil regenerate key */}
            {regenResult && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 border border-slate-200">
                        <h3 className="text-xl font-bold mb-4 text-slate-900">API Key Baru</h3>
                        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
                            <p className="font-medium text-amber-800 text-sm mb-2">
                                API key untuk <b>{regenResult.device_id}</b> (tampil SEKALI):
                            </p>
                            <div className="flex items-center gap-2">
                                <code className="flex-1 bg-white border border-amber-300 rounded px-3 py-2 text-xs font-mono break-all">
                                    {regenResult.api_key}
                                </code>
                                <Button variant="secondary" className="text-xs px-2 py-1" onClick={() => copyKey(regenResult.api_key)}>
                                    {copied ? "Tersalin!" : "Copy"}
                                </Button>
                            </div>
                        </div>
                        <div className="mt-6 flex justify-end">
                            <Button onClick={() => setRegenResult(null)}>Selesai</Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
