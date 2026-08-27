"use client";

import { useState, useEffect, useRef } from "react";

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface UserInfo {
    nama: string;
    email: string;
    role: string;
}

export default function UserMenu() {
    const [token, setToken] = useState<string | null>(null);
    const [user, setUser] = useState<UserInfo | null>(null);
    const [open, setOpen] = useState(false);
    const [loggingOut, setLoggingOut] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);

    // Ambil token dari localStorage (client-only)
    useEffect(() => {
        const t = localStorage.getItem("token");
        setToken(t);
    }, []);

    // Ambil profil user saat token tersedia
    useEffect(() => {
        if (!token) {
            setUser(null);
            return;
        }
        let cancelled = false;
        fetch(`${API_BASE}/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
        })
            .then((res) => (res.ok ? res.json() : null))
            .then((data) => {
                if (!cancelled && data && data.email) {
                    setUser({ nama: data.nama, email: data.email, role: data.role });
                }
            })
            .catch(() => { });
        return () => {
            cancelled = true;
        };
    }, [token]);

    // Tutup dropdown saat klik di luar
    useEffect(() => {
        const onClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener("mousedown", onClickOutside);
        return () => document.removeEventListener("mousedown", onClickOutside);
    }, []);

    const handleLogout = () => {
        setLoggingOut(true);
        localStorage.removeItem("token");
        window.location.href = "/login";
    };

    // Belum login → tombol Login biasa
    if (!token || !user) {
        return (
            <a
                href="/login"
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 transition"
            >
                <span className="w-6 h-6 rounded-full bg-slate-300 flex items-center justify-center text-xs">?</span>
                Login
            </a>
        );
    }

    // Sudah login → avatar + dropdown
    const initial = user.nama?.charAt(0).toUpperCase() || "?";

    return (
        <div className="relative" ref={menuRef}>
            <button
                onClick={() => setOpen((v) => !v)}
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-slate-100 transition text-sm"
            >
                <span className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-sm">
                    {initial}
                </span>
                <span className="hidden sm:block text-slate-700 font-medium max-w-[120px] truncate">
                    {user.nama}
                </span>
                <svg
                    className={`w-4 h-4 text-slate-500 transition-transform ${open ? "rotate-180" : ""}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
            </button>

            {open && (
                <div className="absolute right-0 mt-2 w-56 bg-white border border-slate-200 rounded-xl shadow-lg py-1 z-50">
                    <div className="px-4 py-3 border-b border-slate-100">
                        <p className="font-semibold text-slate-900 truncate">{user.nama}</p>
                        <p className="text-xs text-slate-500 truncate mt-0.5">{user.email}</p>
                        <span className="inline-block mt-1.5 px-2 py-0.5 bg-slate-100 text-slate-700 text-xs rounded-full capitalize font-medium">
                            {user.role.replace(/_/g, " ")}
                        </span>
                    </div>
                    <button
                        onClick={handleLogout}
                        disabled={loggingOut}
                        className="w-full text-left px-4 py-2.5 text-sm text-rose-600 hover:bg-rose-50 transition font-medium disabled:opacity-50"
                    >
                        {loggingOut ? "Keluar..." : "Logout"}
                    </button>
                </div>
            )}
        </div>
    );
}
