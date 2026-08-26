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
                className="bg-white text-blue-600 px-3 py-1 rounded font-semibold hover:bg-gray-100 transition"
            >
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
                className="flex items-center gap-2 bg-white/10 hover:bg-white/20 px-2 py-1 rounded-full transition"
            >
                <span className="w-8 h-8 rounded-full bg-white text-blue-600 flex items-center justify-center font-bold">
                    {initial}
                </span>
                <span className="hidden sm:block text-sm font-medium max-w-[160px] truncate">
                    {user.nama}
                </span>
                <svg
                    className={`w-4 h-4 transition-transform ${open ? "rotate-180" : ""}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
            </button>

            {open && (
                <div className="absolute right-0 mt-2 w-56 bg-white rounded-lg shadow-lg text-gray-800 overflow-hidden z-50">
                    <div className="px-4 py-3 border-b">
                        <p className="font-semibold truncate">{user.nama}</p>
                        <p className="text-sm text-gray-500 truncate">{user.email}</p>
                        <span className="inline-block mt-1 px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full capitalize">
                            {user.role.replace(/_/g, " ")}
                        </span>
                    </div>
                    <button
                        onClick={handleLogout}
                        disabled={loggingOut}
                        className="w-full text-left px-4 py-2.5 text-red-600 hover:bg-red-50 transition disabled:opacity-50"
                    >
                        {loggingOut ? "Keluar..." : "Logout"}
                    </button>
                </div>
            )}
        </div>
    );
}
