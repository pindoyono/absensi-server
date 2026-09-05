"use client";

import { useState, useEffect, useCallback } from "react";
import { format } from "date-fns";
import { id } from "date-fns/locale";
import { Badge, Skeleton, Button } from "@/components/ui/Base";

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface Profil {
    id: number;
    nis: string;
    nama: string;
    kelas: string;
    jurusan: string;
    email: string | null;
}

interface AbsensiSaya {
    record_id: string;
    tanggal: string;
    type: "MASUK" | "PULANG";
    jam_aktual: string;
    status_kehadiran_otomatis: string;
    status_kehadiran_final: string | null;
    catatan: string | null;
}

function statusBadge(status: string) {
    const s = status.toUpperCase();
    if (s === "NORMAL") return <Badge variant="success">Tepat waktu</Badge>;
    if (s === "TERLAMBAT") return <Badge variant="warning">Terlambat</Badge>;
    if (s === "SAKIT" || s === "IZIN") return <Badge variant="warning">{s === "SAKIT" ? "Sakit" : "Izin"}</Badge>;
    return <Badge variant="default">{status}</Badge>;
}

export default function SayaPage() {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [profil, setProfil] = useState<Profil | null>(null);
    const [riwayat, setRiwayat] = useState<AbsensiSaya[]>([]);

    const muat = useCallback(async (t: string) => {
        setLoading(true);
        try {
            const [resProfil, resAbsensi] = await Promise.all([
                fetch(`${API_BASE}/siswa/saya`, { headers: { Authorization: `Bearer ${t}` } }),
                fetch(`${API_BASE}/siswa/saya/absensi`, { headers: { Authorization: `Bearer ${t}` } }),
            ]);
            if (resProfil.status === 401 || resAbsensi.status === 401) {
                localStorage.removeItem("token");
                window.location.href = "/login";
                return;
            }
            if (!resProfil.ok) throw new Error(`HTTP ${resProfil.status}`);
            setProfil(await resProfil.json());
            setRiwayat(resAbsensi.ok ? await resAbsensi.json() : []);
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
        muat(t);
    }, [muat]);

    if (loading) {
        return (
            <div className="space-y-4">
                <Skeleton className="h-8 w-48 mb-6" />
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
            </div>
        );
    }

    if (error || !profil) {
        return (
            <div className="bg-rose-50 border border-rose-200 rounded-xl p-6 text-center">
                <h3 className="font-bold text-rose-700">Gagal memuat data</h3>
                <p className="text-rose-600 text-sm mt-1">{error ?? "Profil tidak ditemukan"}</p>
                <div className="mt-4 flex justify-center gap-3">
                    <Button onClick={() => window.location.reload()} variant="secondary">Coba Lagi</Button>
                    <a href="/login"><Button variant="ghost">Ke Halaman Login</Button></a>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6 max-w-3xl">
            <div>
                <h1 className="text-2xl font-bold text-slate-900">Riwayat Absensi Saya</h1>
                <p className="text-sm text-slate-500">Data pribadi — hanya kamu yang bisa melihat halaman ini</p>
            </div>

            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex items-center gap-4">
                <div className="w-14 h-14 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-xl">
                    {profil.nama.charAt(0).toUpperCase()}
                </div>
                <div>
                    <p className="font-bold text-slate-900">{profil.nama}</p>
                    <p className="text-sm text-slate-500">{profil.kelas} · NIS {profil.nis}</p>
                    {profil.email && <p className="text-xs text-slate-400 mt-0.5">{profil.email}</p>}
                </div>
            </div>

            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                {riwayat.length === 0 ? (
                    <div className="py-12 text-center text-slate-500">
                        <p className="font-medium">Belum ada riwayat absensi</p>
                    </div>
                ) : (
                    <table className="min-w-full text-sm">
                        <thead>
                            <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                                <th className="py-3 px-4 text-left">Tanggal</th>
                                <th className="py-3 px-4 text-left">Jenis</th>
                                <th className="py-3 px-4 text-left">Jam</th>
                                <th className="py-3 px-4 text-left">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {riwayat.map((r) => (
                                <tr key={r.record_id} className="border-b border-slate-100">
                                    <td className="py-3 px-4 text-slate-700">
                                        {format(new Date(r.tanggal), "d MMM yyyy", { locale: id })}
                                    </td>
                                    <td className="py-3 px-4 text-slate-700">{r.type === "MASUK" ? "Masuk" : "Pulang"}</td>
                                    <td className="py-3 px-4 text-slate-700">{r.jam_aktual.slice(11, 16)}</td>
                                    <td className="py-3 px-4">{statusBadge(r.status_kehadiran_final ?? r.status_kehadiran_otomatis)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
