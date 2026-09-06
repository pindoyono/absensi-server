"use client";

import { useState, useEffect, useCallback } from "react";
import { Button, Badge, Skeleton } from "@/components/ui/Base";

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface JadwalStandar {
    id?: number;
    hari: string;
    kelas: string | null;
    kelas_id: number | null;
    jam_masuk: string;
    jam_pulang: string;
}

interface KelasOption { id: number; nama: string; }

interface JadwalOverride {
    id: number;
    tanggal: string;
    kelas: string | null;
    jam_masuk: string | null;
    jam_pulang: string | null;
    alasan: string | null;
    dibuat_oleh: number;
}

const HARI_LIST = ["SENIN", "SELASA", "RABU", "KAMIS", "JUMAT"];

const HARI_LABELS: Record<string, string> = {
    SENIN: "Senin",
    SELASA: "Selasa",
    RABU: "Rabu",
    KAMIS: "Kamis",
    JUMAT: "Jumat",
};

const JADWAL_DEFAULT: Record<string, { masuk: string; pulang: string }> = {
    SENIN: { masuk: "07:30", pulang: "15:35" },
    SELASA: { masuk: "07:30", pulang: "15:35" },
    RABU: { masuk: "07:30", pulang: "15:10" },
    KAMIS: { masuk: "07:30", pulang: "15:10" },
    JUMAT: { masuk: "07:30", pulang: "11:45" },
};

