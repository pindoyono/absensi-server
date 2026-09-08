import type { Metadata } from "next";
import { Geist } from "next/font/google";
import UserMenu from "./components/UserMenu";
import Nav from "./components/Nav";
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
        <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex h-16 items-center gap-2 sm:gap-4">
              {/* Menu: hamburger di mobile/tablet, link dropdown di desktop */}
              <Nav />

              {/* Logo / Title */}
              <a href="/" className="flex items-center gap-2.5 min-w-0">
                <div className="w-9 h-9 shrink-0 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-lg shadow-sm">
                  S2
                </div>
                <div className="min-w-0 leading-tight">
                  <h1 className="text-sm sm:text-base font-bold text-slate-900 truncate">Absensi Admin</h1>
                  <p className="text-xs text-slate-500 truncate hidden sm:block">SMKN 2 Malinau</p>
                </div>
              </a>

              <div className="flex-1" />

              {/* User Menu */}
              <UserMenu />
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
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
