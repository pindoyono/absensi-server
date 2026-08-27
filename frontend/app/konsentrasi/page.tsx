"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Button, Badge, Skeleton } from "@/components/ui/Base";

const API_BASE = "https://absen.smkn2malinau.sch.id";

type Bidang = { id: number; nama: string; kode: string };
type Program = { id: number; bidang_id: number; nama: string; kode: string };
type Konsentrasi = {
    id: number;
    program_id: number;
    nama: string;
    kode: string;
    durasi_tahun: number;
    program_nama?: string;
    bidang_nama?: string;
};
type TreeNode = {
    id: number;
    nama: string;
    kode: string;
    program: { id: number; nama: string; kode: string; konsentrasi: { id: number; nama: string; kode: string; durasi_tahun: number }[] }[];
};

export default function KonsentrasiPage() {
    const router = useRouter();
    const getToken = () => typeof window !== "undefined" ? localStorage.getItem("token") : null;

    const [bidangList, setBidangList] = useState<Bidang[]>([]);
    const [programList, setProgramList] = useState<Program[]>([]);
    const [konsentrasiList, setKonsentrasiList] = useState<Konsentrasi[]>([]);
    const [tree, setTree] = useState<TreeNode[]>([]);
    const [loading, setLoading] = useState(true);
    const [tab, setTab] = useState<"bidang" | "program" | "konsentrasi">("bidang");

    // Filter
    const [filterBidang, setFilterBidang] = useState<number | "">("");
    const [filterProgram, setFilterProgram] = useState<number | "">("");

    // Modal state
    const [modalOpen, setModalOpen] = useState(false);
    const [editingItem, setEditingItem] = useState<any>(null);
    const [modalType, setModalType] = useState<"bidang" | "program" | "konsentrasi">("bidang");
    const [formData, setFormData] = useState<any>({});
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    const authHeaders = useCallback(() => {
        const t = getToken();
        if (!t) { router.push("/login"); return {}; }
        return { Authorization: `Bearer ${t}`, "Content-Type": "application/json" } as Record<string, string>;
    }, [router]);

    const safeFetch = async (url: string, opts?: RequestInit) => {
        const res = await fetch(url, opts);
        if (res.status === 401 || res.status === 403) { router.push("/login"); throw new Error("Unauthorized"); }
        return res;
    };

    // --- Fetch all data ---
    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const headers = authHeaders();
            const [bRes, pRes, kRes, tRes] = await Promise.all([
                safeFetch(`${API_BASE}/spektrum/bidang`, { headers }),
                safeFetch(`${API_BASE}/spektrum/program`, { headers }),
                safeFetch(`${API_BASE}/spektrum/konsentrasi`, { headers }),
                safeFetch(`${API_BASE}/spektrum/tree`, { headers }),
            ]);
            if (bRes.ok) setBidangList(await bRes.json());
            if (pRes.ok) setProgramList(await pRes.json());
            if (kRes.ok) setKonsentrasiList(await kRes.json());
            if (tRes.ok) setTree(await tRes.json());
        } catch (e: any) {
            if (e.message !== "Unauthorized") setError("Gagal memuat data");
        }
        setLoading(false);
    }, [authHeaders, router]);

    useEffect(() => { fetchAll(); }, [fetchAll]);

    // --- CRUD operations ---
    const saveData = async () => {
        setSaving(true);
        setError("");
        try {
            const headers = authHeaders();
            let url = "";
            let method = "POST";
            if (modalType === "bidang") {
                url = editingItem ? `${API_BASE}/spektrum/bidang/${editingItem.id}` : `${API_BASE}/spektrum/bidang`;
                method = editingItem ? "PUT" : "POST";
            } else if (modalType === "program") {
                url = editingItem ? `${API_BASE}/spektrum/program/${editingItem.id}` : `${API_BASE}/spektrum/program`;
                method = editingItem ? "PUT" : "POST";
            } else {
                url = editingItem ? `${API_BASE}/spektrum/konsentrasi/${editingItem.id}` : `${API_BASE}/spektrum/konsentrasi`;
                method = editingItem ? "PUT" : "POST";
            }
            const res = await safeFetch(url, { method, headers, body: JSON.stringify(formData) });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Gagal menyimpan");
            }
            setModalOpen(false);
            fetchAll();
        } catch (e: any) {
            if (e.message !== "Unauthorized") setError(e.message);
        }
        setSaving(false);
    };

    const deleteItem = async (type: string, id: number) => {
        if (!confirm(`Hapus ${type} ini?`)) return;
        try {
            const headers = authHeaders();
            const res = await safeFetch(`${API_BASE}/spektrum/${type}/${id}`, { method: "DELETE", headers });
            if (!res.ok) throw new Error("Gagal menghapus");
            fetchAll();
        } catch (e: any) {
            if (e.message !== "Unauthorized") setError(e.message);
        }
    };

    // --- Modal helpers ---
    const openCreate = (type: "bidang" | "program" | "konsentrasi") => {
        setModalType(type);
        setEditingItem(null);
        if (type === "bidang") setFormData({ nama: "", kode: "" });
        else if (type === "program") setFormData({ bidang_id: filterBidang || "", nama: "", kode: "" });
        else setFormData({ program_id: filterProgram || "", nama: "", kode: "", durasi_tahun: 3 });
        setModalOpen(true);
    };

    const openEdit = (type: "bidang" | "program" | "konsentrasi", item: any) => {
        setModalType(type);
        setEditingItem(item);
        if (type === "bidang") setFormData({ nama: item.nama, kode: item.kode });
        else if (type === "program") setFormData({ bidang_id: item.bidang_id, nama: item.nama, kode: item.kode });
        else setFormData({ program_id: item.program_id, nama: item.nama, kode: item.kode, durasi_tahun: item.durasi_tahun });
        setModalOpen(true);
    };

    // Filtered list based on cascading selection
    const filteredProgramList = filterBidang ? programList.filter(p => p.bidang_id === filterBidang) : programList;
    const filteredKonsentrasiList = filterProgram ? konsentrasiList.filter(k => k.program_id === filterProgram) : filterBidang ? konsentrasiList.filter(k => filteredProgramList.some(p => p.id === k.program_id)) : konsentrasiList;

    return (
        <div className="max-w-6xl mx-auto px-4 py-8">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Manajemen Spektrum Keahlian</h1>
                    <p className="text-sm text-gray-500 mt-1">Kepmendikbudristek No. 244/M/2024</p>
                </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-lg w-fit">
                {(["bidang", "program", "konsentrasi"] as const).map(t => (
                    <button key={t} onClick={() => setTab(t)}
                        className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${tab === t ? "bg-white shadow text-gray-900" : "text-gray-500 hover:text-gray-700"}`}>
                        {t === "bidang" ? "Bidang Keahlian" : t === "program" ? "Program Keahlian" : "Konsentrasi Keahlian"}
                    </button>
                ))}
            </div>

            {/* Filters */}
            <div className="flex flex-wrap gap-3 mb-4">
                {(tab === "program" || tab === "konsentrasi") && (
                    <select value={filterBidang} onChange={e => { setFilterBidang(e.target.value ? Number(e.target.value) : ""); setFilterProgram(""); }}
                        className="border rounded-lg px-3 py-2 text-sm">
                        <option value="">Semua Bidang</option>
                        {bidangList.map(b => <option key={b.id} value={b.id}>{b.kode} - {b.nama}</option>)}
                    </select>
                )}
                {tab === "konsentrasi" && (
                    <select value={filterProgram} onChange={e => setFilterProgram(e.target.value ? Number(e.target.value) : "")}
                        className="border rounded-lg px-3 py-2 text-sm">
                        <option value="">Semua Program</option>
                        {filteredProgramList.map(p => <option key={p.id} value={p.id}>{p.kode} - {p.nama}</option>)}
                    </select>
                )}
                <Button variant="primary" onClick={() => openCreate(tab)}>
                    + Tambah {tab === "bidang" ? "Bidang" : tab === "program" ? "Program" : "Konsentrasi"}
                </Button>
            </div>

            {/* Error */}
            {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{error}</div>}

            {/* Loading */}
            {loading ? (
                <div className="space-y-3">{[1, 2, 3].map(i => <Skeleton key={i} className="h-12 w-full" />)}</div>
            ) : (
                <>
                    {/* Bidang table */}
                    {tab === "bidang" && (
                        <div className="bg-white rounded-xl border overflow-hidden">
                            <table className="w-full text-sm">
                                <thead className="bg-gray-50">
                                    <tr>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Kode</th>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Nama Bidang</th>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Program</th>
                                        <th className="text-right px-4 py-3 font-medium text-gray-500">Aksi</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {bidangList.map(b => {
                                        const progCount = programList.filter(p => p.bidang_id === b.id).length;
                                        return (
                                            <tr key={b.id} className="hover:bg-gray-50">
                                                <td className="px-4 py-3"><Badge>{b.kode}</Badge></td>
                                                <td className="px-4 py-3 font-medium">{b.nama}</td>
                                                <td className="px-4 py-3 text-gray-500">{progCount} program</td>
                                                <td className="px-4 py-3 text-right">
                                                    <button onClick={() => openEdit("bidang", b)} className="text-blue-600 hover:underline text-xs mr-3">Edit</button>
                                                    <button onClick={() => deleteItem("bidang", b.id)} className="text-red-600 hover:underline text-xs">Hapus</button>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                    {bidangList.length === 0 && <tr><td colSpan={4} className="text-center py-8 text-gray-400">Belum ada data bidang keahlian</td></tr>}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Program table */}
                    {tab === "program" && (
                        <div className="bg-white rounded-xl border overflow-hidden">
                            <table className="w-full text-sm">
                                <thead className="bg-gray-50">
                                    <tr>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Kode</th>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Nama Program</th>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Bidang</th>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Konsentrasi</th>
                                        <th className="text-right px-4 py-3 font-medium text-gray-500">Aksi</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {filteredProgramList.map(p => {
                                        const bidang = bidangList.find(b => b.id === p.bidang_id);
                                        const konCount = konsentrasiList.filter(k => k.program_id === p.id).length;
                                        return (
                                            <tr key={p.id} className="hover:bg-gray-50">
                                                <td className="px-4 py-3"><Badge>{p.kode}</Badge></td>
                                                <td className="px-4 py-3 font-medium">{p.nama}</td>
                                                <td className="px-4 py-3 text-gray-500">{bidang?.nama || "-"}</td>
                                                <td className="px-4 py-3 text-gray-500">{konCount} konsentrasi</td>
                                                <td className="px-4 py-3 text-right">
                                                    <button onClick={() => openEdit("program", p)} className="text-blue-600 hover:underline text-xs mr-3">Edit</button>
                                                    <button onClick={() => deleteItem("program", p.id)} className="text-red-600 hover:underline text-xs">Hapus</button>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                    {filteredProgramList.length === 0 && <tr><td colSpan={5} className="text-center py-8 text-gray-400">Belum ada data program keahlian</td></tr>}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Konsentrasi table */}
                    {tab === "konsentrasi" && (
                        <div className="bg-white rounded-xl border overflow-hidden">
                            <table className="w-full text-sm">
                                <thead className="bg-gray-50">
                                    <tr>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Kode</th>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Nama Konsentrasi</th>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Program</th>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Bidang</th>
                                        <th className="text-left px-4 py-3 font-medium text-gray-500">Durasi</th>
                                        <th className="text-right px-4 py-3 font-medium text-gray-500">Aksi</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {filteredKonsentrasiList.map(k => (
                                        <tr key={k.id} className="hover:bg-gray-50">
                                            <td className="px-4 py-3"><Badge>{k.kode}</Badge></td>
                                            <td className="px-4 py-3 font-medium">{k.nama}</td>
                                            <td className="px-4 py-3 text-gray-500">{k.program_nama || "-"}</td>
                                            <td className="px-4 py-3 text-gray-500">{k.bidang_nama || "-"}</td>
                                            <td className="px-4 py-3"><Badge variant={k.durasi_tahun === 4 ? "warning" : "default"}>{k.durasi_tahun} tahun</Badge></td>
                                            <td className="px-4 py-3 text-right">
                                                <button onClick={() => openEdit("konsentrasi", k)} className="text-blue-600 hover:underline text-xs mr-3">Edit</button>
                                                <button onClick={() => deleteItem("konsentrasi", k.id)} className="text-red-600 hover:underline text-xs">Hapus</button>
                                            </td>
                                        </tr>
                                    ))}
                                    {filteredKonsentrasiList.length === 0 && <tr><td colSpan={6} className="text-center py-8 text-gray-400">Belum ada data konsentrasi keahlian</td></tr>}
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}

            {/* Modal */}
            {modalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
                        <h2 className="text-lg font-bold mb-4">
                            {editingItem ? "Edit" : "Tambah"} {modalType === "bidang" ? "Bidang Keahlian" : modalType === "program" ? "Program Keahlian" : "Konsentrasi Keahlian"}
                        </h2>

                        <div className="space-y-4">
                            {modalType === "program" && (
                                <div>
                                    <label className="block text-xs font-medium text-gray-500 mb-1">Bidang Keahlian</label>
                                    <select value={formData.bidang_id || ""} onChange={e => setFormData({ ...formData, bidang_id: Number(e.target.value) })}
                                        className="w-full border rounded-lg px-3 py-2 text-sm">
                                        <option value="">Pilih Bidang</option>
                                        {bidangList.map(b => <option key={b.id} value={b.id}>{b.kode} - {b.nama}</option>)}
                                    </select>
                                </div>
                            )}
                            {modalType === "konsentrasi" && (
                                <div>
                                    <label className="block text-xs font-medium text-gray-500 mb-1">Program Keahlian</label>
                                    <select value={formData.program_id || ""} onChange={e => setFormData({ ...formData, program_id: Number(e.target.value) })}
                                        className="w-full border rounded-lg px-3 py-2 text-sm">
                                        <option value="">Pilih Program</option>
                                        {programList.map(p => <option key={p.id} value={p.id}>{p.kode} - {p.nama}</option>)}
                                    </select>
                                </div>
                            )}
                            <div>
                                <label className="block text-xs font-medium text-gray-500 mb-1">Kode</label>
                                <input type="text" value={formData.kode || ""} onChange={e => setFormData({ ...formData, kode: e.target.value })}
                                    placeholder="misal: 4.1.1" className="w-full border rounded-lg px-3 py-2 text-sm" />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-gray-500 mb-1">Nama</label>
                                <input type="text" value={formData.nama || ""} onChange={e => setFormData({ ...formData, nama: e.target.value })}
                                    placeholder="Nama lengkap" className="w-full border rounded-lg px-3 py-2 text-sm" />
                            </div>
                            {modalType === "konsentrasi" && (
                                <div>
                                    <label className="block text-xs font-medium text-gray-500 mb-1">Durasi Program</label>
                                    <select value={formData.durasi_tahun || 3} onChange={e => setFormData({ ...formData, durasi_tahun: Number(e.target.value) })}
                                        className="w-full border rounded-lg px-3 py-2 text-sm">
                                        <option value={3}>3 Tahun</option>
                                        <option value={4}>4 Tahun</option>
                                    </select>
                                </div>
                            )}
                        </div>

                        {error && <p className="text-red-600 text-xs mt-4">{error}</p>}

                        <div className="flex justify-end gap-3 mt-6">
                            <Button variant="secondary" onClick={() => setModalOpen(false)}>Batal</Button>
                            <Button variant="primary" onClick={saveData} isLoading={saving}>Simpan</Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}