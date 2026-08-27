"use client";

import { useState, useEffect, useCallback } from "react";
import { Button, Badge, Skeleton } from "@/components/ui/Base";

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

const ROLE_LABELS: Record<string, string> = {
    admin: "Admin",
    guru_piket: "Guru Piket",
    wali_kelas: "Wali Kelas",
    kepala_sekolah: "Kepala Sekolah",
};

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
            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("token");
                window.location.href = "/login";
                return;
            }
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

    if (loading) return (
        <div className="space-y-4">
            <Skeleton className="h-8 w-48 mb-6" />
            <Skeleton className="h-12 w-full mb-2" />
            <Skeleton className="h-12 w-full mb-2" />
            <Skeleton className="h-12 w-full" />
        </div>
    );

    if (error) {
        return (
            <div className="bg-rose-50 border border-rose-200 rounded-xl p-6 text-center">
                <h3 className="font-bold text-rose-700">Gagal memuat data guru</h3>
                <p className="text-rose-600 text-sm mt-1">{error}</p>
                <div className="mt-4 flex justify-center gap-3">
                    <Button onClick={() => window.location.reload()} variant="secondary">Coba Lagi</Button>
                    <a href="/login"><Button variant="ghost">Ke Halaman Login</Button></a>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Manajemen Guru</h1>
                    <p className="text-sm text-slate-500">Daftar guru & pengelolaan akun</p>
                </div>
                <Button onClick={openCreate}>+ Tambah Guru</Button>
            </div>

            {error && (
                <div className="p-3 bg-rose-50 text-rose-700 rounded-lg border border-rose-200 text-sm">{error}</div>
            )}

            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <table className="min-w-full text-sm">
                    <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                            <th className="py-3 px-4 text-left">Nama</th>
                            <th className="py-3 px-4 text-left">Email</th>
                            <th className="py-3 px-4 text-left">Role</th>
                            <th className="py-3 px-4 text-left">Kelas Diampu</th>
                            <th className="py-3 px-4 text-left">Status</th>
                            <th className="py-3 px-4 text-center">Aksi</th>
                        </tr>
                    </thead>
                    <tbody>
                        {guruList.length === 0 ? (
                            <tr>
                                <td colSpan={6} className="py-8 text-center text-slate-500">
                                    <p className="font-medium">Belum ada data guru</p>
                                    <p className="text-xs mt-1">Klik "+ Tambah Guru" untuk menambah data baru</p>
                                </td>
                            </tr>
                        ) : (
                            guruList.map((guru) => (
                                <tr key={guru.id} className={`border-b border-slate-100 hover:bg-slate-50 transition ${!guru.aktif ? "opacity-50" : ""}`}>
                                    <td className="py-3 px-4 font-medium text-slate-800">{guru.nama}</td>
                                    <td className="py-3 px-4 text-slate-600">{guru.email}</td>
                                    <td className="py-3 px-4 text-slate-600">{ROLE_LABELS[guru.role] || guru.role}</td>
                                    <td className="py-3 px-4 text-slate-600">{guru.kelas_diampu ?? "-"}</td>
                                    <td className="py-3 px-4">
                                        <Badge variant={guru.aktif ? "success" : "danger"}>
                                            {guru.aktif ? "Aktif" : "Nonaktif"}
                                        </Badge>
                                    </td>
                                    <td className="py-3 px-4 text-center space-x-2 whitespace-nowrap">
                                        <Button onClick={() => openEdit(guru)} variant="secondary" className="text-xs px-2 py-1">Edit</Button>
                                        <Button
                                            onClick={() => handleDelete(guru.id, guru.nama)}
                                            disabled={deletingId === guru.id}
                                            variant="danger"
                                            isLoading={deletingId === guru.id}
                                            className="text-xs px-2 py-1"
                                        >
                                            {deletingId === guru.id ? "" : "Hapus"}
                                        </Button>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {/* Modal Tambah/Edit */}
            {modalOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 border border-slate-200">
                        <h3 className="text-xl font-bold mb-4 text-slate-900">
                            {editingId ? "Edit Guru" : "Tambah Guru"}
                        </h3>

                        {formError && (
                            <div className="mb-4 p-3 bg-rose-50 text-rose-700 rounded-lg border border-rose-200 text-sm">
                                {formError}
                            </div>
                        )}

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Nama</label>
                                <input
                                    type="text"
                                    value={form.nama}
                                    onChange={(e) => setForm({ ...form, nama: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    placeholder="Nama lengkap"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
                                <input
                                    type="email"
                                    value={form.email}
                                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    placeholder="nama@guru.smk.belajar.id"
                                    disabled={!!editingId}
                                />
                                {editingId && (
                                    <p className="text-xs text-slate-500 mt-1">
                                        Email tidak dapat diubah saat edit.
                                    </p>
                                )}
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Role</label>
                                <select
                                    value={form.role}
                                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                >
                                    {ROLES.map((r) => (
                                        <option key={r} value={r}>
                                            {ROLE_LABELS[r]}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">
                                    Kelas Diampu (opsional)
                                </label>
                                <input
                                    type="text"
                                    value={form.kelas_diampu}
                                    onChange={(e) => setForm({ ...form, kelas_diampu: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    placeholder="cth: XII RPL 1"
                                />
                            </div>

                            <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={form.aktif}
                                    onChange={(e) => setForm({ ...form, aktif: e.target.checked })}
                                    className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                                />
                                <span className="text-sm text-slate-700">Akun aktif</span>
                            </label>
                        </div>

                        <div className="mt-6 flex justify-end space-x-3">
                            <Button variant="ghost" onClick={() => setModalOpen(false)} disabled={saving}>Batal</Button>
                            <Button onClick={handleSave} isLoading={saving}>
                                {saving ? "Menyimpan..." : editingId ? "Simpan Perubahan" : "Tambah"}
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
