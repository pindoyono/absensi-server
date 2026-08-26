"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface Guru {
    id: number;
    nama: string;
    email: string;
    role: string;
    kelas_diampu: string | null;
    aktif: boolean;
}

const ROLES = ["admin", "guru_piket", "wali_kelas", "kepala_sekolah"] as const;

const emptyForm = {
    nama: "",
    email: "",
    role: "guru_piket",
    kelas_diampu: "",
    aktif: true,
};

export default function GuruPage() {
    const [guruList, setGuruList] = useState<Guru[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [token, setToken] = useState<string | null>(null);

    // Modal state
    const [modalOpen, setModalOpen] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form, setForm] = useState({ ...emptyForm });
    const [saving, setSaving] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);
    const [deletingId, setDeletingId] = useState<number | null>(null);

    const loadGuru = useCallback(async (t: string) => {
        try {
            const res = await fetch(`${API_BASE}/guru`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setGuruList(Array.isArray(data) ? data : []);
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
        loadGuru(t);
    }, [loadGuru]);

    const openCreate = () => {
        setEditingId(null);
        setForm({ ...emptyForm });
        setFormError(null);
        setModalOpen(true);
    };

    const openEdit = (guru: Guru) => {
        setEditingId(guru.id);
        setForm({
            nama: guru.nama,
            email: guru.email,
            role: guru.role,
            kelas_diampu: guru.kelas_diampu ?? "",
            aktif: guru.aktif,
        });
        setFormError(null);
        setModalOpen(true);
    };

    const handleSave = async () => {
        if (!token) return;
        if (!form.nama.trim() || !form.email.trim()) {
            setFormError("Nama dan email wajib diisi.");
            return;
        }
        setSaving(true);
        setFormError(null);
        try {
            const payload = {
                nama: form.nama.trim(),
                email: form.email.trim(),
                role: form.role,
                kelas_diampu: form.kelas_diampu.trim() || null,
                aktif: form.aktif,
            };
            const url = editingId
                ? `${API_BASE}/guru/${editingId}`
                : `${API_BASE}/guru`;
            const res = await fetch(url, {
                method: editingId ? "PUT" : "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify(payload),
            });
            const body = await res.json().catch(() => null);
            if (!res.ok) {
                throw new Error(body?.detail ?? `HTTP ${res.status}`);
            }
            setModalOpen(false);
            await loadGuru(token);
        } catch (err) {
            setFormError(err instanceof Error ? err.message : "Gagal menyimpan");
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (id: number, nama: string) => {
        if (!token) return;
        if (!window.confirm(`Nonaktifkan akun "${nama}"?`)) return;
        setDeletingId(id);
        try {
            const res = await fetch(`${API_BASE}/guru/${id}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });
            const body = await res.json().catch(() => null);
            if (!res.ok) {
                throw new Error(body?.detail ?? `HTTP ${res.status}`);
            }
            await loadGuru(token);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal menghapus");
        } finally {
            setDeletingId(null);
        }
    };

    if (loading) return <div className="p-4 text-white">Loading...</div>;

    if (error) {
        return (
            <div className="p-4 bg-red-800 text-white rounded">
                <h3 className="font-bold">Gagal memuat data guru</h3>
                <p>{error}</p>
                <div className="mt-4 space-x-4">
                    <button
                        onClick={() => window.location.reload()}
                        className="bg-white text-red-800 px-4 py-2 rounded font-bold hover:bg-gray-200"
                    >
                        Coba Lagi
                    </button>
                    <a
                        href="/login"
                        className="inline-block bg-blue-600 text-white px-4 py-2 rounded font-bold hover:bg-blue-700"
                    >
                        Ke Halaman Login
                    </a>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-white p-6 rounded shadow text-gray-800">
            <div className="flex justify-between items-center mb-4">
                <h2 className="text-2xl font-bold">Manajemen Guru</h2>
                <button
                    onClick={openCreate}
                    className="bg-blue-600 text-white px-4 py-2 rounded font-semibold hover:bg-blue-700"
                >
                    + Tambah Guru
                </button>
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">{error}</div>
            )}

            <table className="min-w-full bg-white border">
                <thead>
                    <tr className="bg-gray-100">
                        <th className="py-2 px-4 border-b text-left">Nama</th>
                        <th className="py-2 px-4 border-b text-left">Email</th>
                        <th className="py-2 px-4 border-b text-left">Role</th>
                        <th className="py-2 px-4 border-b text-left">Kelas Diampu</th>
                        <th className="py-2 px-4 border-b text-left">Status</th>
                        <th className="py-2 px-4 border-b text-center">Aksi</th>
                    </tr>
                </thead>
                <tbody>
                    {guruList.length === 0 ? (
                        <tr>
                            <td colSpan={6} className="py-4 text-center text-gray-500">Belum ada data guru.</td>
                        </tr>
                    ) : (
                        guruList.map((guru) => (
                            <tr key={guru.id} className={`border-b ${!guru.aktif ? "opacity-50" : ""}`}>
                                <td className="py-2 px-4">{guru.nama}</td>
                                <td className="py-2 px-4">{guru.email}</td>
                                <td className="py-2 px-4">{guru.role}</td>
                                <td className="py-2 px-4">{guru.kelas_diampu ?? "-"}</td>
                                <td className="py-2 px-4">
                                    <span
                                        className={`px-2 py-1 rounded text-xs font-semibold ${guru.aktif
                                                ? "bg-green-100 text-green-700"
                                                : "bg-red-100 text-red-700"
                                            }`}
                                    >
                                        {guru.aktif ? "Aktif" : "Nonaktif"}
                                    </span>
                                </td>
                                <td className="py-2 px-4 text-center space-x-2 whitespace-nowrap">
                                    <button
                                        onClick={() => openEdit(guru)}
                                        className="bg-yellow-500 text-white px-3 py-1 rounded text-sm hover:bg-yellow-600"
                                    >
                                        Edit
                                    </button>
                                    <button
                                        onClick={() => handleDelete(guru.id, guru.nama)}
                                        disabled={deletingId === guru.id}
                                        className="bg-red-600 text-white px-3 py-1 rounded text-sm hover:bg-red-700 disabled:opacity-50"
                                    >
                                        {deletingId === guru.id ? "..." : "Hapus"}
                                    </button>
                                </td>
                            </tr>
                        ))
                    )}
                </tbody>
            </table>

            {/* Modal Tambah/Edit */}
            {modalOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
                        <h3 className="text-xl font-bold mb-4">
                            {editingId ? "Edit Guru" : "Tambah Guru"}
                        </h3>

                        {formError && (
                            <div className="mb-4 p-3 bg-red-100 text-red-700 rounded text-sm">
                                {formError}
                            </div>
                        )}

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">Nama</label>
                                <input
                                    type="text"
                                    value={form.nama}
                                    onChange={(e) => setForm({ ...form, nama: e.target.value })}
                                    className="w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="Nama lengkap"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium mb-1">Email</label>
                                <input
                                    type="email"
                                    value={form.email}
                                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                                    className="w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="nama@guru.smk.belajar.id"
                                    disabled={!!editingId}
                                />
                                {editingId && (
                                    <p className="text-xs text-gray-500 mt-1">
                                        Email tidak dapat diubah saat edit.
                                    </p>
                                )}
                            </div>

                            <div>
                                <label className="block text-sm font-medium mb-1">Role</label>
                                <select
                                    value={form.role}
                                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                                    className="w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                >
                                    {ROLES.map((r) => (
                                        <option key={r} value={r}>
                                            {r.replace(/_/g, " ")}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium mb-1">
                                    Kelas Diampu (opsional)
                                </label>
                                <input
                                    type="text"
                                    value={form.kelas_diampu}
                                    onChange={(e) =>
                                        setForm({ ...form, kelas_diampu: e.target.value })
                                    }
                                    className="w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="cth: XII RPL 1"
                                />
                            </div>

                            <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={form.aktif}
                                    onChange={(e) => setForm({ ...form, aktif: e.target.checked })}
                                    className="w-4 h-4"
                                />
                                <span className="text-sm">Akun aktif</span>
                            </label>
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
                                {saving ? "Menyimpan..." : editingId ? "Simpan Perubahan" : "Tambah"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
