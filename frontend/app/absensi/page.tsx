"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Button, Badge, Skeleton } from "@/components/ui/Base";

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface Absensi {
    record_id: string;
    siswa_id: number;
    nis: string;
    nama: string;
    kelas: string;
    tanggal: string;
    type: "MASUK" | "PULANG";
    jam_aktual: string;
    status_kehadiran_otomatis: string;
    status_kehadiran_final: string | null;
    status_efektif: string;
    catatan: string | null;
    device_id: string | null;
    approved_by: number | null;
}

const STATUS_OPTIONS = ["NORMAL", "TERLAMBAT", "PULANG_CEPAT", "IZIN", "SAKIT"];
const TYPE_OPTIONS = ["MASUK", "PULANG"];

const STATUS_BADGE: Record<string, "success" | "warning" | "danger" | "default"> = {
    NORMAL: "success",
    TERLAMBAT: "warning",
    PULANG_CEPAT: "warning",
    IZIN: "default",
    SAKIT: "danger",
};

const STATUS_LABELS: Record<string, string> = {
    NORMAL: "Hadir",
    TERLAMBAT: "Terlambat",
    PULANG_CEPAT: "Pulang Cepat",
    IZIN: "Izin",
    SAKIT: "Sakit",
};

const PAGE_SIZE = 25;

