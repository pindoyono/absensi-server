"use client";

import { useState, useEffect, useCallback } from "react";
import { format } from "date-fns";
import { Button, Badge, Skeleton } from "@/components/ui/Base";

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface Siswa {
    id: number;
    nis: string;
    nama: string;
    kelas: string;
}

interface Dispensasi {
    id: number;
    siswa_id: number;
    tanggal: string;
    jenis: string;
    kategori: string;
    alasan: string | null;
    dibuat_oleh: number;
}

interface SiswaOption {
    value: number;
    label: string;
}

const KATEGORI_OPTIONS = [
    { value: "IZIN", label: "IZIN", color: "bg-blue-100 text-blue-700" },
    { value: "SAKIT", label: "SAKIT", color: "bg-red-100 text-red-700" },
    { value: "DISPENSASI_KEGIATAN", label: "DISPENSASI KEGIATAN", color: "bg-green-100 text-green-700" },
    { value: "LAINNYA", label: "LAINNYA", color: "bg-gray-100 text-gray-700" },
];

const emptyForm = {
    siswa_id: 0,
    tanggal: format(new Date(), "yyyy-MM-dd"),
    jenis: "PULANG_CEPAT" as const,
    kategori: "IZIN" as const,
    alasan: "",
};

export default function DispensasiPage() {
    const [token, setToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [siswaList, setSiswaList] = useState<SiswaOption[]>([]);
    const [dispensasiList, setDispensasiList] = useState<Dispensasi[]>([]);
    const [selectedDate, setSelectedDate] = useState<string>(format(new Date(), "yyyy-MM-dd"));

    const [modalOpen, setModalOpen] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form, setForm] = useState({ ...emptyForm });
    const [saving, setSaving] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);
    const [deletingId, setDeletingId] = useState<number | null>(null);

    const loadSiswa = useCallback(async (t: string) => {
        try {
            const res = await fetch(`${API_BASE}/siswa?enrolled=true`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (!res.ok) throw new Error("Gagal memuat daftar siswa");
            const data = await res.json();
            const options = data.map((s: Siswa) => ({
                value: s.id,
                label: `${s.nis} - ${s.nama} (${s.kelas})`,
            }));
            setSiswaList(options);
        } catch (err) {
            console.error(err);
        }
    }, []);

    const loadDispensasi = useCallback(async (t: string, tanggal: string) => {
        try {
            const res = await fetch(`${API_BASE}/dispensasi/aktif?tanggal=${tanggal}`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("token");
                window.location.href = "/login";
                return;
            }
            if (!res.ok) throw new Error("Gagal memuat dispensasi");
            const data = await res.json();
            setDispensasiList(data);
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
        loadSiswa(t);
        loadDispensasi(t, selectedDate);
    }, [selectedDate, loadSiswa, loadDispensasi]);

    const openCreate = () => {
        setEditingId(null);
        setForm({ ...emptyForm, tanggal: selectedDate });
        setFormError(null);
        setModalOpen(true);
    };

    const openEdit = (d: Dispensasi) => {
        setEditingId(d.id);
        setForm({
            siswa_id: d.siswa_id,
            tanggal: d.tanggal,
            jenis: d.jenis as "PULANG_CEPAT",
            kategori: d.kategori as any,
            alasan: d.alasan ?? "",
        });
        setFormError(null);
        setModalOpen(true);
    };

    const handleSave = async () => {
        if (!token) return;
        if (!form.siswa_id) {
            setFormError("Siswa harus dipilih.");
            return;
        }
        setSaving(true);
        setFormError(null);
        try {
            const payload = {
                siswa_id: form.siswa_id,
                tanggal: form.tanggal,
                jenis: form.jenis,
                kategori: form.kategori,
                alasan: form.alasan.trim() || null,
            };
            const res = await fetch(`${API_BASE}/dispensasi`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const body = await res.json().catch(() => null);
                throw new Error(body?.detail ?? `HTTP ${res.status}`);
            }
            setModalOpen(false);
            loadDispensasi(token, selectedDate);
        } catch (err) {
            setFormError(err instanceof Error ? err.message : "Gagal menyimpan");
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (id: number, nama: string) => {
        if (!token) return;
        if (!window.confirm(`Batalkan dispensasi untuk "${nama}"?`)) return;
        setDeletingId(id);
        try {
            const res = await fetch(`${API_BASE}/dispensasi/${id}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) {
                const body = await res.json().catch(() => null);
                throw new Error(body?.detail ?? `HTTP ${res.status}`);
            }
            loadDispensasi(token, selectedDate);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal menghapus");
        } finally {
            setDeletingId(null);
        }
    };

    const getSiswaName = (siswa_id: number) => {
        const s = siswaList.find(o => o.value === siswa_id);
        return s ? s.label.split(" - ")[1] : "Siswa";
    };

    if (loading) return (
        <div className="space-y-4">
            <Skeleton className="h-8 w-48 mb-6" />
            <Skeleton className="h-12 w-full mb-2" />
            <Skeleton className="h-12 w-full mb-2" />
            <Skeleton className="h-12 w-full" />
        </div>
    );

    if (error && dispensasiList.length === 0) {
        return (
            <div className="bg-rose-50 border border-rose-200 rounded-xl p-6 text-center">
                <h3 className="font-bold text-rose-700">Gagal memuat data</h3>
                <p className="text-rose-600 text-sm mt-1">{error}</p>
                <div className="mt-4">
                    <Button onClick={() => window.location.reload()} variant="secondary">Coba Lagi</Button>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Manajemen Dispensasi</h1>
                    <p className="text-sm text-slate-500">Kelola pengajuan izin & dispensasi siswa</p>
                </div>
                <Button onClick={openCreate}>+ Buat Dispensasi</Button>
            </div>

            {error && (
                <div className="p-3 bg-rose-50 text-rose-700 rounded-lg border border-rose-200 text-sm">{error}</div>
            )}

            <div className="flex items-center gap-4">
                <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Tanggal</label>
                    <input
                        type="date"
                        value={selectedDate}
                        onChange={(e) => setSelectedDate(e.target.value)}
                        className="border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    />
                </div>
            </div>

            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <table className="min-w-full text-sm">
                    <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                            <th className="py-3 px-4 text-left">Siswa</th>
                            <th className="py-3 px-4 text-left">Kelas</th>
                            <th className="py-3 px-4 text-left">Kategori</th>
                            <th className="py-3 px-4 text-left">Alasan</th>
                            <th className="py-3 px-4 text-center">Aksi</th>
                        </tr>
                    </thead>
                    <tbody>
                        {dispensasiList.length === 0 ? (
                            <tr>
                                <td colSpan={5} className="py-8 text-center text-slate-500">
                                    <p className="font-medium">Tidak ada dispensasi untuk tanggal ini</p>
                                    <p className="text-xs mt-1">Pilih tanggal lain atau buat dispensasi baru</p>
                                </td>
                            </tr>
                        ) : (
                            dispensasiList.map((d) => {
                                const siswaInfo = siswaList.find(o => o.value === d.siswa_id);
                                const nama = siswaInfo?.label.split(" - ")[1]?.split(" (")[0] || "Siswa";
                                const kelas = siswaInfo?.label.split("(")[1]?.replace(")", "") || "-";
                                const kat = KATEGORI_OPTIONS.find(k => k.value === d.kategori);
                                return (
                                    <tr key={d.id} className="border-b border-slate-100 hover:bg-slate-50 transition">
                                        <td className="py-3 px-4 font-medium text-slate-800">{nama}</td>
                                        <td className="py-3 px-4 text-slate-600">{kelas}</td>
                                        <td className="py-3 px-4">
                                            <Badge variant={kat?.value === "SAKIT" ? "danger" : kat?.value === "DISPENSASI_KEGIATAN" ? "success" : "default"}>
                                                {kat?.label || d.kategori}
                                            </Badge>
                                        </td>
                                        <td className="py-3 px-4 text-slate-600">{d.alasan || "-"}</td>
                                        <td className="py-3 px-4 text-center">
                                            <Button
                                                onClick={() => handleDelete(d.id, nama)}
                                                disabled={deletingId === d.id}
                                                variant="danger"
                                                isLoading={deletingId === d.id}
                                                className="text-xs px-2 py-1"
                                            >
                                                {deletingId === d.id ? "" : "Hapus"}
                                            </Button>
                                        </td>
                                    </tr>
                                );
                            })
                        )}
                    </tbody>
                </table>
            </div>

            {/* Modal Tambah */}
            {modalOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 border border-slate-200">
                        <h3 className="text-xl font-bold mb-4 text-slate-900">
                            Buat Dispensasi
                        </h3>

                        {formError && (
                            <div className="mb-4 p-3 bg-rose-50 text-rose-700 rounded-lg border border-rose-200 text-sm">
                                {formError}
                            </div>
                        )}

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Siswa</label>
                                <select
                                    value={form.siswa_id}
                                    onChange={(e) => setForm({ ...form, siswa_id: parseInt(e.target.value) })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                >
                                    <option value={0}>-- Pilih Siswa --</option>
                                    {siswaList.map((s) => (
                                        <option key={s.value} value={s.value}>
                                            {s.label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Tanggal</label>
                                <input
                                    type="date"
                                    value={form.tanggal}
                                    onChange={(e) => setForm({ ...form, tanggal: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Kategori</label>
                                <select
                                    value={form.kategori}
                                    onChange={(e) => setForm({ ...form, kategori: e.target.value as any })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                >
                                    {KATEGORI_OPTIONS.map((k) => (
                                        <option key={k.value} value={k.value}>
                                            {k.label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Alasan</label>
                                <textarea
                                    value={form.alasan}
                                    onChange={(e) => setForm({ ...form, alasan: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    rows={3}
                                    placeholder="Misal: Sakit, kegiatan sekolah, dll..."
                                />
                            </div>
                        </div>

                        <div className="mt-6 flex justify-end space-x-3">
                            <Button variant="ghost" onClick={() => setModalOpen(false)} disabled={saving}>Batal</Button>
                            <Button onClick={handleSave} isLoading={saving}>
                                {saving ? "Menyimpan..." : "Buat Dispensasi"}
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}