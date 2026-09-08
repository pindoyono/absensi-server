"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Button, Badge, Skeleton } from "@/components/ui/Base";

const API_BASE = "https://absen.smkn2malinau.sch.id";

type Pending = {
    siswa_id: number;
    nis: string;
    nama: string;
    kelas: string;
    tanggal_enrollment: string | null;
    enrolled_device_id: string | null;
    foto_jpeg: string | null;
};

export default function VerifikasiWajahPage() {
    const router = useRouter();
    const getToken = () => (typeof window !== "undefined" ? localStorage.getItem("token") : null);

    const [rows, setRows] = useState<Pending[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState<number | null>(null);

    const authHeaders = useCallback(() => {
        const t = getToken();
        if (!t) { router.push("/login"); return {} as Record<string, string>; }
        return { Authorization: `Bearer ${t}`, "Content-Type": "application/json" };
    }, [router]);

    const load = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/siswa/enroll-mandiri/pending`, { headers: authHeaders() });
            if (res.status === 401 || res.status === 403) { router.push("/login"); return; }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            setRows(await res.json());
            setError("");
        } catch (e: any) {
            setError("Gagal memuat daftar");
        }
        setLoading(false);
    }, [authHeaders, router]);

    useEffect(() => { load(); }, [load]);

    const aksi = async (siswaId: number, jenis: "konfirmasi" | "tolak") => {
        if (jenis === "tolak" && !confirm("Tolak pendaftaran ini? Data wajah dihapus, siswa harus daftar ulang.")) return;
        setBusy(siswaId);
        try {
            const res = await fetch(`${API_BASE}/siswa/${siswaId}/enroll-mandiri/${jenis}`, {
                method: "POST", headers: authHeaders(),
            });
            const b = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(b.detail || `HTTP ${res.status}`);
            setRows((r) => r.filter((x) => x.siswa_id !== siswaId));
        } catch (e: any) {
            setError(e.message || "Aksi gagal");
        }
        setBusy(null);
    };

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900">Verifikasi Daftar Wajah</h1>
                <p className="text-sm text-slate-500 mt-1">
                    Siswa yang mendaftarkan wajahnya sendiri di kiosk. Cocokkan foto dengan nama/NIS,
                    lalu Konfirmasi (siswa bisa absen) atau Tolak (hapus, daftar ulang). Foto dihapus otomatis setelah diproses.
                </p>
            </div>

            {error && <div className="bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-lg text-sm">{error}</div>}

            {loading ? (
                <div className="grid sm:grid-cols-2 gap-4">{[1, 2].map((i) => <Skeleton key={i} className="h-64 w-full" />)}</div>
            ) : rows.length === 0 ? (
                <div className="bg-white rounded-xl border border-slate-200 py-12 text-center text-slate-500">
                    <p className="font-medium">Tidak ada yang menunggu verifikasi</p>
                </div>
            ) : (
                <div className="grid sm:grid-cols-2 gap-4">
                    {rows.map((p) => (
                        <div key={p.siswa_id} className="bg-white rounded-xl border border-slate-200 overflow-hidden flex flex-col">
                            {p.foto_jpeg ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img
                                    src={`data:image/jpeg;base64,${p.foto_jpeg}`}
                                    alt={`Foto ${p.nama}`}
                                    className="w-full h-56 object-cover bg-slate-100"
                                />
                            ) : (
                                <div className="w-full h-56 bg-slate-100 flex items-center justify-center text-slate-400 text-sm">
                                    (tidak ada foto)
                                </div>
                            )}
                            <div className="p-4 flex-1 flex flex-col gap-1">
                                <p className="font-semibold text-slate-800">{p.nama}</p>
                                <p className="text-sm text-slate-500 font-mono">{p.nis}</p>
                                <div className="flex flex-wrap gap-2 mt-1 text-xs">
                                    {p.kelas && <Badge>{p.kelas}</Badge>}
                                    {p.tanggal_enrollment && <Badge variant="default">daftar {p.tanggal_enrollment}</Badge>}
                                    {p.enrolled_device_id && <Badge variant="default">{p.enrolled_device_id}</Badge>}
                                </div>
                                <div className="flex gap-2 mt-3">
                                    <Button className="flex-1" isLoading={busy === p.siswa_id}
                                        onClick={() => aksi(p.siswa_id, "konfirmasi")}>Konfirmasi</Button>
                                    <Button variant="danger" className="flex-1" disabled={busy === p.siswa_id}
                                        onClick={() => aksi(p.siswa_id, "tolak")}>Tolak</Button>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
