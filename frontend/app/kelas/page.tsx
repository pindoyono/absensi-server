"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
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
type SiswaRingkas = {
    id: number;
    nis: string;
    nama: string;
    kelas: string;
    kelas_id: number | null;
    enrolled: boolean;
};
type Guru = { id: number; nama: string; role: string };
type Konsentrasi = { id: number; nama: string; kode: string };

export default function KelasPage() {
    const router = useRouter();
    const getToken = () => (typeof window !== "undefined" ? localStorage.getItem("token") : null);

    const [kelasList, setKelasList] = useState<Kelas[]>([]);
    const [siswaList, setSiswaList] = useState<SiswaRingkas[]>([]);
    const [guruList, setGuruList] = useState<Guru[]>([]);
    const [konsentrasiList, setKonsentrasiList] = useState<Konsentrasi[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    // modal kelas (create / edit)
    const [modalOpen, setModalOpen] = useState(false);
    const [editing, setEditing] = useState<Kelas | null>(null);
    const [form, setForm] = useState({
        nama: "", tingkat: "", konsentrasi_id: null as number | null,
        konsentrasi_search: "", wali_id: null as number | null, aktif: true,
    });
    const [saving, setSaving] = useState(false);
    const [formError, setFormError] = useState("");

    // modal anggota
    const [anggotaKelas, setAnggotaKelas] = useState<Kelas | null>(null);
    const [cariKiri, setCariKiri] = useState("");
    const [cariKanan, setCariKanan] = useState("");
    const [filterKanan, setFilterKanan] = useState<"semua" | "tanpa" | string>("tanpa");
    const [pilihKiri, setPilihKiri] = useState<Set<number>>(new Set());
    const [pilihKanan, setPilihKanan] = useState<Set<number>>(new Set());
    const [proses, setProses] = useState(false);

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

    const konsentrasiNama = (id: number | null) =>
        konsentrasiList.find((k) => k.id === id)?.nama ?? null;

    // ---------- CRUD kelas ----------
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
            nama: k.nama, tingkat: k.tingkat ?? "",
            konsentrasi_id: k.konsentrasi_id,
            konsentrasi_search: kon ? `${kon.kode} - ${kon.nama}` : "",
            wali_id: k.wali_id, aktif: k.aktif,
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

    // ---------- modal anggota ----------
    const bukaAnggota = (k: Kelas) => {
        setAnggotaKelas(k);
        setCariKiri("");
        setCariKanan("");
        setFilterKanan("tanpa");
        setPilihKiri(new Set());
        setPilihKanan(new Set());
    };

    const anggotaRombel = useMemo(
        () => (anggotaKelas ? siswaList.filter((s) => s.kelas_id === anggotaKelas.id) : []),
        [siswaList, anggotaKelas]
    );
    const kandidat = useMemo(() => {
        if (!anggotaKelas) return [];
        return siswaList.filter((s) => {
            if (s.kelas_id === anggotaKelas.id) return false; // sudah anggota
            if (filterKanan === "tanpa") return s.kelas_id == null;
            if (filterKanan === "semua") return true;
            return String(s.kelas_id) === filterKanan;
        });
    }, [siswaList, anggotaKelas, filterKanan]);

    const cocok = (s: SiswaRingkas, q: string) =>
        !q || s.nama.toLowerCase().includes(q.toLowerCase()) || s.nis.includes(q);

    const kiriTampil = anggotaRombel.filter((s) => cocok(s, cariKiri));
    const kananTampil = kandidat.filter((s) => cocok(s, cariKanan));

    const toggle = (set: Set<number>, id: number, setter: (s: Set<number>) => void) => {
        const n = new Set(set);
        n.has(id) ? n.delete(id) : n.add(id);
        setter(n);
    };

    const terapkan = async (tambah: number[], keluarkan: number[]) => {
        if (!anggotaKelas || (!tambah.length && !keluarkan.length)) return;
        setProses(true);
        try {
            const res = await safeFetch(`${API_BASE}/kelas/${anggotaKelas.id}/anggota`, {
                method: "PATCH",
                headers: authHeaders(),
                body: JSON.stringify({ tambah, keluarkan }),
            });
            if (!res.ok) throw new Error();
            // optimistic + refetch
            setSiswaList((list) =>
                list.map((s) =>
                    tambah.includes(s.id) ? { ...s, kelas_id: anggotaKelas.id, kelas: anggotaKelas.nama }
                    : keluarkan.includes(s.id) ? { ...s, kelas_id: null, kelas: "" }
                    : s
                )
            );
            setPilihKiri(new Set());
            setPilihKanan(new Set());
            fetchAll();
        } catch {
            setError("Gagal memperbarui anggota rombel");
        }
        setProses(false);
    };

    const listSiswa = (
        rows: SiswaRingkas[],
        dipilih: Set<number>,
        onToggle: (id: number) => void,
        sisiKanan: boolean
    ) => (
        <div className="border border-slate-200 rounded-lg overflow-y-auto flex-1 min-h-0 divide-y divide-slate-100">
            {rows.length === 0 && (
                <p className="text-xs text-slate-400 text-center py-8">Tidak ada data</p>
            )}
            {rows.map((s) => (
                <label key={s.id} className="flex items-center gap-3 px-3 py-2 hover:bg-slate-50 cursor-pointer text-sm">
                    <input type="checkbox" checked={dipilih.has(s.id)} onChange={() => onToggle(s.id)} />
                    <span className="flex-1 min-w-0">
                        <span className="font-medium text-slate-800 block truncate">{s.nama}</span>
                        <span className="text-xs text-slate-400 font-mono">
                            {s.nis}
                            {!s.enrolled && " · belum enroll"}
                        </span>
                    </span>
                    {sisiKanan && (
                        <Badge variant={s.kelas_id == null ? "warning" : "default"}>
                            {s.kelas_id == null ? "tanpa rombel" : s.kelas || "—"}
                        </Badge>
                    )}
                </label>
            ))}
        </div>
    );

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Manajemen Kelas</h1>
                    <p className="text-sm text-slate-500">Daftar rombel &amp; pengelolaan anggotanya</p>
                </div>
                <Button onClick={openCreate}>+ Kelas</Button>
            </div>

            {error && <div className="bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-lg text-sm">{error}</div>}

            {loading ? (
                <div className="space-y-2">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
            ) : (
                <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-x-auto">
                    <table className="min-w-full text-sm">
                        <thead>
                            <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                                <th className="py-3 px-4 text-left">Nama Rombel</th>
                                <th className="py-3 px-4 text-left">Tingkat</th>
                                <th className="py-3 px-4 text-left">Konsentrasi</th>
                                <th className="py-3 px-4 text-left">Wali Kelas</th>
                                <th className="py-3 px-4 text-center">Siswa</th>
                                <th className="py-3 px-4 text-left">Status</th>
                                <th className="py-3 px-4 text-center">Aksi</th>
                            </tr>
                        </thead>
                        <tbody>
                            {kelasList.length === 0 ? (
                                <tr><td colSpan={7} className="py-8 text-center text-slate-500">
                                    <p className="font-medium">Belum ada rombel</p>
                                    <p className="text-xs mt-1">Klik "+ Kelas" untuk membuat rombel baru</p>
                                </td></tr>
                            ) : (
                                kelasList.map((k) => (
                                    <tr key={k.id} className={`border-b border-slate-100 hover:bg-slate-50 transition ${!k.aktif ? "opacity-50" : ""}`}>
                                        <td className="py-3 px-4 font-medium text-slate-800">{k.nama}</td>
                                        <td className="py-3 px-4 text-slate-600">{k.tingkat ?? "-"}</td>
                                        <td className="py-3 px-4 text-slate-600">{konsentrasiNama(k.konsentrasi_id) ?? "-"}</td>
                                        <td className="py-3 px-4 text-slate-600">{k.wali_nama ?? "-"}</td>
                                        <td className="py-3 px-4 text-center">
                                            <Badge>{k.jumlah_siswa}</Badge>
                                        </td>
                                        <td className="py-3 px-4">
                                            <Badge variant={k.aktif ? "success" : "danger"}>{k.aktif ? "Aktif" : "Nonaktif"}</Badge>
                                        </td>
                                        <td className="py-3 px-4 text-center space-x-2 whitespace-nowrap">
                                            <Button onClick={() => bukaAnggota(k)} className="text-xs px-2 py-1">Anggota</Button>
                                            <Button onClick={() => openEdit(k)} variant="secondary" className="text-xs px-2 py-1">Edit</Button>
                                            <Button onClick={() => hapus(k)} variant="danger" className="text-xs px-2 py-1">Hapus</Button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            )}

            {/* ---------- Modal Anggota ---------- */}
            {anggotaKelas && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-4xl flex flex-col" style={{ maxHeight: "88vh" }}>
                        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
                            <h2 className="text-lg font-bold text-slate-900">
                                Anggota Rombel — {anggotaKelas.nama}
                            </h2>
                            <button onClick={() => setAnggotaKelas(null)} className="text-slate-400 hover:text-slate-700 text-xl leading-none">&times;</button>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-6 overflow-hidden flex-1 min-h-0">
                            {/* KIRI: anggota terdaftar */}
                            <div className="flex flex-col min-h-0">
                                <div className="flex items-center justify-between mb-2">
                                    <p className="font-semibold text-sm text-slate-700">Anggota Rombel ({anggotaRombel.length})</p>
                                    <Button
                                        variant="danger"
                                        className="text-xs px-2 py-1"
                                        disabled={proses || pilihKiri.size === 0}
                                        onClick={() => terapkan([], [...pilihKiri])}
                                    >
                                        Keluarkan ({pilihKiri.size})
                                    </Button>
                                </div>
                                <input
                                    value={cariKiri}
                                    onChange={(e) => setCariKiri(e.target.value)}
                                    placeholder="Cari nama / NIS…"
                                    className="w-full border border-slate-300 rounded-lg px-3 py-1.5 text-sm mb-2"
                                />
                                {listSiswa(kiriTampil, pilihKiri, (id) => toggle(pilihKiri, id, setPilihKiri), false)}
                            </div>

                            {/* KANAN: semua siswa */}
                            <div className="flex flex-col min-h-0">
                                <div className="flex items-center justify-between mb-2">
                                    <p className="font-semibold text-sm text-slate-700">Tambah Siswa</p>
                                    <Button
                                        className="text-xs px-2 py-1"
                                        disabled={proses || pilihKanan.size === 0}
                                        onClick={() => terapkan([...pilihKanan], [])}
                                    >
                                        Masukkan ({pilihKanan.size})
                                    </Button>
                                </div>
                                <div className="flex gap-2 mb-2">
                                    <input
                                        value={cariKanan}
                                        onChange={(e) => setCariKanan(e.target.value)}
                                        placeholder="Cari nama / NIS…"
                                        className="flex-1 min-w-0 border border-slate-300 rounded-lg px-3 py-1.5 text-sm"
                                    />
                                    <select
                                        value={filterKanan}
                                        onChange={(e) => { setFilterKanan(e.target.value); setPilihKanan(new Set()); }}
                                        className="border border-slate-300 rounded-lg px-2 py-1.5 text-sm max-w-[45%]"
                                    >
                                        <option value="tanpa">Belum ada rombel</option>
                                        <option value="semua">Semua rombel</option>
                                        {kelasList.filter((k) => k.id !== anggotaKelas.id).map((k) => (
                                            <option key={k.id} value={String(k.id)}>{k.nama}</option>
                                        ))}
                                    </select>
                                </div>
                                {listSiswa(kananTampil, pilihKanan, (id) => toggle(pilihKanan, id, setPilihKanan), true)}
                            </div>
                        </div>

                        <div className="px-6 py-3 border-t border-slate-200 flex justify-between items-center text-xs text-slate-500">
                            <span>Pilih siswa lalu klik "Masukkan" / "Keluarkan". Perubahan langsung tersimpan.</span>
                            <Button variant="secondary" className="text-xs px-3 py-1.5" onClick={() => setAnggotaKelas(null)}>Selesai</Button>
                        </div>
                    </div>
                </div>
            )}

            {/* ---------- Modal Kelas ---------- */}
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
                                    {guruList.map((g) => <option key={g.id} value={g.id}>{g.nama}</option>)}
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
