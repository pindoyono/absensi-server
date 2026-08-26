"use client";

import { useState, useEffect, useCallback } from "react";
import { format, startOfWeek, addDays } from "date-fns";

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

    if (loading) return <div className="p-4 text-white">Loading...</div>;

    if (error && dispensasiList.length === 0) {
        return (
            <div className="p-4 bg-red-800 text-white rounded">
                <h3 className="font-bold">Gagal memuat data</h3>
                <p>{error}</p>
                <button
                    onClick={() => window.location.reload()}
                    className="mt-4 bg-white text-red-800 px-4 py-2 rounded font-bold hover:bg-gray-200"
                >
                    Coba Lagi
                </button>
            </div>
        );
    }

    return (
        <div className="bg-white p-6 rounded shadow text-gray-800">
            <div className="flex justify-between items-center mb-4">
                <h2 className="text-2xl font-bold">Manajemen Dispensasi</h2>
                <button
                    onClick={openCreate}
                    className="bg-blue-600 text-white px-4 py-2 rounded font-semibold hover:bg-blue-700"
                >
                    + Buat Dispensasi
                </button>
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">{error}</div>
            )}

            <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Tanggal</label>
                <input
                    type="date"
                    value={selectedDate}
                    onChange={(e) => setSelectedDate(e.target.value)}
                    className="border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
            </div>

            <table className="min-w-full bg-white border">
                <thead>
                    <tr className="bg-gray-100">
                        <th className="py-2 px-4 border-b text-left">Siswa</th>
                        <th className="py-2 px-4 border-b text-left">Kelas</th>
                        <th className="py-2 px-4 border-b text-left">Kategori</th>
                        <th className="py-2 px-4 border-b text-left">Alasan</th>
                        <th className="py-2 px-4 border-b text-center">Aksi</th>
                    </tr>
                </thead>
                <tbody>
                    {dispensasiList.length === 0 ? (
                        <tr>
                            <td colSpan={5} className="py-4 text-center text-gray-500">
                                Tidak ada dispensasi untuk tanggal ini.
                            </td>
                        </tr>
                    ) : (
                        dispensasiList.map((d) => {
                            const kat = KATEGORI_OPTIONS.find(k => k.value === d.kategori);
                            return (
                                <tr key={d.id} className="border-b">
                                    <td className="py-2 px-4">{getSiswaName(d.siswa_id)}</td>
                                    <td className="py-2 px-4">
                                        {siswaList.find(o => o.value === d.siswa_id)?.label.split(" (")[1]?.replace(")", "") || "-"}
                                    </td>
                                    <td className="py-2 px-4">
                                        <span className={`px-2 py-1 rounded text-xs font-semibold ${kat?.color || "bg-gray-100 text-gray-700"}`}>
                                            {kat?.label || d.kategori}
                                        </span>
                                    </td>
                                    <td className="py-2 px-4">{d.alasan || "-"}</td>
                                    <td className="py-2 px-4 text-center">
                                        <button
                                            onClick={() => handleDelete(d.id, getSiswaName(d.siswa_id))}
                                            disabled={deletingId === d.id}
                                            className="bg-red-600 text-white px-3 py-1 rounded text-sm hover:bg-red-700 disabled:opacity-50"
                                        >
                                            {deletingId === d.id ? "..." : "Hapus"}
                                        </button>
                                    </td>
                                </tr>
                            );
                        })
                    )}
                </tbody>
            </table>

            {/* Modal Tambah/Edit */}
            {modalOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
                        <h3 className="text-xl font-bold mb-4">
                            {editingId ? "Edit Dispensasi" : "Buat Dispensasi"}
                        </h3>

                        {formError && (
                            <div className="mb-4 p-3 bg-red-100 text-red-700 rounded text-sm">
                                {formError}
                            </div>
                        )}

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">Siswa</label>
                                <select
                                    value={form.siswa_id}
                                    onChange={(e) => setForm({ ...form, siswa_id: parseInt(e.target.value) })}
                                    className="w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                                <label className="block text-sm font-medium mb-1">Tanggal</label>
                                <input
                                    type="date"
                                    value={form.tanggal}
                                    onChange={(e) => setForm({ ...form, tanggal: e.target.value })}
                                    className="w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium mb-1">Kategori</label>
                                <select
                                    value={form.kategori}
                                    onChange={(e) => setForm({ ...form, kategori: e.target.value as any })}
                                    className="w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                >
                                    {KATEGORI_OPTIONS.map((k) => (
                                        <option key={k.value} value={k.value}>
                                            {k.label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium mb-1">Alasan</label>
                                <textarea
                                    value={form.alasan}
                                    onChange={(e) => setForm({ ...form, alasan: e.target.value })}
                                    className="w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    rows={3}
                                    placeholder="Misal: Sakit, kegiatan scholastic, dll..."
                                />
                            </div>
                        </div>

                        <div className="mt-6 flex justify-end space-x-3">
                            <button
                                onClick={() => setModalOpen(false)}
                                className="px-4 py-2 rounded border text-gray-700 hover:bg-gray-100"
                                disabled={saving}
                            >
                                Batal
                            </button>
                            <button
                                onClick={handleSave}
                                disabled={saving}
                                className="bg-blue-600 text-white px-4 py-2 rounded font-semibold hover:bg-blue-700 disabled:opacity-50"
                            >
                                {saving ? "Menyimpan..." : editingId ? "Simpan" : "Buat"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}