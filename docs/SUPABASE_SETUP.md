# Supabase Database & Environment Setup Guide

This guide explains how to connect **Pricing the Heat (Parametric Micro-Insurance)** directly to a cloud **Supabase** instance.

---

## 1. Environment Variables Configuration

Copy `.env.example` to `.env` in the repository root:

```bash
# Backend Environment (.env)
SUPABASE_URL="https://your-project-ref.supabase.co"
SUPABASE_KEY="your-supabase-anon-or-service-role-key"

# Optional configuration
AUTH_SECRET="your-production-secret-jwt-key"
FRONTEND_ORIGIN="http://localhost:3000"
PORT=8000
```

For the frontend (`frontend/.env.local`):

```bash
NEXT_PUBLIC_API_URL="http://localhost:8000"
NEXT_PUBLIC_SUPABASE_URL="https://your-project-ref.supabase.co"
NEXT_PUBLIC_SUPABASE_ANON_KEY="your-supabase-anon-key"
```

---

## 2. Supabase SQL Schema Script

Run the following SQL script inside your **Supabase SQL Editor** (SQL Editor -> New Query -> Run) to set up all parametric tables with Row Level Security (RLS) enabled:

```sql
-- 1. Cohorts Table (Worksite / Delivery / Vendor Groups)
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

-- 2. Workers Table
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

-- 3. Policy Templates Table (Created by Insurers)
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

-- 4. Active Policies Table (Purchased by Managers)
CREATE TABLE IF NOT EXISTS public.active_policies (
    id TEXT PRIMARY KEY,
    cohort_id TEXT NOT NULL REFERENCES public.cohorts(id) ON DELETE CASCADE,
    policy_template_id TEXT NOT NULL REFERENCES public.policy_templates(id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    covered_workers_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active'
);

-- 5. Payout Events Table (Weather Triggers & Autopay Approvals)
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

-- Enable RLS for all tables
ALTER TABLE public.cohorts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.policy_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.active_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payout_events ENABLE ROW LEVEL SECURITY;

-- Allow Public / Anonymous Access for demo endpoints
CREATE POLICY "Allow public read cohorts" ON public.cohorts FOR SELECT USING (true);
CREATE POLICY "Allow public insert cohorts" ON public.cohorts FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow public read workers" ON public.workers FOR SELECT USING (true);
CREATE POLICY "Allow public insert workers" ON public.workers FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow public read policy_templates" ON public.policy_templates FOR SELECT USING (true);
CREATE POLICY "Allow public insert policy_templates" ON public.policy_templates FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow public read active_policies" ON public.active_policies FOR SELECT USING (true);
CREATE POLICY "Allow public insert active_policies" ON public.active_policies FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow public read payout_events" ON public.payout_events FOR SELECT USING (true);
CREATE POLICY "Allow public update payout_events" ON public.payout_events FOR UPDATE USING (true);
```

---

## 3. How Dual Persistence Works
- When `SUPABASE_URL` and `SUPABASE_KEY` are provided in `.env`, the FastAPI backend automatically uses your live Supabase cloud database.
- When omitted, it automatically falls back to local SQLite (`data/parametric.db`), ensuring zero downtime or configuration friction!
