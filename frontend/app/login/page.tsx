"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { GoogleLogin, GoogleOAuthProvider } from "@react-oauth/google";

const API_BASE = "https://absen.smkn2malinau.sch.id";

export default function LoginPage() {
    const router = useRouter();
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    const handleGoogleSuccess = async (credentialResponse: any) => {
        setIsLoading(true);
        try {
            const res = await fetch(`${API_BASE}/auth/login/google`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ google_id_token: credentialResponse.credential }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Login Google gagal");
            localStorage.setItem("token", data.access_token);
            router.push("/");
        } catch (err: any) {
            setError(err.message);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || ""}>
            <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
                <div className="w-full max-w-md">
                    {/* Logo / Branding */}
                    <div className="text-center mb-8">
                        <div className="w-16 h-16 rounded-xl bg-blue-600 text-white flex items-center justify-center font-bold text-2xl mx-auto mb-3 shadow-lg">
                            S2
                        </div>
                        <h1 className="text-2xl font-bold text-slate-900">Absensi Admin</h1>
                        <p className="text-sm text-slate-500 mt-1">SMKN 2 Malinau</p>
                    </div>

                    {/* Login Card */}
                    <div className="bg-white rounded-xl shadow-md border border-slate-200 p-8 space-y-5">
                        <h2 className="text-xl font-semibold text-center text-slate-800">Masuk ke Akun Anda</h2>
                        <p className="text-sm text-slate-500 text-center">
                            Gunakan akun Google sekolah Anda untuk masuk
                        </p>

                        {error && (
                            <div className="p-3 bg-rose-50 text-rose-700 rounded-lg text-sm border border-rose-200">
                                {error}
                            </div>
                        )}

                        <div className="flex justify-center">
                            {isLoading ? (
                                <div className="flex items-center gap-2 text-sm text-slate-500">
                                    <svg className="animate-spin h-5 w-5 text-blue-600" fill="none" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                    </svg>
                                    Memproses login...
                                </div>
                            ) : (
                                <GoogleLogin onSuccess={handleGoogleSuccess} onError={() => setError("Login Google gagal")} />
                            )}
                        </div>
                    </div>

                    <p className="text-center text-xs text-slate-500 mt-6">
                        © 2026 SMKN 2 Malinau — Sistem Presensi Berbasis Wajah
                    </p>
                </div>
            </div>
        </GoogleOAuthProvider>
    );
}
