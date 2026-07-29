"use client";

import React, { useState, useEffect } from "react";
import { Shield, Users, Landmark, UserCheck, Key } from "lucide-react";

export type Role = "group_manager" | "insurance_provider" | "public";

export function getActiveRole(): Role {
  if (typeof window === "undefined") return "group_manager";
  return (localStorage.getItem("heat_user_role") as Role) || "group_manager";
}

export function setActiveRole(role: Role) {
  if (typeof window === "undefined") return;
  localStorage.setItem("heat_user_role", role);
  window.dispatchEvent(new Event("role_changed"));
}

export function getAuthHeaders(): Record<string, string> {
  const role = getActiveRole();
  return {
    "X-Role": role,
    "Authorization": `Bearer token-${role}`
  };
}

export default function RoleSwitcher() {
  const [role, setRole] = useState<Role>("group_manager");

  useEffect(() => {
    setRole(getActiveRole());

    const handleRoleChange = () => setRole(getActiveRole());
    window.addEventListener("role_changed", handleRoleChange);
    return () => window.removeEventListener("role_changed", handleRoleChange);
  }, []);

  const handleSelectRole = (newRole: Role) => {
    setActiveRole(newRole);
    setRole(newRole);
  };

  return (
    <div className="flex items-center gap-1.5 bg-slate-900 text-white p-1 rounded-full border border-slate-700 shadow-sm text-xs font-semibold">
      <div className="flex items-center gap-1 pl-2 pr-1 text-slate-400 font-mono text-[10px]">
        <Key className="w-3 h-3 text-amber-400" />
        <span>ROLE:</span>
      </div>

      <button
        onClick={() => handleSelectRole("group_manager")}
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-all ${
          role === "group_manager"
            ? "bg-amber-500 text-slate-950 font-bold shadow-xs"
            : "text-slate-300 hover:text-white"
        }`}
        title="Group Manager Role"
      >
        <Users className="w-3 h-3" />
        <span className="hidden sm:inline">Manager</span>
      </button>

      <button
        onClick={() => handleSelectRole("insurance_provider")}
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-all ${
          role === "insurance_provider"
            ? "bg-sky-500 text-slate-950 font-bold shadow-xs"
            : "text-slate-300 hover:text-white"
        }`}
        title="Insurance Provider Role"
      >
        <Landmark className="w-3 h-3" />
        <span className="hidden sm:inline">Insurer</span>
      </button>

      <button
        onClick={() => handleSelectRole("public")}
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full transition-all ${
          role === "public"
            ? "bg-slate-700 text-white font-bold"
            : "text-slate-300 hover:text-white"
        }`}
        title="Public / Worker Role"
      >
        <UserCheck className="w-3 h-3" />
        <span className="hidden sm:inline">Public</span>
      </button>
    </div>
  );
}
