"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { GoogleLogin, GoogleOAuthProvider } from "@react-oauth/google";

export default function LoginPage() {
    const router = useRouter();
    const [error, setError] = useState<string | null>(null);

    const handleSuccess = async (credentialResponse: any) => {
        try {
            const res = await fetch("https://absen.smkn2malinau.sch.id/auth/login/google", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ google_id_token: credentialResponse.credential }),
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Login gagal");

            localStorage.setItem("token", data.access_token);
            router.push("/guru");
        } catch (err: any) {
            setError(err.message);
        }
    };

    return (
        <GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || ""}>
            <div className="flex min-h-[80vh] items-center justify-center">
                <div className="p-8 bg-white rounded-lg shadow-md text-center">
                    <h2 className="text-2xl font-bold mb-6">Login Admin Absensi</h2>
                    {error && <p className="text-red-600 mb-4">{error}</p>}
                    <GoogleLogin onSuccess={handleSuccess} onError={() => setError("Login Google gagal")} />
                </div>
            </div>
        </GoogleOAuthProvider>
    );
}
