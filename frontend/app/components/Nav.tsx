"use client";

import { useState, useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

const API_BASE = "https://absen.smkn2malinau.sch.id";

type Link = { href: string; label: string };
type Group = { label: string; items: Link[] };
// entri nav = link tunggal ATAU grup dropdown
type Entry = Link | Group;

const isGroup = (e: Entry): e is Group => "items" in e;

// Nav staf (admin/guru): dikelompokkan supaya rapi walau menu banyak.
const NAV_STAF: Entry[] = [
    { href: "/", label: "Dashboard" },
    {
        label: "Data",
        items: [
            { href: "/guru", label: "Guru" },
            { href: "/siswa", label: "Siswa" },
            { href: "/kelas", label: "Kelas" },
            { href: "/konsentrasi", label: "Spektrum Keahlian" },
        ],
    },
    {
        label: "Kehadiran",
        items: [
            { href: "/absensi", label: "Absensi" },
            { href: "/laporan", label: "Laporan" },
            { href: "/dispensasi", label: "Dispensasi" },
            { href: "/verifikasi-wajah", label: "Verifikasi Wajah" },
        ],
    },
    { href: "/jadwal", label: "Jadwal" },
    {
        label: "Perangkat",
        items: [
            { href: "/device", label: "Device" },
            { href: "/status-device", label: "Status Device" },
        ],
    },
];

const NAV_SISWA: Entry[] = [{ href: "/saya", label: "Riwayat Saya" }];

export default function Nav() {
    const pathname = usePathname();
    const [entries, setEntries] = useState<Entry[]>(NAV_STAF);
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [openGroup, setOpenGroup] = useState<string | null>(null);
    const navRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const token = localStorage.getItem("token");
        if (!token) return;
        fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
            .then((res) => (res.ok ? res.json() : null))
            .then((data) => { if (data?.role === "siswa") setEntries(NAV_SISWA); })
            .catch(() => { });
    }, []);

    // Tutup dropdown/drawer saat pindah halaman atau klik di luar.
    useEffect(() => { setDrawerOpen(false); setOpenGroup(null); }, [pathname]);
    useEffect(() => {
        const onDown = (e: MouseEvent) => {
            if (navRef.current && !navRef.current.contains(e.target as Node)) setOpenGroup(null);
        };
        document.addEventListener("mousedown", onDown);
        return () => document.removeEventListener("mousedown", onDown);
    }, []);

    const aktif = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
    const grupAktif = (g: Group) => g.items.some((i) => aktif(i.href));

    return (
        <div ref={navRef} className="flex items-center">
            {/* ---------- Desktop (lg+) ---------- */}
            <nav className="hidden lg:flex items-center gap-0.5">
                {entries.map((e) =>
                    isGroup(e) ? (
                        <div key={e.label} className="relative">
                            <button
                                onClick={() => setOpenGroup((g) => (g === e.label ? null : e.label))}
                                className={`flex items-center gap-1 px-3 py-2 rounded-md text-sm font-medium transition ${
                                    grupAktif(e) ? "text-blue-700 bg-blue-50" : "text-slate-600 hover:text-blue-600 hover:bg-slate-50"
                                }`}
                            >
                                {e.label}
                                <svg className={`w-3.5 h-3.5 transition-transform ${openGroup === e.label ? "rotate-180" : ""}`}
                                    fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                </svg>
                            </button>
                            {openGroup === e.label && (
                                <div className="absolute left-0 mt-1 w-52 bg-white border border-slate-200 rounded-xl shadow-lg py-1 z-50">
                                    {e.items.map((i) => (
                                        <a key={i.href} href={i.href}
                                            className={`block px-4 py-2 text-sm transition ${
                                                aktif(i.href) ? "text-blue-700 font-semibold bg-blue-50" : "text-slate-700 hover:bg-slate-50"
                                            }`}>
                                            {i.label}
                                        </a>
                                    ))}
                                </div>
                            )}
                        </div>
                    ) : (
                        <a key={e.href} href={e.href}
                            className={`px-3 py-2 rounded-md text-sm font-medium transition ${
                                aktif(e.href) ? "text-blue-700 bg-blue-50" : "text-slate-600 hover:text-blue-600 hover:bg-slate-50"
                            }`}>
                            {e.label}
                        </a>
                    )
                )}
            </nav>

            {/* ---------- Mobile / tablet (< lg): tombol hamburger ---------- */}
            <button
                onClick={() => setDrawerOpen((v) => !v)}
                aria-label="Menu"
                className="lg:hidden p-2 -ml-1 rounded-md text-slate-600 hover:bg-slate-100"
            >
                {drawerOpen ? (
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                ) : (
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                    </svg>
                )}
            </button>

            {/* ---------- Mobile drawer ---------- */}
            {drawerOpen && (
                <>
                    <div className="lg:hidden fixed inset-0 top-16 bg-black/30 z-40" onClick={() => setDrawerOpen(false)} />
                    <div className="lg:hidden fixed left-0 right-0 top-16 max-h-[calc(100vh-4rem)] overflow-y-auto bg-white border-b border-slate-200 shadow-lg z-40 px-4 py-3 space-y-4">
                        {entries.map((e) =>
                            isGroup(e) ? (
                                <div key={e.label}>
                                    <p className="px-2 text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1">{e.label}</p>
                                    <div className="space-y-0.5">
                                        {e.items.map((i) => (
                                            <a key={i.href} href={i.href}
                                                className={`block px-3 py-2.5 rounded-lg text-sm transition ${
                                                    aktif(i.href) ? "text-blue-700 font-semibold bg-blue-50" : "text-slate-700 hover:bg-slate-50"
                                                }`}>
                                                {i.label}
                                            </a>
                                        ))}
                                    </div>
                                </div>
                            ) : (
                                <a key={e.href} href={e.href}
                                    className={`block px-3 py-2.5 rounded-lg text-sm font-medium transition ${
                                        aktif(e.href) ? "text-blue-700 bg-blue-50" : "text-slate-700 hover:bg-slate-50"
                                    }`}>
                                    {e.label}
                                </a>
                            )
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
