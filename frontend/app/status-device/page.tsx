"use client";

import { useState, useEffect, useCallback } from "react";
import { format } from "date-fns";
import { id } from "date-fns/locale";
import { Badge, Skeleton } from "@/components/ui/Base";

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface DeviceStatus {
    device_id: string;
    nama_lokasi: string | null;
    online_terakhir: string | null;
    health_dilaporkan_pada: string | null;
    jadwal_jam_lalu: number | null;
    dispensasi_jam_lalu: number | null;
    jadwal_bermasalah: boolean;
    dispensasi_bermasalah: boolean;
    belum_pernah_lapor: boolean;
}

function formatWaktu(t: string | null): string {
    if (!t) return "-";
    const d = new Date(t);
    if (isNaN(d.getTime())) return t;
    return format(d, "d MMM yyyy, HH:mm", { locale: id });
}

function formatJamLalu(jam: number | null): string {
    if (jam === null) return "belum pernah sync";
    if (jam < 1) return `${Math.round(jam * 60)} mnt lalu`;
    return `${jam.toFixed(1)} jam lalu`;
}

function StatusBadge({ bermasalah, belum_pernah_lapor, label }: {
    bermasalah: boolean; belum_pernah_lapor: boolean; label: string;
}) {
    if (belum_pernah_lapor) {
        return <Badge variant="default">{label}: belum ada laporan</Badge>;
    }
    return bermasalah
        ? <Badge variant="danger">{label}: bermasalah</Badge>
        : <Badge variant="success">{label}: segar</Badge>;
}

export default function StatusDevicePage() {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [rows, setRows] = useState<DeviceStatus[]>([]);
    const [refreshing, setRefreshing] = useState(false);

    const load = useCallback(async (t: string) => {
        try {
            const res = await fetch(`${API_BASE}/device/status-kesehatan`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("token");
                window.location.href = "/login";
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setRows(Array.isArray(data) ? data : []);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal memuat data");
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, []);

    useEffect(() => {
        const t = localStorage.getItem("token");
        if (!t) {
            setError("Belum login. Silakan login terlebih dahulu.");
            setLoading(false);
            return;
        }
        load(t);
        // auto-refresh tiap 60 detik — ini halaman monitoring
        const iv = setInterval(() => load(t), 60000);
        return () => clearInterval(iv);
    }, [load]);

    const refresh = () => {
        const t = localStorage.getItem("token");
        if (!t) return;
        setRefreshing(true);
        load(t);
    };

    const total = rows.length;
    const belumLapor = rows.filter((r) => r.belum_pernah_lapor).length;
    const bermasalah = rows.filter(
        (r) => !r.belum_pernah_lapor && (r.jadwal_bermasalah || r.dispensasi_bermasalah)
    ).length;

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Status Device</h1>
                    <p className="text-sm text-slate-500 mt-1">
                        Pemantauan kesegaran data jadwal &amp; dispensasi di semua kiosk
                    </p>
                </div>
                <button
                    onClick={refresh}
                    disabled={refreshing}
                    className="text-sm px-3 py-2 rounded-lg bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                >
                    {refreshing ? "Memuat..." : "↻ Muat ulang"}
                </button>
            </div>

            {error && (
                <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 text-sm text-rose-700">
                    {error}
                </div>
            )}

            {/* Ringkasan */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
                    <p className="text-xs uppercase text-slate-400">Total Device Aktif</p>
                    <p className="text-2xl font-bold text-slate-900 mt-1">{total}</p>
                </div>
                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
                    <p className="text-xs uppercase text-slate-400">Belum Ada Laporan</p>
                    <p className={`text-2xl font-bold mt-1 ${belumLapor > 0 ? "text-slate-500" : "text-slate-400"}`}>{belumLapor}</p>
                </div>
                <div className={`bg-white rounded-xl shadow-sm border p-4 ${bermasalah > 0 ? "border-rose-300 bg-rose-50" : "border-slate-200"}`}>
                    <p className="text-xs uppercase text-slate-400">Data Bermasalah</p>
                    <p className={`text-2xl font-bold mt-1 ${bermasalah > 0 ? "text-rose-600" : "text-slate-400"}`}>{bermasalah}</p>
                    {bermasalah > 0 && (
                        <p className="text-xs text-rose-600 mt-1">Jadwal basi &gt;6 jam atau dispensasi basi &gt;2 jam</p>
                    )}
                </div>
            </div>

            {/* Tabel */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                {loading ? (
                    <div className="p-4 space-y-3">
                        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
                    </div>
                ) : rows.length === 0 ? (
                    <div className="py-12 text-center text-slate-500">
                        <p className="font-medium">Belum ada device aktif terdaftar</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                            <thead>
                                <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                                    <th className="py-3 px-4 text-left">Device</th>
                                    <th className="py-3 px-4 text-left">Terakhir Online</th>
                                    <th className="py-3 px-4 text-left">Lapor Kesehatan</th>
                                    <th className="py-3 px-4 text-left">Jadwal</th>
                                    <th className="py-3 px-4 text-left">Dispensasi</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.device_id} className="border-b border-slate-100 hover:bg-slate-50 transition">
                                        <td className="py-3 px-4">
                                            <div className="font-mono text-xs text-slate-700">{r.device_id}</div>
                                            <div className="text-slate-500 text-xs">{r.nama_lokasi || "-"}</div>
                                        </td>
                                        <td className="py-3 px-4 text-slate-500 text-xs">{formatWaktu(r.online_terakhir)}</td>
                                        <td className="py-3 px-4 text-slate-500 text-xs">
                                            {r.belum_pernah_lapor ? (
                                                <span className="text-slate-400 italic">belum pernah</span>
                                            ) : formatWaktu(r.health_dilaporkan_pada)}
                                        </td>
                                        <td className="py-3 px-4">
                                            <div className="space-y-1">
                                                <StatusBadge
                                                    bermasalah={r.jadwal_bermasalah}
                                                    belum_pernah_lapor={r.belum_pernah_lapor}
                                                    label="Jadwal"
                                                />
                                                <div className="text-xs text-slate-400">{formatJamLalu(r.jadwal_jam_lalu)}</div>
                                            </div>
                                        </td>
                                        <td className="py-3 px-4">
                                            <div className="space-y-1">
                                                <StatusBadge
                                                    bermasalah={r.dispensasi_bermasalah}
                                                    belum_pernah_lapor={r.belum_pernah_lapor}
                                                    label="Dispensasi"
                                                />
                                                <div className="text-xs text-slate-400">{formatJamLalu(r.dispensasi_jam_lalu)}</div>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            <p className="text-xs text-slate-400">
                Ambang batas: jadwal dianggap basi &amp;gt;6 jam, dispensasi &amp;gt;2 jam (sama dengan config client kiosk).
            </p>
        </div>
    );
}
