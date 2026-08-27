"use client";

import { useState, useEffect } from "react";
import { Skeleton } from "@/components/ui/Base";

const API_BASE = "https://absen.smkn2malinau.sch.id";

interface StatCard {
  title: string;
  value: string;
  icon: string;
  color: string;
}

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<StatCard[]>([]);
  const [recentDispensasi, setRecentDispensasi] = useState<any[]>([]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      window.location.href = "/login";
      return;
    }

    const fetchData = async () => {
      try {
        // Fetch guru list for stat
        const guruRes = await fetch(`${API_BASE}/guru`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const guruData = await guruRes.json();

        // Fetch dispensasi for today
        const today = new Date().toISOString().split("T")[0];
        const dispRes = await fetch(`${API_BASE}/dispensasi/aktif?tanggal=${today}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const dispData = await dispRes.json();

        setStats([
          { title: "Total Guru", value: String(guruData.length || 0), icon: "👨‍🏫", color: "bg-blue-500" },
          { title: "Dispensasi Hari Ini", value: String(dispData.length || 0), icon: "📋", color: "bg-amber-500" },
          { title: "Guru Aktif", value: String(guruData.filter((g: any) => g.aktif).length || 0), icon: "✅", color: "bg-emerald-500" },
        ]);
        setRecentDispensasi(dispData.slice(0, 5));
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48 mb-4" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="h-64 w-full mt-6" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">Ringkasan presensi & dispensasi hari ini</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {stats.map((stat) => (
          <div key={stat.title} className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex items-center gap-4">
            <div className={`w-10 h-10 rounded-lg ${stat.color} flex items-center justify-center text-white text-xl`}>
              {stat.icon}
            </div>
            <div>
              <p className="text-sm text-slate-500">{stat.title}</p>
              <p className="text-2xl font-bold text-slate-900">{stat.value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Recent Dispensasi */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
        <h2 className="text-lg font-semibold text-slate-900 mb-3">Dispensasi Terbaru</h2>
        {recentDispensasi.length === 0 ? (
          <p className="text-sm text-slate-500">Tidak ada dispensasi untuk hari ini.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 uppercase">
                  <th className="pb-2">Tanggal</th>
                  <th className="pb-2">Jenis</th>
                  <th className="pb-2">Kategori</th>
                  <th className="pb-2">Alasan</th>
                </tr>
              </thead>
              <tbody>
                {recentDispensasi.map((d) => (
                  <tr key={d.id} className="border-t border-slate-100">
                    <td className="py-2 text-slate-700">{d.tanggal}</td>
                    <td className="py-2 text-slate-700">{d.jenis}</td>
                    <td className="py-2">
                      <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                        {d.kategori}
                      </span>
                    </td>
                    <td className="py-2 text-slate-600">{d.alasan || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
