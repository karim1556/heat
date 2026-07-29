"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { supabase } from "@/lib/supabase";

export type UserRole = "group_manager" | "insurance_provider" | "super_admin";

export interface UserSession {
  token: string;
  email: string;
  name: string;
  role: UserRole;
  orgName?: string;
}

export interface AuthResult {
  success: boolean;
  needsEmailConfirmation?: boolean;
  message?: string;
}

interface AuthContextType {
  user: UserSession | null;
  loading: boolean;
  login: (role: UserRole, email: string, password: string, name?: string, orgName?: string) => Promise<AuthResult>;
  signUp: (role: UserRole, email: string, password: string, name: string, orgName?: string, sector?: string) => Promise<AuthResult>;
  logout: () => Promise<void>;
  getAuthHeaders: () => Record<string, string>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const syncUserToPublicTable = async (supabaseUser: any, sessionObj: UserSession) => {
  try {
    const { data, error } = await supabase
      .from("users")
      .select("id")
      .eq("id", supabaseUser.id)
      .maybeSingle();

    if (error) {
      console.warn("Supabase public.users check note:", error.message);
      return;
    }

    if (!data) {
      console.log("Syncing missing user to public.users:", sessionObj.email);
      const { error: insertError } = await supabase.from("users").insert([
        {
          id: supabaseUser.id,
          email: sessionObj.email,
          name: sessionObj.name,
          role: sessionObj.role,
          org_name: sessionObj.orgName || null,
          sector: supabaseUser.user_metadata?.sector || null,
          status: "active"
        }
      ]);
      if (insertError) {
        console.warn("Failed to auto-sync user to public.users:", insertError.message);
      } else {
        console.log("Successfully auto-synced user to public.users!");
      }
    }
  } catch (e) {
    console.warn("Sync user exception:", e);
  }
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserSession | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check initial Supabase Session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        const metadata = session.user.user_metadata || {};
        const sessObj: UserSession = {
          token: session.access_token,
          email: session.user.email || "",
          name: metadata.name || session.user.email?.split("@")[0] || "User",
          role: metadata.role || "group_manager",
          orgName: metadata.orgName
        };
        setUser(sessObj);
        syncUserToPublicTable(session.user, sessObj);
      } else {
        setUser(null);
      }
      setLoading(false);
    });

    // Listen for Supabase Auth state changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        const metadata = session.user.user_metadata || {};
        const sessObj: UserSession = {
          token: session.access_token,
          email: session.user.email || "",
          name: metadata.name || session.user.email?.split("@")[0] || "User",
          role: metadata.role || "group_manager",
          orgName: metadata.orgName
        };
        setUser(sessObj);
        localStorage.setItem("heat_user_session", JSON.stringify(sessObj));
        syncUserToPublicTable(session.user, sessObj);
      } else {
        setUser(null);
        localStorage.removeItem("heat_user_session");
      }
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  const signUp = async (role: UserRole, email: string, password: string, name: string, orgName?: string, sector?: string): Promise<AuthResult> => {
    setLoading(true);
    try {
      // Call our server-side API route which uses the Supabase service role key
      // to create the user with email_confirm=true — no email sent, instant access.
      const res = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, name, role, orgName, sector }),
      });

      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.error || "Signup failed");
      }

      // Set the Supabase session so the client SDK is properly authenticated
      const { session, user: apiUser } = json;
      await supabase.auth.setSession({
        access_token: session.access_token,
        refresh_token: session.refresh_token,
      });

      const sessObj: UserSession = {
        token: session.access_token,
        email: apiUser.email,
        name: apiUser.name,
        role: apiUser.role,
        orgName: apiUser.orgName || undefined,
      };
      setUser(sessObj);
      localStorage.setItem("heat_user_session", JSON.stringify(sessObj));
      return { success: true };
    } catch (err: any) {
      throw err;
    } finally {
      setLoading(false);
    }
  };


  const login = async (role: UserRole, email: string, password: string, name?: string, orgName?: string): Promise<AuthResult> => {
    setLoading(true);
    try {
      // --- DEMO ACCOUNTS BYPASS ---
      // These users exist in the public.users database table but not in Supabase Auth,
      // so we bypass the Auth check to allow the demo to work seamlessly.
      if (email === "rajesh.kumar@quicklogistics.in") {
        const sessObj: UserSession = {
          token: "mgr-session-active",
          email: email,
          name: "Rajesh Kumar",
          role: "group_manager",
          orgName: "Swiggy Bandra Delivery Fleet"
        };
        setUser(sessObj);
        localStorage.setItem("heat_user_session", JSON.stringify(sessObj));
        return { success: true };
      }
      if (email === "underwriter@icicilombard.com") {
        const sessObj: UserSession = {
          token: "ins-session-active",
          email: email,
          name: "ICICI Lombard Climate Risk Desk",
          role: "insurance_provider",
          orgName: "ICICI Lombard GIC Ltd"
        };
        setUser(sessObj);
        localStorage.setItem("heat_user_session", JSON.stringify(sessObj));
        return { success: true };
      }
      if (email === "admin@pricingtheheat.com") {
        const sessObj: UserSession = {
          token: "mock-token-admin",
          email: email,
          name: "Master Platform Admin",
          role: "super_admin",
          orgName: "Pricing the Heat Core"
        };
        setUser(sessObj);
        localStorage.setItem("heat_user_session", JSON.stringify(sessObj));
        return { success: true };
      }
      // --- END DEMO BYPASS ---

      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password
      });

      if (error) {
        throw new Error(
          error.message === "Invalid login credentials"
            ? "Incorrect email or password. Please try again."
            : error.message
        );
      }

      if (data?.session?.user) {
        const metadata = data.session.user.user_metadata || {};
        const sessObj: UserSession = {
          token: data.session.access_token,
          email: data.session.user.email || email,
          name: metadata.name || name || email.split("@")[0],
          role: metadata.role || role,
          orgName: metadata.orgName || orgName
        };
        setUser(sessObj);
        localStorage.setItem("heat_user_session", JSON.stringify(sessObj));
        return { success: true };
      }

      return { success: false, message: "Login failed. Please try again." };
    } catch (err: any) {
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    try {
      await supabase.auth.signOut();
    } catch (e) {}
    setUser(null);
    localStorage.removeItem("heat_user_session");
    setLoading(false);
  };

  const getAuthHeaders = (): Record<string, string> => {
    if (!user) {
      return { "X-Role": "public" };
    }
    return {
      "Authorization": `Bearer ${user.token}`,
      "X-Role": user.role,
      "X-User-Email": user.email
    };
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, signUp, logout, getAuthHeaders }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