function formatTanggal(t: string): string {
    if (!t) return "-";
    const d = new Date(t);
    if (isNaN(d.getTime())) return t;
    return d.toLocaleDateString("id-ID", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function formatJam(t: string): string {
    if (!t) return "-";
    const d = new Date(t);
    if (isNaN(d.getTime())) return t;
    return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
}

export default function AbsensiPage() {
    const [token, setToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Filter
    const [cari, setCari] = useState("");
    const [cariDebounced, setCariDebounced] = useState("");
    const [dariTanggal, setDariTanggal] = useState("");
    const [sampaiTanggal, setSampaiTanggal] = useState("");
    const [filterKelas, setFilterKelas] = useState("");
    const [filterType, setFilterType] = useState("");
    const [filterStatus, setFilterStatus] = useState("");

    // Pagination
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);

    // Data + sort (sorting client-side di atas halaman aktif)
    const [rows, setRows] = useState<Absensi[]>([]);
    const [sortKey, setSortKey] = useState<string>("tanggal");
    const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

    // Daftar kelas untuk dropdown filter
    const [kelasOptions, setKelasOptions] = useState<string[]>([]);

    // Debounce pencarian
    useEffect(() => {
        const h = setTimeout(() => setCariDebounced(cari), 350);
        return () => clearTimeout(h);
    }, [cari]);

    // Reset ke halaman 1 tiap filter berubah
    useEffect(() => {
        setPage(1);
    }, [cariDebounced, dariTanggal, sampaiTanggal, filterKelas, filterType, filterStatus]);

    const loadAbsensi = useCallback(async (t: string) => {
        setLoading(true);
        try {
            const params = new URLSearchParams();
            if (dariTanggal) params.set("dari_tanggal", dariTanggal);
            if (sampaiTanggal) params.set("sampai_tanggal", sampaiTanggal);
            if (filterKelas) params.set("kelas", filterKelas);
            if (filterType) params.set("type", filterType);
            if (filterStatus) params.set("status", filterStatus);
            if (cariDebounced) params.set("cari", cariDebounced);
            params.set("limit", String(PAGE_SIZE));
            params.set("offset", String((page - 1) * PAGE_SIZE));

            const res = await fetch(`${API_BASE}/absensi/list?${params.toString()}`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("token");
                window.location.href = "/login";
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setRows(data.data ?? []);
            setTotal(data.total ?? 0);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal memuat data");
        } finally {
            setLoading(false);
        }
    }, [cariDebounced, dariTanggal, sampaiTanggal, filterKelas, filterType, filterStatus, page]);

    // Ambil daftar kelas unik dari endpoint siswa
    const loadKelas = useCallback(async (t: string) => {
        try {
            const res = await fetch(`${API_BASE}/siswa`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (!res.ok) return;
            const data = await res.json();
            if (Array.isArray(data)) {
                const unik = Array.from(new Set(data.map((s: any) => s.kelas).filter(Boolean))).sort();
                setKelasOptions(unik);
            }
        } catch {
            /* kelas opsional */
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
        loadAbsensi(t);
        loadKelas(t);
    }, [loadAbsensi, loadKelas]);

    // Sorting client-side di atas halaman aktif
    const sorted = useMemo(() => {
        const arr = [...rows];
        arr.sort((a, b) => {
            let va: any = a[sortKey as keyof Absensi];
            let vb: any = b[sortKey as keyof Absensi];
            if (va == null) va = "";
            if (vb == null) vb = "";
            const cmp = va < vb ? -1 : va > vb ? 1 : 0;
            return sortDir === "asc" ? cmp : -cmp;
        });
        return arr;
    }, [rows, sortKey, sortDir]);

    const totalHalaman = Math.max(1, Math.ceil(total / PAGE_SIZE));

    const toggleSort = (key: string) => {
        if (sortKey === key) {
            setSortDir(sortDir === "asc" ? "desc" : "asc");
        } else {
            setSortKey(key);
            setSortDir("desc");
        }
    };

    const resetFilter = () => {
        setCari("");
        setDariTanggal("");
        setSampaiTanggal("");
        setFilterKelas("");
        setFilterType("");
        setFilterStatus("");
    };

    const adaFilter =
        cari || dariTanggal || sampaiTanggal || filterKelas || filterType || filterStatus;

    const SortIcon = ({ col }: { col: string }) =>
        sortKey === col ? (
            <span className="inline-block ml-1 text-xs">{sortDir === "asc" ? "▲" : "▼"}</span>
        ) : null;

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900">Daftar Absensi</h1>
                <p className="text-sm text-slate-500 mt-1">
                    Rekap detail presensi siswa — cari, filter, dan urutkan untuk mempermudah pembacaan
                </p>
            </div>

            {/* Filter & Pencarian */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 space-y-4">
                <div className="flex flex-col sm:flex-row gap-3">
                    <div className="flex-1">
                        <label className="block text-xs font-medium text-slate-500 mb-1">Cari Nama / NISN</label>
                        <input
                            type="text"
                            value={cari}
                            onChange={(e) => setCari(e.target.value)}
                            className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                            placeholder="Ketik nama atau NISN siswa..."
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Dari Tanggal</label>
                        <input
                            type="date"
                            value={dariTanggal}
                            onChange={(e) => setDariTanggal(e.target.value)}
                            className="border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Sampai Tanggal</label>
                        <input
                            type="date"
                            value={sampaiTanggal}
                            onChange={(e) => setSampaiTanggal(e.target.value)}
                            className="border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                        />
                    </div>
                </div>

                <div className="flex flex-wrap gap-3 items-end">
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Kelas</label>
                        <select
                            value={filterKelas}
                            onChange={(e) => setFilterKelas(e.target.value)}
                            className="border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                        >
                            <option value="">Semua Kelas</option>
                            {kelasOptions.map((k) => (
                                <option key={k} value={k}>{k}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Jenis</label>
                        <select
                            value={filterType}
                            onChange={(e) => setFilterType(e.target.value)}
                            className="border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                        >
                            <option value="">Semua</option>
                            {TYPE_OPTIONS.map((t) => (
                                <option key={t} value={t}>{t === "MASUK" ? "Masuk" : "Pulang"}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Status</label>
                        <select
                            value={filterStatus}
                            onChange={(e) => setFilterStatus(e.target.value)}
                            className="border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                        >
                            <option value="">Semua Status</option>
                            {STATUS_OPTIONS.map((s) => (
                                <option key={s} value={s}>{STATUS_LABELS[s] ?? s}</option>
                            ))}
                        </select>
                    </div>
                    <Button variant="ghost" onClick={resetFilter} className="text-sm">
                        Reset Filter
                    </Button>
                </div>
            </div>

            {/* Ringkasan */}
            <div className="flex items-center justify-between text-sm text-slate-500">
                <span>
                    Menampilkan <b className="text-slate-800">{rows.length}</b> dari <b className="text-slate-800">{total}</b> record
                    {adaFilter && " (terfilter)"}
                </span>
            </div>

            {/* Tabel */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                {loading ? (
                    <div className="p-4 space-y-3">
                        {[1, 2, 3, 4, 5].map((i) => (
                            <Skeleton key={i} className="h-12 w-full" />
                        ))}
                    </div>
                ) : error ? (
                    <div className="p-6 text-center">
                        <p className="text-rose-600 text-sm">{error}</p>
                        <Button variant="secondary" onClick={() => token && loadAbsensi(token)} className="mt-3 text-sm">
                            Coba Lagi
                        </Button>
                    </div>
                ) : sorted.length === 0 ? (
                    <div className="py-12 text-center text-slate-500">
                        <p className="font-medium">Tidak ada data absensi</p>
                        <p className="text-xs mt-1">Ubah filter atau rentang tanggal untuk melihat data lain</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                            <thead>
                                <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                                    <th className="py-3 px-4 text-left cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("tanggal")}>
                                        Tanggal <SortIcon col="tanggal" />
                                    </th>
                                    <th className="py-3 px-4 text-left cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("nama")}>
                                        Siswa <SortIcon col="nama" />
                                    </th>
                                    <th className="py-3 px-4 text-left cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("kelas")}>
                                        Kelas <SortIcon col="kelas" />
                                    </th>
                                    <th className="py-3 px-4 text-left cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("type")}>
                                        Jenis <SortIcon col="type" />
                                    </th>
                                    <th className="py-3 px-4 text-left cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("jam_aktual")}>
                                        Jam <SortIcon col="jam_aktual" />
                                    </th>
                                    <th className="py-3 px-4 text-left cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("status_efektif")}>
                                        Status <SortIcon col="status_efektif" />
                                    </th>
                                    <th className="py-3 px-4 text-left">Catatan</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sorted.map((a) => (
                                    <tr key={a.record_id} className="border-b border-slate-100 hover:bg-slate-50 transition">
                                        <td className="py-3 px-4 whitespace-nowrap text-slate-700">{formatTanggal(a.tanggal)}</td>
                                        <td className="py-3 px-4">
                                            <div className="font-medium text-slate-800">{a.nama}</div>
                                            <div className="text-xs text-slate-400 font-mono">{a.nis}</div>
                                        </td>
                                        <td className="py-3 px-4 text-slate-600">{a.kelas}</td>
                                        <td className="py-3 px-4">
                                            <Badge variant={a.type === "MASUK" ? "success" : "warning"}>
                                                {a.type === "MASUK" ? "Masuk" : "Pulang"}
                                            </Badge>
                                        </td>
                                        <td className="py-3 px-4 font-mono text-slate-600">{formatJam(a.jam_aktual)}</td>
                                        <td className="py-3 px-4">
                                            <Badge variant={STATUS_BADGE[a.status_efektif] ?? "default"}>
                                                {STATUS_LABELS[a.status_efektif] ?? a.status_efektif}
                                            </Badge>
                                        </td>
                                        <td className="py-3 px-4 text-slate-500 max-w-[220px] truncate" title={a.catatan ?? ""}>
                                            {a.catatan || "-"}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Pagination */}
            {!loading && !error && total > 0 && (
                <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-500">
                        Halaman {page} dari {totalHalaman}
                    </span>
                    <div className="flex gap-2">
                        <Button
                            variant="secondary"
                            className="text-sm"
                            disabled={page <= 1}
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                        >
                            ← Sebelumnya
                        </Button>
                        <Button
                            variant="secondary"
                            className="text-sm"
                            disabled={page >= totalHalaman}
                            onClick={() => setPage((p) => Math.min(totalHalaman, p + 1))}
                        >
                            Berikutnya →
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}
