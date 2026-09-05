"use client";

import { useState, useEffect } from "react";

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface NavLink {
    href: string;
    label: string;
}

// Nav penuh untuk guru/admin (role apa pun selain "siswa") — sama seperti
// sebelum role siswa ditambahkan, supaya tidak ada yang berubah untuk mereka.
const NAV_STAF: NavLink[] = [
    { href: "/", label: "Dashboard" },
    { href: "/guru", label: "Guru" },
    { href: "/siswa", label: "Siswa" },
    { href: "/jadwal", label: "Jadwal" },
    { href: "/dispensasi", label: "Dispensasi" },
    { href: "/absensi", label: "Absensi" },
    { href: "/laporan", label: "Laporan" },
    { href: "/device", label: "Device" },
    { href: "/status-device", label: "Status Device" },
    { href: "/konsentrasi", label: "Spektrum" },
];

// Siswa hanya boleh lihat riwayat sendiri — TIDAK menampilkan tautan ke
// halaman admin lain sama sekali (walau backend juga sudah menolaknya lewat
// 401, ini soal UX: jangan tunjukkan menu yang memang tidak bisa dipakai).
const NAV_SISWA: NavLink[] = [
    { href: "/saya", label: "Riwayat Saya" },
];

export default function Nav({ variant }: { variant: "desktop" | "mobile" }) {
    const [links, setLinks] = useState<NavLink[]>(NAV_STAF);

    useEffect(() => {
        const token = localStorage.getItem("token");
        if (!token) return;
        fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
            .then((res) => (res.ok ? res.json() : null))
            .then((data) => {
                if (data?.role === "siswa") setLinks(NAV_SISWA);
            })
            .catch(() => { /* biarkan nav staf default kalau /auth/me gagal */ });
    }, []);

    if (variant === "mobile") {
        return (
            <div className="md:hidden bg-slate-100 border-b border-slate-200 px-4 py-2 flex justify-around text-xs font-medium">
                {links.map((l) => (
                    <a key={l.href} href={l.href} className="text-slate-600 hover:text-blue-600">
                        {l.label}
                    </a>
                ))}
            </div>
        );
    }

    return (
        <nav className="hidden md:flex items-center space-x-1">
            {links.map((l) => (
                <a
                    key={l.href}
                    href={l.href}
                    className="px-3 py-2 rounded-md text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50 transition"
                >
                    {l.label}
                </a>
            ))}
        </nav>
    );
}
