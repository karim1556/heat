-- ====================================================================
-- PRICING THE HEAT: PARAMETRIC MICRO-INSURANCE PLATFORM SCHEMAS
-- Execute this SQL script in your Supabase SQL Editor
-- (Supabase Dashboard -> SQL Editor -> New Query -> Run)
-- ====================================================================

-- 1. Users & Accounts Table (Registered Group Managers, Insurers, Super Admins)
CREATE TABLE IF NOT EXISTS public.users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'group_manager', -- 'group_manager', 'insurance_provider', 'super_admin'
    org_name TEXT,
    sector TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Cohorts Table (Worksite / Delivery / Vendor Groups)
CREATE TABLE IF NOT EXISTS public.cohorts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    manager_name TEXT NOT NULL,
    manager_email TEXT NOT NULL,
    sector TEXT NOT NULL,
    location_name TEXT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Workers Table (Field workers, delivery boys, street vendors)
CREATE TABLE IF NOT EXISTS public.workers (
    id TEXT PRIMARY KEY,
    cohort_id TEXT NOT NULL REFERENCES public.cohorts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    payment_upi TEXT NOT NULL,
    payment_method TEXT DEFAULT 'UPI',
    status TEXT DEFAULT 'active',
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Policy Templates Table (Underwritten by Insurance Providers)
CREATE TABLE IF NOT EXISTS public.policy_templates (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    sector TEXT NOT NULL,
    temperature_threshold_c DOUBLE PRECISION NOT NULL,
    duration_days INTEGER NOT NULL,
    payout_amount_inr DOUBLE PRECISION NOT NULL,
    premium_monthly_inr DOUBLE PRECISION NOT NULL,
    provider_name TEXT NOT NULL,
    description TEXT NOT NULL
);

-- 5. Active Policies Table (Purchased by Group Managers)
CREATE TABLE IF NOT EXISTS public.active_policies (
    id TEXT PRIMARY KEY,
    cohort_id TEXT NOT NULL REFERENCES public.cohorts(id) ON DELETE CASCADE,
    policy_template_id TEXT NOT NULL REFERENCES public.policy_templates(id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    covered_workers_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active'
);

-- 6. Payout Events Table (Weather Triggers & One-Tap Autopay Approvals)
CREATE TABLE IF NOT EXISTS public.payout_events (
    id TEXT PRIMARY KEY,
    active_policy_id TEXT NOT NULL REFERENCES public.active_policies(id),
    cohort_id TEXT NOT NULL REFERENCES public.cohorts(id),
    trigger_temperature_c DOUBLE PRECISION NOT NULL,
    trigger_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    total_amount_inr DOUBLE PRECISION NOT NULL,
    per_worker_amount_inr DOUBLE PRECISION NOT NULL,
    status TEXT DEFAULT 'pending_approval',
    approved_at TIMESTAMP WITH TIME ZONE,
    approved_by TEXT
);

-- 7. Enterprise Partner Keys Table (Managed by Platform Super Admin)
CREATE TABLE IF NOT EXISTS public.enterprise_keys (
    id TEXT PRIMARY KEY,
    partner_name TEXT NOT NULL,
    key_code TEXT UNIQUE NOT NULL,
    tier TEXT DEFAULT 'enterprise',
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed initial default users
INSERT INTO public.users (id, email, name, role, org_name, sector, status)
VALUES 
    ('usr-01', 'admin@pricingtheheat.com', 'Master Platform Admin', 'super_admin', 'Pricing the Heat Core', 'platform', 'active'),
    ('usr-02', 'rajesh.kumar@quicklogistics.in', 'Rajesh Kumar', 'group_manager', 'Swiggy Bandra Delivery Fleet', 'delivery', 'active'),
    ('usr-03', 'underwriter@icicilombard.com', 'ICICI Lombard Climate Risk Desk', 'insurance_provider', 'ICICI Lombard GIC Ltd', 'insurance', 'active')
ON CONFLICT (email) DO NOTHING;

-- Seed initial enterprise partner keys
INSERT INTO public.enterprise_keys (id, partner_name, key_code, tier, status)
VALUES 
    ('key-01', 'ICICI Lombard Climate Risk Desk', 'ICICI-LOMBARD-PARAMETRIC', 'tier1', 'active'),
    ('key-02', 'HDFC ERGO Micro-Protect', 'HDFC-PARTNER-2026', 'tier1', 'active'),
    ('key-03', 'Tata AIG Parametric Unit', 'TATA-AIG-CLIMATE', 'enterprise', 'active')
ON CONFLICT (key_code) DO NOTHING;

-- Enable Row Level Security (RLS)
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cohorts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.policy_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.active_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payout_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.enterprise_keys ENABLE ROW LEVEL SECURITY;

-- Set up permissive policies for API backend access
CREATE POLICY "Allow full access users" ON public.users FOR ALL USING (true);
CREATE POLICY "Allow full access cohorts" ON public.cohorts FOR ALL USING (true);
CREATE POLICY "Allow full access workers" ON public.workers FOR ALL USING (true);
CREATE POLICY "Allow full access policy_templates" ON public.policy_templates FOR ALL USING (true);
CREATE POLICY "Allow full access active_policies" ON public.active_policies FOR ALL USING (true);
CREATE POLICY "Allow full access payout_events" ON public.payout_events FOR ALL USING (true);
CREATE POLICY "Allow full access enterprise_keys" ON public.enterprise_keys FOR ALL USING (true);
