"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Button, Badge, Skeleton } from "@/components/ui/Base";

const API_BASE = "https://absen.smkn2malinau.sch.id";

type Kelas = {
    id: number;
    nama: string;
    tingkat: string | null;
    konsentrasi_id: number | null;
    wali_id: number | null;
    wali_nama: string | null;
    aktif: boolean;
    jumlah_siswa: number;
};
type SiswaRingkas = { id: number; nis: string; nama: string; kelas_id: number | null; enrolled: boolean };
type Guru = { id: number; nama: string; role: string };
type Konsentrasi = { id: number; nama: string; kode: string };

const TANPA_ROMBEL = -1; // id sintetis untuk kolom "Belum ada rombel"

export default function KelasPage() {
    const router = useRouter();
    const getToken = () => (typeof window !== "undefined" ? localStorage.getItem("token") : null);

    const [kelasList, setKelasList] = useState<Kelas[]>([]);
    const [siswaList, setSiswaList] = useState<SiswaRingkas[]>([]);
    const [guruList, setGuruList] = useState<Guru[]>([]);
    const [konsentrasiList, setKonsentrasiList] = useState<Konsentrasi[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [dragId, setDragId] = useState<number | null>(null);
    const [dropTarget, setDropTarget] = useState<number | null>(null);

    // Modal kelas
    const [modalOpen, setModalOpen] = useState(false);
    const [editing, setEditing] = useState<Kelas | null>(null);
    const [form, setForm] = useState<{ nama: string; tingkat: string; konsentrasi_id: number | null; konsentrasi_search: string; wali_id: number | null; aktif: boolean }>(
        { nama: "", tingkat: "", konsentrasi_id: null, konsentrasi_search: "", wali_id: null, aktif: true }
    );
    const [saving, setSaving] = useState(false);
    const [formError, setFormError] = useState("");

    const authHeaders = useCallback(() => {
        const t = getToken();
        if (!t) { router.push("/login"); return {} as Record<string, string>; }
        return { Authorization: `Bearer ${t}`, "Content-Type": "application/json" };
    }, [router]);

    const safeFetch = useCallback(async (url: string, opts?: RequestInit) => {
        const res = await fetch(url, opts);
        if (res.status === 401 || res.status === 403) { router.push("/login"); throw new Error("Unauthorized"); }
        return res;
    }, [router]);

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const headers = authHeaders();
            const [kRes, sRes, gRes, koRes] = await Promise.all([
                safeFetch(`${API_BASE}/kelas`, { headers }),
                safeFetch(`${API_BASE}/siswa`, { headers }),
                safeFetch(`${API_BASE}/guru`, { headers }),
                safeFetch(`${API_BASE}/spektrum/konsentrasi`, { headers }),
            ]);
            if (kRes.ok) setKelasList(await kRes.json());
            if (sRes.ok) setSiswaList(await sRes.json());
            if (gRes.ok) setGuruList(await gRes.json());
            if (koRes.ok) setKonsentrasiList(await koRes.json());
        } catch (e: any) {
            if (e.message !== "Unauthorized") setError("Gagal memuat data");
        }
        setLoading(false);
    }, [authHeaders, safeFetch]);

    useEffect(() => { fetchAll(); }, [fetchAll]);

    // --- drag & drop (native HTML5) ---
    const pindah = async (siswaId: number, kelasId: number | null) => {
        const sebelum = siswaList;
        setSiswaList((list) => list.map((s) => (s.id === siswaId ? { ...s, kelas_id: kelasId } : s)));
        try {
            const res = await safeFetch(`${API_BASE}/siswa/${siswaId}`, {
                method: "PATCH",
                headers: authHeaders(),
                body: JSON.stringify({ kelas_id: kelasId }),
            });
            if (!res.ok) throw new Error();
            fetchAll(); // segarkan jumlah_siswa
        } catch {
            setSiswaList(sebelum); // rollback
            setError("Gagal memindahkan siswa");
        }
    };

    const onDrop = (kelasId: number | null) => {
        if (dragId != null) pindah(dragId, kelasId);
        setDragId(null);
        setDropTarget(null);
    };

    // --- CRUD kelas ---
    const openCreate = () => {
        setEditing(null);
        setForm({ nama: "", tingkat: "", konsentrasi_id: null, konsentrasi_search: "", wali_id: null, aktif: true });
        setFormError("");
        setModalOpen(true);
    };
    const openEdit = (k: Kelas) => {
        setEditing(k);
        const kon = konsentrasiList.find((x) => x.id === k.konsentrasi_id);
        setForm({
            nama: k.nama,
            tingkat: k.tingkat ?? "",
            konsentrasi_id: k.konsentrasi_id,
            konsentrasi_search: kon ? `${kon.kode} - ${kon.nama}` : "",
            wali_id: k.wali_id,
            aktif: k.aktif,
        });
        setFormError("");
        setModalOpen(true);
    };

    const simpan = async () => {
        if (!form.nama.trim()) { setFormError("Nama kelas wajib diisi."); return; }
        setSaving(true);
        setFormError("");
        try {
            const payload: any = {
                nama: form.nama.trim(),
                tingkat: form.tingkat.trim() || null,
                konsentrasi_id: form.konsentrasi_id,
                wali_id: form.wali_id,
            };
            if (editing) payload.aktif = form.aktif;
            const res = await safeFetch(
                editing ? `${API_BASE}/kelas/${editing.id}` : `${API_BASE}/kelas`,
                { method: editing ? "PUT" : "POST", headers: authHeaders(), body: JSON.stringify(payload) }
            );
            if (!res.ok) {
                const b = await res.json().catch(() => ({}));
                throw new Error(b.detail || "Gagal menyimpan");
            }
            setModalOpen(false);
            fetchAll();
        } catch (e: any) {
            if (e.message !== "Unauthorized") setFormError(e.message);
        }
        setSaving(false);
    };

    const hapus = async (k: Kelas) => {
        if (!confirm(`Hapus kelas "${k.nama}"?`)) return;
        try {
            const res = await safeFetch(`${API_BASE}/kelas/${k.id}`, { method: "DELETE", headers: authHeaders() });
            if (!res.ok) {
                const b = await res.json().catch(() => ({}));
                throw new Error(b.detail || "Gagal menghapus");
            }
            setError("");
            fetchAll();
        } catch (e: any) {
            if (e.message !== "Unauthorized") setError(e.message);
        }
    };

    const siswaDi = (kelasId: number | null) => siswaList.filter((s) => (s.kelas_id ?? null) === kelasId);
    const guruWali = guruList; // semua guru bisa jadi wali

    const kolom = (judul: string, kelasId: number | null, k?: Kelas) => {
        const isDrop = dropTarget === (kelasId ?? TANPA_ROMBEL);
        const anggota = siswaDi(kelasId);
        return (
            <div
                key={kelasId ?? TANPA_ROMBEL}
                onDragOver={(e) => { e.preventDefault(); setDropTarget(kelasId ?? TANPA_ROMBEL); }}
                onDragLeave={() => setDropTarget(null)}
                onDrop={() => onDrop(kelasId)}
                className={`flex-shrink-0 w-64 rounded-xl border p-3 flex flex-col max-h-[70vh] ${
                    isDrop ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-white"
                }`}
            >
                <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="min-w-0">
                        <p className="font-semibold text-slate-800 text-sm truncate">{judul}</p>
                        <p className="text-xs text-slate-500">
                            {anggota.length} siswa
                            {k?.wali_nama ? ` · wali: ${k.wali_nama}` : ""}
                        </p>
                    </div>
                    {k && (
                        <div className="flex gap-1 shrink-0">
                            <button onClick={() => openEdit(k)} className="text-blue-600 hover:underline text-xs">Edit</button>
                            <button onClick={() => hapus(k)} className="text-rose-600 hover:underline text-xs">Hapus</button>
                        </div>
                    )}
                </div>
                <div className="space-y-1.5 overflow-y-auto flex-1 pr-1">
                    {anggota.map((s) => (
                        <div
                            key={s.id}
                            draggable
                            onDragStart={() => setDragId(s.id)}
                            onDragEnd={() => { setDragId(null); setDropTarget(null); }}
                            className={`rounded-lg border px-2.5 py-1.5 bg-white cursor-grab active:cursor-grabbing text-xs ${
                                dragId === s.id ? "opacity-40" : "border-slate-200 hover:border-slate-300"
                            }`}
                        >
                            <p className="font-medium text-slate-800 truncate">{s.nama}</p>
                            <p className="text-slate-400 font-mono">{s.nis}{s.enrolled ? "" : " · belum enroll"}</p>
                        </div>
                    ))}
                    {anggota.length === 0 && (
                        <p className="text-xs text-slate-400 text-center py-4">Tarik siswa ke sini</p>
                    )}
                </div>
            </div>
        );
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Manajemen Kelas</h1>
                    <p className="text-sm text-slate-500">Seret kartu siswa antar rombel untuk memindahkannya</p>
                </div>
                <Button onClick={openCreate}>+ Kelas</Button>
            </div>

            {error && <div className="bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-lg text-sm">{error}</div>}

            {loading ? (
                <div className="flex gap-3">{[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-64 w-64" />)}</div>
            ) : (
                <div className="flex gap-3 overflow-x-auto pb-3">
                    {kolom("Belum ada rombel", null)}
                    {kelasList.map((k) => kolom(k.nama, k.id, k))}
                </div>
            )}

            {modalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
                        <h2 className="text-lg font-bold mb-4">{editing ? "Edit Kelas" : "Tambah Kelas"}</h2>
                        {formError && <div className="mb-4 p-3 bg-rose-50 text-rose-700 rounded-lg border border-rose-200 text-sm">{formError}</div>}
                        <div className="space-y-4">
                            <div>
                                <label className="block text-xs font-medium text-slate-500 mb-1">Nama Kelas</label>
                                <input type="text" value={form.nama} onChange={(e) => setForm({ ...form, nama: e.target.value })}
                                    placeholder="XI DKV A" className="w-full border rounded-lg px-3 py-2 text-sm" />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-slate-500 mb-1">Tingkat <span className="text-slate-400">(opsional)</span></label>
                                <input type="text" value={form.tingkat} onChange={(e) => setForm({ ...form, tingkat: e.target.value })}
                                    placeholder="X / XI / XII" className="w-full border rounded-lg px-3 py-2 text-sm" />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-slate-500 mb-1">Konsentrasi Keahlian <span className="text-slate-400">(opsional)</span></label>
                                <input type="text" list="kelas-konsentrasi-list" value={form.konsentrasi_search}
                                    onChange={(e) => {
                                        const v = e.target.value;
                                        const kon = konsentrasiList.find((k) => `${k.kode} - ${k.nama}` === v || k.nama.toLowerCase() === v.toLowerCase());
                                        setForm({ ...form, konsentrasi_search: v, konsentrasi_id: kon ? kon.id : null });
                                    }}
                                    placeholder="Ketik untuk cari…" className="w-full border rounded-lg px-3 py-2 text-sm" />
                                <datalist id="kelas-konsentrasi-list">
                                    {konsentrasiList.map((k) => <option key={k.id} value={`${k.kode} - ${k.nama}`} />)}
                                </datalist>
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-slate-500 mb-1">Wali Kelas <span className="text-slate-400">(opsional)</span></label>
                                <select value={form.wali_id ?? ""} onChange={(e) => setForm({ ...form, wali_id: e.target.value ? Number(e.target.value) : null })}
                                    className="w-full border rounded-lg px-3 py-2 text-sm">
                                    <option value="">— tidak ada —</option>
                                    {guruWali.map((g) => <option key={g.id} value={g.id}>{g.nama}</option>)}
                                </select>
                            </div>
                            {editing && (
                                <label className="flex items-center gap-2 text-sm text-slate-700">
                                    <input type="checkbox" checked={form.aktif} onChange={(e) => setForm({ ...form, aktif: e.target.checked })} />
                                    Kelas aktif
                                </label>
                            )}
                        </div>
                        <div className="flex justify-end gap-3 mt-6">
                            <Button variant="secondary" onClick={() => setModalOpen(false)} disabled={saving}>Batal</Button>
                            <Button onClick={simpan} isLoading={saving}>Simpan</Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
