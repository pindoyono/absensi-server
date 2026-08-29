"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { format, subDays } from "date-fns";
import { Button, Skeleton } from "@/components/ui/Base";

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface RekapRow {
    siswa_id: number;
    nis: string;
    nama: string;
    kelas: string;
    hadir: number;
    terlambat: number;
    izin: number;
    tanpa_keterangan_estimasi: number;
}

interface RekapResponse {
    periode: { dari: string; sampai: string };
    kelas: string;
    data: RekapRow[];
}

function pct(part: number, total: number): string {
    if (!total) return "0%";
    return `${Math.round((part / total) * 100)}%`;
}

export default function LaporanPage() {
    const [token, setToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [dari, setDari] = useState(format(subDays(new Date(), 30), "yyyy-MM-dd"));
    const [sampai, setSampai] = useState(format(new Date(), "yyyy-MM-dd"));
    const [kelas, setKelas] = useState("");
    const [kelasOptions, setKelasOptions] = useState<string[]>([]);

    const [cari, setCari] = useState("");
    const [rows, setRows] = useState<RekapRow[]>([]);
    const [periode, setPeriode] = useState<{ dari: string; sampai: string } | null>(null);

    const [sortKey, setSortKey] = useState<keyof RekapRow>("nama");
    const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

    const loadKelas = useCallback(async (t: string) => {
        try {
            const res = await fetch(`${API_BASE}/siswa`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (!res.ok) return;
            const data = await res.json();
            if (Array.isArray(data)) {
                setKelasOptions(Array.from(new Set(data.map((s: any) => s.kelas).filter(Boolean))).sort());
            }
        } catch {
            /* opsional */
        }
    }, []);

    const loadRekap = useCallback(async (t: string) => {
        setLoading(true);
        setError(null);
        try {
            const params = new URLSearchParams({ dari_tanggal: dari, sampai_tanggal: sampai });
            if (kelas) params.set("kelas", kelas);
            const res = await fetch(`${API_BASE}/laporan/rekap?${params.toString()}`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("token");
                window.location.href = "/login";
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data: RekapResponse = await res.json();
            setRows(data.data ?? []);
            setPeriode(data.periode ?? null);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal memuat laporan");
        } finally {
            setLoading(false);
        }
    }, [dari, sampai, kelas]);

    useEffect(() => {
        const t = localStorage.getItem("token");
        if (!t) {
            setError("Belum login. Silakan login terlebih dahulu.");
            setLoading(false);
            return;
        }
        setToken(t);
        loadKelas(t);
    }, [loadKelas]);

    useEffect(() => {
        if (token) loadRekap(token);
    }, [token, loadRekap]);

    const filtered = useMemo(() => {
        const q = cari.trim().toLowerCase();
        const arr = q
            ? rows.filter((r) => r.nama.toLowerCase().includes(q) || r.nis.toLowerCase().includes(q))
            : [...rows];
        arr.sort((a, b) => {
            const va = a[sortKey];
            const vb = b[sortKey];
            const cmp = va < vb ? -1 : va > vb ? 1 : 0;
            return sortDir === "asc" ? cmp : -cmp;
        });
        return arr;
    }, [rows, cari, sortKey, sortDir]);

    const ringkas = useMemo(() => {
        const total = filtered.reduce(
            (acc, r) => {
                acc.hadir += r.hadir;
                acc.terlambat += r.terlambat;
                acc.izin += r.izin;
                acc.alpha += r.tanpa_keterangan_estimasi;
                return acc;
            },
            { hadir: 0, terlambat: 0, izin: 0, alpha: 0 }
        );
        return total;
    }, [filtered]);

    const toggleSort = (key: keyof RekapRow) => {
        if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
        else { setSortKey(key); setSortDir("asc"); }
    };

    const exportCSV = () => {
        const header = ["NISN", "Nama", "Kelas", "Hadir", "Terlambat", "Izin/Sakit", "Tanpa Keterangan (estimasi)", "Persentase Hadir"];
        const lines = filtered.map((r) => {
            const totalHari = r.hadir + r.terlambat + r.izin + r.tanpa_keterangan_estimasi || 1;
            return [
                r.nis, r.nama, r.kelas, r.hadir, r.terlambat, r.izin, r.tanpa_keterangan_estimasi,
                pct(r.hadir, totalHari),
            ].join(",");
        });
        const csv = "﻿" + [header.join(","), ...lines].join("\n");
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `laporan_kehadiran_${dari}_sd_${sampai}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    };

    const SortIcon = ({ col }: { col: keyof RekapRow }) =>
        sortKey === col ? <span className="ml-1 text-xs">{sortDir === "asc" ? "▲" : "▼"}</span> : null;

    const preset = (hari: number) => {
        setDari(format(subDays(new Date(), hari), "yyyy-MM-dd"));
        setSampai(format(new Date(), "yyyy-MM-dd"));
    };

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Laporan Kehadiran</h1>
                    <p className="text-sm text-slate-500 mt-1">
                        Rekap per siswa untuk periode tertentu{periode ? ` (${periode.dari} s.d. ${periode.sampai})` : ""}
                    </p>
                </div>
                <Button variant="secondary" onClick={exportCSV} disabled={loading || filtered.length === 0}>
                    Export CSV
                </Button>
            </div>

            {/* Filter periode */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 space-y-4">
                <div className="flex flex-wrap gap-3 items-end">
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Dari Tanggal</label>
                        <input
                            type="date"
                            value={dari}
                            onChange={(e) => setDari(e.target.value)}
                            className="border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Sampai Tanggal</label>
                        <input
                            type="date"
                            value={sampai}
                            onChange={(e) => setSampai(e.target.value)}
                            className="border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Kelas</label>
                        <select
                            value={kelas}
                            onChange={(e) => setKelas(e.target.value)}
                            className="border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                        >
                            <option value="">Semua Kelas</option>
                            {kelasOptions.map((k) => (
                                <option key={k} value={k}>{k}</option>
                            ))}
                        </select>
                    </div>
                    <div className="flex-1 min-w-[180px]">
                        <label className="block text-xs font-medium text-slate-500 mb-1">Cari Nama / NISN</label>
                        <input
                            type="text"
                            value={cari}
                            onChange={(e) => setCari(e.target.value)}
                            className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                            placeholder="Ketik nama atau NISN..."
                        />
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    <Button variant="ghost" className="text-xs" onClick={() => preset(7)}>7 hari terakhir</Button>
                    <Button variant="ghost" className="text-xs" onClick={() => preset(30)}>30 hari terakhir</Button>
                    <Button variant="ghost" className="text-xs" onClick={() => preset(90)}>±90 hari</Button>
                    <Button variant="ghost" className="text-xs" onClick={() => { setKelas(""); setCari(""); }}>Reset Filter</Button>
                </div>
            </div>

            {/* Kartu ringkasan */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                    { label: "Hadir", value: ringkas.hadir, color: "text-emerald-600", bg: "bg-emerald-50" },
                    { label: "Terlambat", value: ringkas.terlambat, color: "text-amber-600", bg: "bg-amber-50" },
                    { label: "Izin / Sakit", value: ringkas.izin, color: "text-blue-600", bg: "bg-blue-50" },
                    { label: "Tanpa Ket.", value: ringkas.alpha, color: "text-rose-600", bg: "bg-rose-50" },
                ].map((c) => (
                    <div key={c.label} className={`rounded-xl border border-slate-200 p-4 ${c.bg}`}>
                        <p className="text-xs text-slate-500">{c.label}</p>
                        <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
                    </div>
                ))}
            </div>

            {/* Tabel rekap */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                {loading ? (
                    <div className="p-4 space-y-3">
                        {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
                    </div>
                ) : error ? (
                    <div className="p-6 text-center">
                        <p className="text-rose-600 text-sm">{error}</p>
                        <Button variant="secondary" className="mt-3 text-sm" onClick={() => token && loadRekap(token)}>
                            Coba Lagi
                        </Button>
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="py-12 text-center text-slate-500">
                        <p className="font-medium">Tidak ada data</p>
                        <p className="text-xs mt-1">Ubah periode, kelas, atau kata kunci pencarian</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                            <thead>
                                <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                                    <th className="py-3 px-4 text-left cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("nama")}>
                                        NISN / Nama <SortIcon col="nama" />
                                    </th>
                                    <th className="py-3 px-4 text-left cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("kelas")}>
                                        Kelas <SortIcon col="kelas" />
                                    </th>
                                    <th className="py-3 px-4 text-center cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("hadir")}>
                                        Hadir <SortIcon col="hadir" />
                                    </th>
                                    <th className="py-3 px-4 text-center cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("terlambat")}>
                                        Terlambat <SortIcon col="terlambat" />
                                    </th>
                                    <th className="py-3 px-4 text-center cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("izin")}>
                                        Izin/Sakit <SortIcon col="izin" />
                                    </th>
                                    <th className="py-3 px-4 text-center cursor-pointer hover:text-blue-600 select-none" onClick={() => toggleSort("tanpa_keterangan_estimasi")}>
                                        Tanpa Ket. <SortIcon col="tanpa_keterangan_estimasi" />
                                    </th>
                                    <th className="py-3 px-4 text-left">Persentase Hadir</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((r) => {
                                    const totalHari = r.hadir + r.terlambat + r.izin + r.tanpa_keterangan_estimasi || 1;
                                    const persen = Math.round((r.hadir / totalHari) * 100);
                                    return (
                                        <tr key={r.siswa_id} className="border-b border-slate-100 hover:bg-slate-50 transition">
                                            <td className="py-3 px-4">
                                                <div className="font-medium text-slate-800">{r.nama}</div>
                                                <div className="text-xs text-slate-400 font-mono">{r.nis}</div>
                                            </td>
                                            <td className="py-3 px-4 text-slate-600">{r.kelas}</td>
                                            <td className="py-3 px-4 text-center font-medium text-emerald-700">{r.hadir}</td>
                                            <td className="py-3 px-4 text-center text-amber-700">{r.terlambat}</td>
                                            <td className="py-3 px-4 text-center text-blue-700">{r.izin}</td>
                                            <td className="py-3 px-4 text-center text-rose-700">{r.tanpa_keterangan_estimasi}</td>
                                            <td className="py-3 px-4">
                                                <div className="flex items-center gap-2">
                                                    <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden">
                                                        <div
                                                            className={`h-full ${persen >= 80 ? "bg-emerald-500" : persen >= 60 ? "bg-amber-500" : "bg-rose-500"}`}
                                                            style={{ width: `${persen}%` }}
                                                        />
                                                    </div>
                                                    <span className="text-xs text-slate-500 w-10">{persen}%</span>
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {!loading && !error && filtered.length > 0 && (
                <p className="text-xs text-slate-400">
                    Menampilkan {filtered.length} siswa · "Tanpa Keterangan" adalah estimasi (total hari dalam rentang −
                    jumlah record masuk; belum exclude hari libur).
                </p>
            )}
        </div>
    );
}
