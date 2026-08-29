import type { Metadata } from "next";
import { Geist } from "next/font/google";
import UserMenu from "./components/UserMenu";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Absensi Admin — SMKN 2 Malinau",
  description: "Panel Kontrol Presensi & Dispensasi SMKN 2 Malinau",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id" className="h-full antialiased">
      <body className={`${geistSans.variable} font-sans min-h-full flex flex-col bg-slate-50 text-slate-800`}>
        {/* Top Navbar */}
        <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-16 items-center">
              {/* Logo / Title */}
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-lg shadow-sm">
                  S2
                </div>
                <div>
                  <h1 className="text-base font-bold text-slate-900 leading-tight">Absensi Admin</h1>
                  <p className="text-xs text-slate-500">SMKN 2 Malinau</p>
                </div>
              </div>

              {/* Navigation Links */}
              <nav className="hidden md:flex items-center space-x-1">
                <a
                  href="/"
                  className="px-3 py-2 rounded-md text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50 transition"
                >
                  Dashboard
                </a>
                <a
                  href="/guru"
                  className="px-3 py-2 rounded-md text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50 transition"
                >
                  Guru
                </a>
                <a
                  href="/siswa"
                  className="px-3 py-2 rounded-md text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50 transition"
                >
                  Siswa
                </a>
                <a
                  href="/jadwal"
                  className="px-3 py-2 rounded-md text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50 transition"
                >
                  Jadwal
                </a>
                <a
                  href="/dispensasi"
                  className="px-3 py-2 rounded-md text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50 transition"
                >
                  Dispensasi
                </a>
                <a
                  href="/absensi"
                  className="px-3 py-2 rounded-md text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50 transition"
                >
                  Absensi
                </a>
                <a
                  href="/konsentrasi"
                  className="px-3 py-2 rounded-md text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50 transition"
                >
                  Spektrum
                </a>
              </nav>

              {/* User Menu */}
              <div className="flex items-center gap-2">
                <UserMenu />
              </div>
            </div>
          </div>
        </header>

        {/* Mobile Subnav */}
        <div className="md:hidden bg-slate-100 border-b border-slate-200 px-4 py-2 flex justify-around text-xs font-medium">
          <a href="/" className="text-slate-600 hover:text-blue-600">Dashboard</a>
          <a href="/guru" className="text-slate-600 hover:text-blue-600">Guru</a>
          <a href="/siswa" className="text-slate-600 hover:text-blue-600">Siswa</a>
          <a href="/jadwal" className="text-slate-600 hover:text-blue-600">Jadwal</a>
          <a href="/dispensasi" className="text-slate-600 hover:text-blue-600">Dispensasi</a>
          <a href="/absensi" className="text-slate-600 hover:text-blue-600">Absensi</a>
          <a href="/konsentrasi" className="text-slate-600 hover:text-blue-600">Spektrum</a>
        </div>

        {/* Main Content Area */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>

        {/* Footer */}
        <footer className="bg-white border-t border-slate-200 py-4 text-center text-xs text-slate-500">
          © 2026 SMKN 2 Malinau. Sistem Presensi Berbasis Pengenalan Wajah.
        </footer>
      </body>
    </html>
  );
}