export default function JadwalPage() {
    const [token, setToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Jadwal Standar
    const [jadwalStandar, setJadwalStandar] = useState<JadwalStandar[]>([]);
    const [editingStandar, setEditingStandar] = useState<string | null>(null);
    const [formStandar, setFormStandar] = useState<{ jam_masuk: string; jam_pulang: string }>({ jam_masuk: "07:30", jam_pulang: "15:35" });
    const [savingStandar, setSavingStandar] = useState(false);
    const [deletingStandarId, setDeletingStandarId] = useState<number | null>(null);
    // null = jadwal umum (semua kelas); angka = jadwal khusus kelas itu
    const [standarScope, setStandarScope] = useState<number | null>(null);

    // Jadwal Override
    const [jadwalOverride, setJadwalOverride] = useState<JadwalOverride[]>([]);
    const [modalOverrideOpen, setModalOverrideOpen] = useState(false);
    const [editingOverrideId, setEditingOverrideId] = useState<number | null>(null);
    const [formOverride, setFormOverride] = useState({
        tanggal: new Date().toISOString().split("T")[0],
        kelas: "",
        jam_masuk: "",
        jam_pulang: "",
        alasan: "",
    });
    const [savingOverride, setSavingOverride] = useState(false);
    const [deletingOverrideId, setDeletingOverrideId] = useState<number | null>(null);
    const [kelasOptions, setKelasOptions] = useState<KelasOption[]>([]);

    const loadStandar = useCallback(async (t: string) => {
        try {
            const res = await fetch(`${API_BASE}/jadwal/standar`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("token");
                window.location.href = "/login";
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setJadwalStandar(Array.isArray(data) ? data : []);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal memuat jadwal standar");
        }
    }, []);

    const loadOverride = useCallback(async (t: string) => {
        try {
            const res = await fetch(`${API_BASE}/jadwal/override`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("token");
                window.location.href = "/login";
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setJadwalOverride(Array.isArray(data) ? data : []);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal memuat jadwal override");
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
        Promise.all([loadStandar(t), loadOverride(t)]).finally(() => setLoading(false));
        fetch(`${API_BASE}/kelas`, { headers: { Authorization: `Bearer ${t}` } })
            .then((r) => (r.ok ? r.json() : []))
            .then((d) => setKelasOptions(
                Array.isArray(d)
                    ? d.map((k: any) => ({ id: k.id, nama: k.nama })).sort((a: KelasOption, b: KelasOption) => a.nama.localeCompare(b.nama))
                    : []
            ))
            .catch(() => setKelasOptions([]));
    }, [loadStandar, loadOverride]);

    const handleSaveStandar = async (hari: string) => {
        if (!token) return;
        setSavingStandar(true);
        try {
            const res = await fetch(`${API_BASE}/jadwal/standar`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({
                    hari,
                    kelas_id: standarScope,
                    jam_masuk: formStandar.jam_masuk,
                    jam_pulang: formStandar.jam_pulang,
                }),
            });
            if (!res.ok) {
                const body = await res.json().catch(() => null);
                throw new Error(body?.detail ?? `HTTP ${res.status}`);
            }
            setEditingStandar(null);
            await loadStandar(token);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal menyimpan jadwal");
        } finally {
            setSavingStandar(false);
        }
    };

    const handleDeleteStandar = async (id: number) => {
        if (!token) return;
        if (!window.confirm("Hapus jadwal khusus kelas ini? Kelas akan kembali mengikuti jadwal umum.")) return;
        setDeletingStandarId(id);
        try {
            const res = await fetch(`${API_BASE}/jadwal/standar/${id}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) {
                const body = await res.json().catch(() => null);
                throw new Error(body?.detail ?? `HTTP ${res.status}`);
            }
            await loadStandar(token);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal menghapus jadwal");
        } finally {
            setDeletingStandarId(null);
        }
    };

    const handleSaveOverride = async () => {
        if (!token) return;
        if (!formOverride.jam_masuk || !formOverride.jam_pulang) {
            setError("Jam masuk dan jam pulang wajib diisi.");
            return;
        }
        setSavingOverride(true);
        try {
            const url = editingOverrideId
                ? `${API_BASE}/jadwal/override/${editingOverrideId}`
                : `${API_BASE}/jadwal/override`;
            const res = await fetch(url, {
                method: editingOverrideId ? "PUT" : "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({
                    tanggal: formOverride.tanggal,
                    kelas: formOverride.kelas || null,
                    jam_masuk: formOverride.jam_masuk,
                    jam_pulang: formOverride.jam_pulang,
                    alasan: formOverride.alasan || null,
                }),
            });
            if (!res.ok) {
                const body = await res.json().catch(() => null);
                throw new Error(body?.detail ?? `HTTP ${res.status}`);
            }
            setModalOverrideOpen(false);
            setEditingOverrideId(null);
            setFormOverride({
                tanggal: new Date().toISOString().split("T")[0],
                kelas: "",
                jam_masuk: "",
                jam_pulang: "",
                alasan: "",
            });
            await loadOverride(token);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal menyimpan override");
        } finally {
            setSavingOverride(false);
        }
    };

    const openCreateOverride = () => {
        setEditingOverrideId(null);
        setFormOverride({
            tanggal: new Date().toISOString().split("T")[0],
            kelas: "",
            jam_masuk: "",
            jam_pulang: "",
            alasan: "",
        });
        setModalOverrideOpen(true);
    };

    const openEditOverride = (o: JadwalOverride) => {
        setEditingOverrideId(o.id);
        setFormOverride({
            tanggal: o.tanggal,
            kelas: o.kelas ?? "",
            jam_masuk: o.jam_masuk ?? "",
            jam_pulang: o.jam_pulang ?? "",
            alasan: o.alasan ?? "",
        });
        setModalOverrideOpen(true);
    };

    const handleDeleteOverride = async (id: number) => {
        if (!token) return;
        if (!window.confirm("Hapus jadwal override ini?")) return;
        setDeletingOverrideId(id);
        try {
            const res = await fetch(`${API_BASE}/jadwal/override/${id}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) {
                const body = await res.json().catch(() => null);
                throw new Error(body?.detail ?? `HTTP ${res.status}`);
            }
            await loadOverride(token);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal menghapus");
        } finally {
            setDeletingOverrideId(null);
        }
    };

    // Baris pada scope yang sedang dipilih (umum = kelas_id null, atau kelas tertentu)
    const getStandarForHari = (hari: string): JadwalStandar | undefined => {
        return jadwalStandar.find(j => j.hari === hari && (j.kelas_id ?? null) === standarScope);
    };
    // Baris umum (dipakai sebagai "warisan" saat scope kelas belum punya baris sendiri)
    const getUmumForHari = (hari: string): JadwalStandar | undefined => {
        return jadwalStandar.find(j => j.hari === hari && j.kelas_id == null);
    };

    if (loading) return (
        <div className="space-y-4">
            <Skeleton className="h-8 w-48 mb-6" />
            <Skeleton className="h-48 w-full mb-4" />
            <Skeleton className="h-48 w-full" />
        </div>
    );

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-slate-900">Manajemen Jadwal</h1>
                <p className="text-sm text-slate-500">Atur jam masuk & pulang standar sekolah</p>
            </div>

            {error && (
                <div className="p-3 bg-rose-50 text-rose-700 rounded-lg border border-rose-200 text-sm flex justify-between items-center">
                    {error}
                    <button onClick={() => setError(null)} className="underline text-xs">Tutup</button>
                </div>
            )}

            {/* Jadwal Standar */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">Jadwal Standard (Per Hari)</h2>
                        <p className="text-xs text-slate-500 mt-1">
                            {standarScope == null
                                ? "Berlaku untuk semua kelas kecuali ada jadwal khusus kelas / override per tanggal"
                                : "Jadwal khusus kelas ini — menimpa jadwal umum. Hari tanpa baris sendiri tetap ikut jadwal umum."}
                        </p>
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Berlaku untuk</label>
                        <select
                            value={standarScope ?? ""}
                            onChange={(e) => { setStandarScope(e.target.value ? Number(e.target.value) : null); setEditingStandar(null); }}
                            className="border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
                        >
                            <option value="">Umum (semua kelas)</option>
                            {kelasOptions.map((k) => <option key={k.id} value={k.id}>{k.nama}</option>)}
                        </select>
                    </div>
                </div>
                <table className="min-w-full text-sm">
                    <thead>
                        <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                            <th className="py-3 px-6 text-left w-32">Hari</th>
                            <th className="py-3 px-6 text-left">Jam Masuk</th>
                            <th className="py-3 px-6 text-left">Jam Pulang</th>
                            <th className="py-3 px-6 text-left">Jam Efektif (Durasi)</th>
                            <th className="py-3 px-6 text-center w-32">Aksi</th>
                        </tr>
                    </thead>
                    <tbody>
                        {HARI_LIST.map((hari) => {
                            const standar = getStandarForHari(hari);
                            const umum = getUmumForHari(hari);
                            const defaultVal = JADWAL_DEFAULT[hari];
                            const isEditing = editingStandar === hari;
                            // scope kelas tanpa baris sendiri → tampilkan (dan warisi) nilai umum
                            const warisan = standarScope != null && !standar;
                            const jamMasuk = standar?.jam_masuk || umum?.jam_masuk || defaultVal.masuk;
                            const jamPulang = standar?.jam_pulang || umum?.jam_pulang || defaultVal.pulang;

                            // Hitung jam efektif / durasi
                            const [mH, mM] = jamMasuk.split(":").map(Number);
                            const [pH, pM] = jamPulang.split(":").map(Number);
                            const totalMenit = (pH * 60 + pM) - (mH * 60 + mM);
                            const durasiJam = Math.floor(totalMenit / 60);
                            const durasiMenit = totalMenit % 60;
                            const teksDurasi = totalMenit > 0 ? `${durasiJam} jam ${durasiMenit > 0 ? `${durasiMenit} menit` : ""}` : "-";

                            return (
                                <tr key={hari} className="border-b border-slate-100 hover:bg-slate-50 transition">
                                    <td className="py-3 px-6 font-medium text-slate-800">
                                        {HARI_LABELS[hari]}
                                        {warisan && <span className="ml-2 text-xs font-normal text-slate-400">ikut umum</span>}
                                    </td>
                                    <td className="py-3 px-6">
                                        {isEditing ? (
                                            <input
                                                type="time"
                                                value={formStandar.jam_masuk}
                                                onChange={(e) => setFormStandar({ ...formStandar, jam_masuk: e.target.value })}
                                                className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500"
                                            />
                                        ) : (
                                            <span className={`font-mono ${warisan ? "text-slate-400" : "text-slate-700"}`}>{jamMasuk}</span>
                                        )}
                                    </td>
                                    <td className="py-3 px-6">
                                        {isEditing ? (
                                            <input
                                                type="time"
                                                value={formStandar.jam_pulang}
                                                onChange={(e) => setFormStandar({ ...formStandar, jam_pulang: e.target.value })}
                                                className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500"
                                            />
                                        ) : (
                                            <span className={`font-mono ${warisan ? "text-slate-400" : "text-slate-700"}`}>{jamPulang}</span>
                                        )}
                                    </td>
                                    <td className="py-3 px-6">
                                        <Badge variant="success">{teksDurasi}</Badge>
                                    </td>
                                    <td className="py-3 px-6 text-center">
                                        {isEditing ? (
                                            <div className="flex justify-center gap-2">
                                                <Button
                                                    onClick={() => handleSaveStandar(hari)}
                                                    isLoading={savingStandar}
                                                    className="text-xs px-3 py-1"
                                                >
                                                    Simpan
                                                </Button>
                                                <Button
                                                    onClick={() => setEditingStandar(null)}
                                                    variant="ghost"
                                                    className="text-xs px-3 py-1"
                                                >
                                                    Batal
                                                </Button>
                                            </div>
                                        ) : (
                                            <div className="flex justify-center gap-2">
                                                <Button
                                                    onClick={() => {
                                                        setEditingStandar(hari);
                                                        setFormStandar({ jam_masuk: jamMasuk, jam_pulang: jamPulang });
                                                    }}
                                                    variant="secondary"
                                                    className="text-xs px-3 py-1"
                                                >
                                                    {warisan ? "Atur khusus" : "Edit"}
                                                </Button>
                                                {standar && standarScope != null && (
                                                    <Button
                                                        onClick={() => handleDeleteStandar(standar.id!)}
                                                        variant="danger"
                                                        isLoading={deletingStandarId === standar.id}
                                                        className="text-xs px-3 py-1"
                                                    >
                                                        {deletingStandarId === standar.id ? "" : "Hapus"}
                                                    </Button>
                                                )}
                                            </div>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* Jadwal Override */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">Jadwal Override (Per Tanggal)</h2>
                        <p className="text-xs text-slate-500 mt-1">Untuk hari libur, ujian, upacara, atau kondisi khusus</p>
                    </div>
                    <Button onClick={openCreateOverride}>+ Tambah Override</Button>
                </div>

                {jadwalOverride.length === 0 ? (
                    <div className="py-8 text-center text-slate-500">
                        <p className="font-medium">Belum ada jadwal override</p>
                        <p className="text-xs mt-1">Klik "+ Tambah Override" untuk jadwal khusus</p>
                    </div>
                ) : (
                    <table className="min-w-full text-sm">
                        <thead>
                            <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                                <th className="py-3 px-6 text-left">Tanggal</th>
                                <th className="py-3 px-6 text-left">Kelas</th>
                                <th className="py-3 px-6 text-left">Jam Masuk</th>
                                <th className="py-3 px-6 text-left">Jam Pulang</th>
                                <th className="py-3 px-6 text-left">Jam Efektif (Durasi)</th>
                                <th className="py-3 px-6 text-left">Alasan</th>
                                <th className="py-3 px-6 text-center w-24">Aksi</th>
                            </tr>
                        </thead>
                        <tbody>
                            {jadwalOverride.map((o) => {
                                const durasiOverride = (o.jam_masuk && o.jam_pulang)
                                    ? (() => {
                                        const [mH, mM] = o.jam_masuk.split(":").map(Number);
                                        const [pH, pM] = o.jam_pulang.split(":").map(Number);
                                        const totalMenit = (pH * 60 + pM) - (mH * 60 + mM);
                                        const dj = Math.floor(totalMenit / 60);
                                        const dm = totalMenit % 60;
                                        return totalMenit > 0 ? `${dj} jam ${dm > 0 ? `${dm} menit` : ""}` : "-";
                                    })()
                                    : "-";
                                return (
                                    <tr key={o.id} className="border-b border-slate-100 hover:bg-slate-50 transition">
                                        <td className="py-3 px-6 font-medium text-slate-800">{o.tanggal}</td>
                                        <td className="py-3 px-6 text-slate-600">{o.kelas || "Semua Kelas"}</td>
                                        <td className="py-3 px-6 font-mono text-slate-700">{o.jam_masuk || "-"}</td>
                                        <td className="py-3 px-6 font-mono text-slate-700">{o.jam_pulang || "-"}</td>
                                        <td className="py-3 px-6">
                                            <Badge variant="success">{durasiOverride}</Badge>
                                        </td>
                                        <td className="py-3 px-6 text-slate-600">{o.alasan || "-"}</td>
                                        <td className="py-3 px-6 text-center whitespace-nowrap">
                                            <div className="flex justify-center gap-2">
                                                <Button
                                                    onClick={() => openEditOverride(o)}
                                                    variant="secondary"
                                                    className="text-xs px-2 py-1"
                                                >
                                                    Edit
                                                </Button>
                                                <Button
                                                    onClick={() => handleDeleteOverride(o.id)}
                                                    disabled={deletingOverrideId === o.id}
                                                    variant="danger"
                                                    isLoading={deletingOverrideId === o.id}
                                                    className="text-xs px-2 py-1"
                                                >
                                                    {deletingOverrideId === o.id ? "" : "Hapus"}
                                                </Button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Modal Tambah Override */}
            {modalOverrideOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 border border-slate-200">
                        <h3 className="text-xl font-bold mb-4 text-slate-900">
                            {editingOverrideId ? "Edit Jadwal Override" : "Tambah Jadwal Override"}
                        </h3>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Tanggal</label>
                                <input
                                    type="date"
                                    value={formOverride.tanggal}
                                    onChange={(e) => setFormOverride({ ...formOverride, tanggal: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Kelas (opsional)</label>
                                <input
                                    type="text"
                                    list="override-kelas-list"
                                    value={formOverride.kelas}
                                    onChange={(e) => setFormOverride({ ...formOverride, kelas: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    placeholder="Kosongkan untuk semua kelas"
                                />
                                <datalist id="override-kelas-list">
                                    {kelasOptions.map((k) => <option key={k.id} value={k.nama} />)}
                                </datalist>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Jam Masuk</label>
                                    <input
                                        type="time"
                                        value={formOverride.jam_masuk}
                                        onChange={(e) => setFormOverride({ ...formOverride, jam_masuk: e.target.value })}
                                        className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Jam Pulang</label>
                                    <input
                                        type="time"
                                        value={formOverride.jam_pulang}
                                        onChange={(e) => setFormOverride({ ...formOverride, jam_pulang: e.target.value })}
                                        className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Alasan</label>
                                <textarea
                                    value={formOverride.alasan}
                                    onChange={(e) => setFormOverride({ ...formOverride, alasan: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    rows={2}
                                    placeholder="Upacara, ujian, dll."
                                />
                            </div>
                        </div>

                        <div className="mt-6 flex justify-end space-x-3">
                            <Button variant="ghost" onClick={() => { setModalOverrideOpen(false); setEditingOverrideId(null); }} disabled={savingOverride}>Batal</Button>
                            <Button onClick={handleSaveOverride} isLoading={savingOverride}>
                                {savingOverride ? "Menyimpan..." : editingOverrideId ? "Simpan Perubahan" : "Simpan"}
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}