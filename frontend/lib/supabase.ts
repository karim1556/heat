import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://mhkpgnuvdfetkxvppcbo.supabase.co";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1oa3BnbnV2ZGZldGt4dnBwY2JvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUyNTE3MjAsImV4cCI6MjEwMDgyNzcyMH0.ww6-jy7Yxw8xVnjVQ_PjtjuIbeTByTBPJLCU2FT3k8g";

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
