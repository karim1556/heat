"use client";

import React from "react";
import Link from "next/link";
import { useAuth } from "./AuthProvider";
import { LogIn, LogOut, User, Users, Landmark } from "lucide-react";

export default function UserNav() {
  const { user, logout } = useAuth();

  if (!user) {
    return (
      <Link
        href="/login"
        className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-slate-900 text-white text-xs font-bold hover:bg-slate-800 transition-all shadow-sm"
      >
        <LogIn className="w-3.5 h-3.5 text-amber-400" />
        <span>Log In</span>
      </Link>
    );
  }

  const isManager = user.role === "group_manager";

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white border border-slate-200 shadow-xs text-xs">
        <div className={`w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] text-white ${
          isManager ? "bg-amber-500" : "bg-sky-500"
        }`}>
          {isManager ? <Users className="w-3 h-3" /> : <Landmark className="w-3 h-3" />}
        </div>
        <div className="flex flex-col">
          <span className="font-bold text-slate-900 text-[11px] leading-tight">{user.name}</span>
          <span className="text-[9px] uppercase font-semibold text-slate-500 tracking-wider">
            {isManager ? "Site Head" : "Insurer"}
          </span>
        </div>
      </div>

      <button
        onClick={logout}
        className="p-2 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors"
        title="Log Out"
      >
        <LogOut className="w-3.5 h-3.5 text-slate-600" />
      </button>
    </div>
  );
}
