import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

// Admin client — uses service role key, runs ONLY on the server
// Never expose SUPABASE_SERVICE_ROLE_KEY to the browser (no NEXT_PUBLIC_ prefix)
const supabaseAdmin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!,
  {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  }
);

export async function POST(req: NextRequest) {
  try {
    const { email, password, name, role, orgName, sector } = await req.json();

    // Basic validation
    if (!email || !password || !name || !role) {
      return NextResponse.json(
        { error: "email, password, name, and role are required" },
        { status: 400 }
      );
    }

    if (password.length < 6) {
      return NextResponse.json(
        { error: "Password must be at least 6 characters" },
        { status: 400 }
      );
    }

    // 1. Create user with admin API — email_confirm: true means NO email is sent,
    //    and the user is immediately confirmed and can log in right away.
    const { data: adminData, error: adminError } =
      await supabaseAdmin.auth.admin.createUser({
        email,
        password,
        email_confirm: true, // ← this is the magic: skip email confirmation
        user_metadata: { name, role, orgName, sector },
      });

    if (adminError) {
      // If user already exists in auth, surface a clean error
      if (
        adminError.message.includes("already been registered") ||
        adminError.message.includes("already exists") ||
        adminError.message.includes("duplicate")
      ) {
        return NextResponse.json(
          { error: "An account with this email already exists. Please sign in." },
          { status: 409 }
        );
      }
      return NextResponse.json({ error: adminError.message }, { status: 400 });
    }

    const createdUser = adminData.user;

    // 2. Insert into public.users table
    if (createdUser) {
      const { error: dbError } = await supabaseAdmin.from("users").insert([
        {
          id: createdUser.id,
          email: email,
          name: name,
          role: role,
          org_name: orgName || null,
          sector: sector || null,
          status: "active",
        },
      ]);

      if (dbError) {
        console.warn("public.users insert warning:", dbError.message);
        // Don't fail the whole signup — auth user was created successfully
      }
    }

    // 3. Now sign in as this user to get a real session token
    //    (admin createUser doesn't return a session, so we do a fresh signIn)
    const { data: signInData, error: signInError } =
      await supabaseAdmin.auth.signInWithPassword({ email, password });

    if (signInError || !signInData.session) {
      // User was created but couldn't get session — shouldn't happen, but handle it
      return NextResponse.json(
        {
          error:
            "Account created but could not log in automatically. Please sign in manually.",
        },
        { status: 500 }
      );
    }

    // Return session + user info to the client
    return NextResponse.json({
      session: {
        access_token: signInData.session.access_token,
        refresh_token: signInData.session.refresh_token,
        expires_at: signInData.session.expires_at,
      },
      user: {
        id: createdUser!.id,
        email,
        name,
        role,
        orgName: orgName || null,
      },
    });
  } catch (err: any) {
    console.error("Signup API error:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
