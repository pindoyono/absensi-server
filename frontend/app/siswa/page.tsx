"use client";

import { useState, useEffect, useCallback } from "react";
import { Button, Badge, Skeleton } from "@/components/ui/Base";

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface Siswa {
    id: number;
    nis: string;
    nama: string;
    kelas: string;
    jurusan: string;
    konsentrasi_id: number | null;
    enrolled: boolean;
    tanggal_enrollment: string | null;
}

interface KonsentrasiOption {
    id: number;
    nama: string;
    kode: string;
    program_nama?: string;
    bidang_nama?: string;
}

const emptyForm = {
    nis: "",
    nama: "",
    kelas: "",
    jurusan: "Teknik Elektronika",
    konsentrasi_id: null as number | null,
    konsentrasi_search: "",
};

export default function SiswaPage() {
    const [siswaList, setSiswaList] = useState<Siswa[]>([]);
    const [konsentrasiOptions, setKonsentrasiOptions] = useState<KonsentrasiOption[]>([]);
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

    // Import CSV state
    const [importOpen, setImportOpen] = useState(false);
    const [importFile, setImportFile] = useState<File | null>(null);
    const [importing, setImporting] = useState(false);
    const [importResult, setImportResult] = useState<{ ditambahkan: number; dilewati_sudah_ada: number; baris_error: string[] } | null>(null);
    const [importError, setImportError] = useState<string | null>(null);

    // Filter state
    const [filterKelas, setFilterKelas] = useState<string>("");
    const [filterEnrolled, setFilterEnrolled] = useState<string>("all");

    const loadSiswa = useCallback(async (t: string) => {
        try {
            const params = new URLSearchParams();
            if (filterKelas) params.set("kelas", filterKelas);
            if (filterEnrolled !== "all") params.set("enrolled", filterEnrolled);

            const res = await fetch(`${API_BASE}/siswa?${params.toString()}`, {
                headers: { Authorization: `Bearer ${t}` },
            });
            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("token");
                window.location.href = "/login";
                return;
            }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setSiswaList(Array.isArray(data) ? data : []);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal memuat data");
        } finally {
            setLoading(false);
        }
    }, [filterKelas, filterEnrolled]);

    useEffect(() => {
        const t = localStorage.getItem("token");
        if (!t) {
            setError("Belum login. Silakan login terlebih dahulu.");
            setLoading(false);
            return;
        }
        setToken(t);
        loadSiswa(t);
        // Load konsentrasi options dari API spektrum
        fetch(`${API_BASE}/spektrum/konsentrasi`, {
            headers: { Authorization: `Bearer ${t}` },
        })
            .then(res => res.ok ? res.json() : [])
            .then(data => setKonsentrasiOptions(Array.isArray(data) ? data : []))
            .catch(() => setKonsentrasiOptions([]));
    }, [loadSiswa]);

    const openCreate = () => {
        setEditingId(null);
        setForm({ ...emptyForm });
        setFormError(null);
        setModalOpen(true);
    };

    const openEdit = (siswa: Siswa) => {
        setEditingId(siswa.id);
        const kon = konsentrasiOptions.find(k => k.id === siswa.konsentrasi_id);
        setForm({
            nis: siswa.nis,
            nama: siswa.nama,
            kelas: siswa.kelas,
            jurusan: siswa.jurusan,
            konsentrasi_id: siswa.konsentrasi_id,
            konsentrasi_search: kon ? `${kon.kode} - ${kon.nama}` : siswa.jurusan,
        });
        setFormError(null);
        setModalOpen(true);
    };

    const handleSave = async () => {
        if (!token) return;
        if (!form.nis.trim() || !form.nama.trim() || !form.kelas.trim()) {
            setFormError("NISN, nama, dan kelas wajib diisi.");
            return;
        }
        setSaving(true);
        setFormError(null);
        try {
            const payload = {
                nis: form.nis.trim(),
                nama: form.nama.trim(),
                kelas: form.kelas.trim(),
                jurusan: form.jurusan,
                konsentrasi_id: form.konsentrasi_id,
            };
            const url = editingId
                ? `${API_BASE}/siswa/${editingId}`
                : `${API_BASE}/siswa`;
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
            await loadSiswa(token);
        } catch (err) {
            setFormError(err instanceof Error ? err.message : "Gagal menyimpan");
        } finally {
            setSaving(false);
        }
    };

    const handleDownloadTemplate = async () => {
        if (!token) return;
        try {
            const res = await fetch(`${API_BASE}/siswa/template-csv`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "template_siswa.csv";
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Gagal mengunduh template");
        }
    };

    const handleImport = async () => {
        if (!token || !importFile) return;
        setImporting(true);
        setImportError(null);
        setImportResult(null);
        try {
            const formData = new FormData();
            formData.append("file", importFile);
            const res = await fetch(`${API_BASE}/siswa/import`, {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
                body: formData,
            });
            const body = await res.json().catch(() => null);
            if (!res.ok) {
                throw new Error(body?.detail ?? `HTTP ${res.status}`);
            }
            setImportResult({
                ditambahkan: body.ditambahkan ?? 0,
                dilewati_sudah_ada: body.dilewati_sudah_ada ?? 0,
                baris_error: body.baris_error ?? [],
            });
            await loadSiswa(token);
        } catch (err) {
            setImportError(err instanceof Error ? err.message : "Gagal mengimpor");
        } finally {
            setImporting(false);
        }
    };

    const handleDelete = async (id: number, nama: string) => {
        if (!token) return;
        if (!window.confirm(`Hapus siswa "${nama}"?`)) return;
        setDeletingId(id);
        try {
            const res = await fetch(`${API_BASE}/siswa/${id}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });
            const body = await res.json().catch(() => null);
            if (!res.ok) {
                throw new Error(body?.detail ?? `HTTP ${res.status}`);
            }
            await loadSiswa(token);
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
                <h3 className="font-bold text-rose-700">Gagal memuat data</h3>
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
                    <h1 className="text-2xl font-bold text-slate-900">Manajemen Siswa</h1>
                    <p className="text-sm text-slate-500">Daftar siswa & pengelolaan data</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="ghost" onClick={handleDownloadTemplate}>
                        Download Template
                    </Button>
                    <Button variant="ghost" onClick={() => { setImportOpen(true); setImportResult(null); setImportError(null); setImportFile(null); }}>
                        Import CSV
                    </Button>
                    <Button onClick={openCreate}>+ Tambah Siswa</Button>
                </div>
            </div>

            {/* Filter */}
            <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-end">
                <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Kelas</label>
                    <input
                        type="text"
                        value={filterKelas}
                        onChange={(e) => setFilterKelas(e.target.value)}
                        className="border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm w-40"
                        placeholder="XII RPL 1"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Status Enrolled</label>
                    <select
                        value={filterEnrolled}
                        onChange={(e) => setFilterEnrolled(e.target.value)}
                        className="border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    >
                        <option value="all">Semua</option>
                        <option value="true">Sudah Enrolled</option>
                        <option value="false">Belum Enrolled</option>
                    </select>
                </div>
                <Button variant="ghost" onClick={() => { setFilterKelas(""); setFilterEnrolled("all"); }}>Reset Filter</Button>
            </div>

            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <table className="min-w-full text-sm">
                    <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                            <th className="py-3 px-4 text-left">NISN</th>
                            <th className="py-3 px-4 text-left">Nama</th>
                            <th className="py-3 px-4 text-left">Kelas</th>
                            <th className="py-3 px-4 text-left">Jurusan</th>
                            <th className="py-3 px-4 text-left">Status</th>
                            <th className="py-3 px-4 text-center">Aksi</th>
                        </tr>
                    </thead>
                    <tbody>
                        {siswaList.length === 0 ? (
                            <tr>
                                <td colSpan={6} className="py-8 text-center text-slate-500">
                                    <p className="font-medium">Belum ada data siswa</p>
                                    <p className="text-xs mt-1">Klik "+ Tambah Siswa" untuk menambah data baru</p>
                                </td>
                            </tr>
                        ) : (
                            siswaList.map((siswa) => (
                                <tr key={siswa.id} className="border-b border-slate-100 hover:bg-slate-50 transition">
                                    <td className="py-3 px-4 font-mono text-xs text-slate-600">{siswa.nis}</td>
                                    <td className="py-3 px-4 font-medium text-slate-800">{siswa.nama}</td>
                                    <td className="py-3 px-4 text-slate-600">{siswa.kelas}</td>
                                    <td className="py-3 px-4 text-slate-600">{siswa.jurusan}</td>
                                    <td className="py-3 px-4">
                                        <Badge variant={siswa.enrolled ? "success" : "warning"}>
                                            {siswa.enrolled ? "Teraplikasi" : "Belum Enrolled"}
                                        </Badge>
                                    </td>
                                    <td className="py-3 px-4 text-center space-x-2 whitespace-nowrap">
                                        <Button onClick={() => openEdit(siswa)} variant="secondary" className="text-xs px-2 py-1">Edit</Button>
                                        <Button
                                            onClick={() => handleDelete(siswa.id, siswa.nama)}
                                            disabled={deletingId === siswa.id}
                                            variant="danger"
                                            isLoading={deletingId === siswa.id}
                                            className="text-xs px-2 py-1"
                                        >
                                            {deletingId === siswa.id ? "" : "Hapus"}
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
                            {editingId ? "Edit Siswa" : "Tambah Siswa"}
                        </h3>

                        {formError && (
                            <div className="mb-4 p-3 bg-rose-50 text-rose-700 rounded-lg border border-rose-200 text-sm">
                                {formError}
                            </div>
                        )}

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">NISN</label>
                                <input
                                    type="text"
                                    value={form.nis}
                                    onChange={(e) => setForm({ ...form, nis: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    placeholder="Nomor Induk Siswa"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Nama Lengkap</label>
                                <input
                                    type="text"
                                    value={form.nama}
                                    onChange={(e) => setForm({ ...form, nama: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    placeholder="Nama lengkap siswa"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Kelas</label>
                                <input
                                    type="text"
                                    value={form.kelas}
                                    onChange={(e) => setForm({ ...form, kelas: e.target.value })}
                                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    placeholder="XII RPL 1"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Jurusan / Konsentrasi</label>
                                <div className="relative">
                                    <input
                                        type="text"
                                        list="konsentrasi-list"
                                        value={form.konsentrasi_search ?? ""}
                                        onChange={(e) => {
                                            const search = e.target.value;
                                            setForm({ ...form, konsentrasi_search: search });
                                            // Cari konsentrasi yang cocok
                                            const kon = konsentrasiOptions.find(
                                                k => k.nama.toLowerCase().includes(search.toLowerCase()) ||
                                                    k.kode.includes(search)
                                            );
                                            if (kon) {
                                                setForm({
                                                    ...form,
                                                    konsentrasi_search: search,
                                                    konsentrasi_id: kon.id,
                                                    jurusan: kon.nama,
                                                });
                                            } else {
                                                setForm({
                                                    ...form,
                                                    konsentrasi_search: search,
                                                    konsentrasi_id: null,
                                                    jurusan: search,
                                                });
                                            }
                                        }}
                                        className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                        placeholder="Ketik untuk cari konsentrasi..."
                                    />
                                    <datalist id="konsentrasi-list">
                                        {konsentrasiOptions.map((k) => (
                                            <option key={k.id} value={`${k.kode} - ${k.nama}${k.bidang_nama ? ` (${k.bidang_nama})` : ""}`} />
                                        ))}
                                    </datalist>
                                </div>
                                {konsentrasiOptions.length === 0 && (
                                    <p className="text-xs text-amber-600 mt-1">
                                        Data konsentrasi kosong. Tambahkan di menu "Manajemen Spektrum Keahlian" terlebih dahulu.
                                    </p>
                                )}
                            </div>
                        </div>

                        <div className="mt-6 flex justify-end space-x-3">
                            <Button variant="ghost" onClick={() => setModalOpen(false)} disabled={saving}>Batal</Button>
                            <Button onClick={handleSave} isLoading={saving}>
                                {saving ? "Menyimpan..." : editingId ? "Simpan Perubahan" : "Tambah Siswa"}
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Modal Import CSV */}
            {importOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 border border-slate-200">
                        <h3 className="text-xl font-bold mb-4 text-slate-900">Import Siswa (CSV)</h3>

                        <p className="text-sm text-slate-500 mb-3">
                            Format kolom: <code className="bg-slate-100 px-1 rounded">nis,nama,kelas,jurusan</code>.
                            Baris dengan NISN yang sudah ada akan dilewati.
                        </p>

                        <input
                            type="file"
                            accept=".csv,text/csv"
                            onChange={(e) => setImportFile(e.target.files?.[0] ?? null)}
                            className="block w-full text-sm text-slate-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 file:font-medium hover:file:bg-blue-100"
                        />

                        {importError && (
                            <div className="mt-4 p-3 bg-rose-50 text-rose-700 rounded-lg border border-rose-200 text-sm">
                                {importError}
                            </div>
                        )}

                        {importResult && (
                            <div className="mt-4 p-3 bg-emerald-50 text-emerald-800 rounded-lg border border-emerald-200 text-sm space-y-1">
                                <p className="font-medium">Import selesai</p>
                                <p>Ditambahkan: {importResult.ditambahkan}</p>
                                <p>Dilewati (sudah ada): {importResult.dilewati_sudah_ada}</p>
                                {importResult.baris_error.length > 0 && (
                                    <div className="mt-1">
                                        <p className="font-medium">Baris bermasalah:</p>
                                        <ul className="list-disc list-inside text-xs text-rose-700">
                                            {importResult.baris_error.map((e, i) => (
                                                <li key={i}>{e}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        )}

                        <div className="mt-6 flex justify-end space-x-3">
                            <Button variant="ghost" onClick={() => setImportOpen(false)} disabled={importing}>
                                {importResult ? "Tutup" : "Batal"}
                            </Button>
                            {!importResult && (
                                <Button onClick={handleImport} isLoading={importing} disabled={!importFile}>
                                    {importing ? "Mengimpor..." : "Import"}
                                </Button>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}