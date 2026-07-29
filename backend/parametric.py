"""Parametric Insurance & Autopay Module for Heat micro-insurance.
Provides data management for Cohorts, Workers, Policy Templates, Active Policies,
and One-Tap Autopay Events.
Supports Supabase database integration with automatic fallback to local SQLite for instant zero-config usage.
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# SQLite DB Path for local persistence fallback
DB_PATH = os.environ.get("PARAMETRIC_DB_PATH", "data/parametric.db")

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables and seed initial demo data if empty."""
    conn = get_db()
    cursor = conn.cursor()

    # 0. Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'group_manager',
        org_name TEXT,
        sector TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT NOT NULL
    );
    """)

    # 1. Cohorts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cohorts (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        manager_name TEXT NOT NULL,
        manager_email TEXT NOT NULL,
        sector TEXT NOT NULL,
        location_name TEXT NOT NULL,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    # 2. Workers table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workers (
        id TEXT PRIMARY KEY,
        cohort_id TEXT NOT NULL,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        payment_upi TEXT NOT NULL,
        payment_method TEXT DEFAULT 'UPI',
        status TEXT DEFAULT 'active',
        registered_at TEXT NOT NULL,
        FOREIGN KEY(cohort_id) REFERENCES cohorts(id)
    );
    """)

    # 3. Policy Templates table (Insurance Providers)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS policy_templates (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        sector TEXT NOT NULL,
        temperature_threshold_c REAL NOT NULL,
        duration_days INTEGER NOT NULL,
        payout_amount_inr REAL NOT NULL,
        premium_monthly_inr REAL NOT NULL,
        provider_name TEXT NOT NULL,
        description TEXT NOT NULL
    );
    """)

    # 4. Active Policies table (Purchased by Managers)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS active_policies (
        id TEXT PRIMARY KEY,
        cohort_id TEXT NOT NULL,
        policy_template_id TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        covered_workers_count INTEGER NOT NULL,
        status TEXT DEFAULT 'active',
        FOREIGN KEY(cohort_id) REFERENCES cohorts(id),
        FOREIGN KEY(policy_template_id) REFERENCES policy_templates(id)
    );
    """)

    # 5. Payout Events table (Threshold triggers & Autopay approvals)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payout_events (
        id TEXT PRIMARY KEY,
        active_policy_id TEXT NOT NULL,
        cohort_id TEXT NOT NULL,
        trigger_temperature_c REAL NOT NULL,
        trigger_date TEXT NOT NULL,
        total_amount_inr REAL NOT NULL,
        per_worker_amount_inr REAL NOT NULL,
        status TEXT DEFAULT 'pending_approval',
        approved_at TEXT,
        approved_by TEXT,
        FOREIGN KEY(active_policy_id) REFERENCES active_policies(id),
        FOREIGN KEY(cohort_id) REFERENCES cohorts(id)
    );
    """)

    conn.commit()

    # Check if empty to seed realistic defaults
    cursor.execute("SELECT COUNT(*) as cnt FROM policy_templates;")
    if cursor.fetchone()["cnt"] == 0:
        _seed_default_data(conn)

    conn.close()

def _seed_default_data(conn):
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    # Seed Policy Templates
    templates = [
        ("pol-tmpl-01", "Urban Fleet Heat Shield", "delivery", 42.5, 2, 750.0, 85.0, "ICICI Lombard Climate", "Covers delivery riders when Heat Index exceeds 42.5°C for 2 consecutive days."),
        ("pol-tmpl-02", "Street Vendor Extreme Heat Relief", "street_vendor", 44.0, 1, 500.0, 60.0, "HDFC ERGO Micro-Protect", "Provides immediate daily wage loss compensation for street vendors during extreme heat warnings."),
        ("pol-tmpl-03", "Construction Crew Severe Weather Guard", "construction", 43.0, 2, 1200.0, 140.0, "Tata AIG Parametric", "Guarantees wage backup for heavy construction labor during mandatory work suspension heatwaves.")
    ]
    cursor.executemany("""
    INSERT INTO policy_templates (id, title, sector, temperature_threshold_c, duration_days, payout_amount_inr, premium_monthly_inr, provider_name, description)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, templates)

    # Seed Demo Cohorts
    cohorts = [
        ("cohort-01", "Bandra QuickCommerce Fleet #14", "Rajesh Kumar", "rajesh.kumar@quicklogistics.in", "delivery", "Bandra West, Mumbai", 19.0596, 72.8295, now),
        ("cohort-02", "Dharavi Artisan & Vendor Guild", "Sunita Patil", "sunita.patil@vendors-guild.org", "street_vendor", "Dharavi, Mumbai", 19.0402, 72.8508, now),
        ("cohort-03", "Andheri Metro Construction Site C", "Vikram Singh", "vikram.singh@infracorp.co.in", "construction", "Andheri East, Mumbai", 19.1136, 72.8697, now)
    ]
    cursor.executemany("""
    INSERT INTO cohorts (id, name, manager_name, manager_email, sector, location_name, lat, lon, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, cohorts)

    # Seed Demo Workers
    workers = [
        ("w-01", "cohort-01", "Amit Verma", "+919876543210", "amitverma@okaxis", "UPI", "active", now),
        ("w-02", "cohort-01", "Rahul Sharma", "+919876543211", "rahul.sharma@paytm", "UPI", "active", now),
        ("w-03", "cohort-01", "Priya Nair", "+919876543212", "priyanair@ybl", "UPI", "active", now),
        ("w-04", "cohort-02", "Ramesh Jadhav", "+919876543213", "ramesh.j@gpay", "UPI", "active", now),
        ("w-05", "cohort-02", "Fatima Sheikh", "+919876543214", "fatima.s@okicici", "UPI", "active", now),
        ("w-06", "cohort-03", "Suresh Yadav", "+919876543215", "sureshyadav@sbi", "UPI", "active", now),
        ("w-07", "cohort-03", "Ganesh Gowda", "+919876543216", "ganeshgowda@ubi", "UPI", "active", now)
    ]
    cursor.executemany("""
    INSERT INTO workers (id, cohort_id, name, phone, payment_upi, payment_method, status, registered_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, workers)

    # Seed Active Policies
    active_policies = [
        ("act-pol-01", "cohort-01", "pol-tmpl-01", "2026-07-01", "2026-12-31", 3, "active"),
        ("act-pol-02", "cohort-02", "pol-tmpl-02", "2026-07-01", "2026-12-31", 2, "active"),
        ("act-pol-03", "cohort-03", "pol-tmpl-03", "2026-07-01", "2026-12-31", 2, "active")
    ]
    cursor.executemany("""
    INSERT INTO active_policies (id, cohort_id, policy_template_id, start_date, end_date, covered_workers_count, status)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """, active_policies)

    # Seed Pending Payout Event ready for One-Tap Approval
    payout_events = [
        ("evt-01", "act-pol-01", "cohort-01", 43.8, now, 2250.0, 750.0, "pending_approval", None, None)
    ]
    cursor.executemany("""
    INSERT INTO payout_events (id, active_policy_id, cohort_id, trigger_temperature_c, trigger_date, total_amount_inr, per_worker_amount_inr, status, approved_at, approved_by)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, payout_events)

    conn.commit()


# Pydantic Schemas

class CohortCreate(BaseModel):
    name: str
    manager_name: str
    manager_email: str
    sector: str  # delivery, construction, street_vendor
    location_name: str
    lat: float
    lon: float

class WorkerCreate(BaseModel):
    cohort_id: str
    name: str
    phone: str
    payment_upi: str

class PolicyTemplateCreate(BaseModel):
    title: str
    sector: str
    temperature_threshold_c: float
    duration_days: int
    payout_amount_inr: float
    premium_monthly_inr: float
    provider_name: str
    description: str

class BuyPolicyRequest(BaseModel):
    cohort_id: str
    policy_template_id: str

class TriggerSimulateRequest(BaseModel):
    cohort_id: str
    simulated_temp_c: float

class ApprovePayoutRequest(BaseModel):
    approved_by: str

import backend.supabase_client as supa

# Helper CRUD functions

def get_all_cohorts(manager_email: Optional[str] = None) -> List[Dict[str, Any]]:
    if supa.is_supabase_configured():
        match_dict = {"manager_email": manager_email} if manager_email else None
        cohorts = supa.supabase_select("cohorts", match=match_dict, order="created_at.desc")
        if cohorts:
            all_workers = supa.supabase_select("workers")
            all_policies = supa.supabase_select("active_policies", match={"status": "active"})

            worker_counts: Dict[str, int] = {}
            for w in all_workers:
                cid = w.get("cohort_id")
                if cid:
                    worker_counts[cid] = worker_counts.get(cid, 0) + 1

            policy_counts: Dict[str, int] = {}
            for p in all_policies:
                cid = p.get("cohort_id")
                if cid:
                    policy_counts[cid] = policy_counts.get(cid, 0) + 1

            for c in cohorts:
                cid = c.get("id")
                c["worker_count"] = worker_counts.get(cid, 0)
                c["active_policy_count"] = policy_counts.get(cid, 0)

        return cohorts

    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT c.*, 
               (SELECT COUNT(*) FROM workers w WHERE w.cohort_id = c.id) as worker_count,
               (SELECT COUNT(*) FROM active_policies ap WHERE ap.cohort_id = c.id AND ap.status = 'active') as active_policy_count
        FROM cohorts c
    """
    params = []
    if manager_email:
        query += " WHERE c.manager_email = ?"
        params.append(manager_email)
    query += " ORDER BY created_at DESC;"

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_cohort_by_id(cohort_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cohorts WHERE id = ?;", (cohort_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_cohort(data: CohortCreate) -> Dict[str, Any]:
    cohort_id = f"cohort-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": cohort_id,
        "name": data.name,
        "manager_name": data.manager_name,
        "manager_email": data.manager_email,
        "sector": data.sector,
        "location_name": data.location_name,
        "lat": data.lat,
        "lon": data.lon,
        "created_at": now
    }
    if supa.is_supabase_configured():
        return supa.supabase_insert("cohorts", row)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cohorts (id, name, manager_name, manager_email, sector, location_name, lat, lon, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (cohort_id, data.name, data.manager_name, data.manager_email, data.sector, data.location_name, data.lat, data.lon, now))
    conn.commit()
    conn.close()
    return get_cohort_by_id(cohort_id)

def get_workers_by_cohort(cohort_id: str) -> List[Dict[str, Any]]:
    if supa.is_supabase_configured():
        return supa.supabase_select("workers", match={"cohort_id": cohort_id}, order="registered_at.desc")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workers WHERE cohort_id = ? ORDER BY registered_at DESC;", (cohort_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def register_worker(data: WorkerCreate) -> Dict[str, Any]:
    worker_id = f"w-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": worker_id,
        "cohort_id": data.cohort_id,
        "name": data.name,
        "phone": data.phone,
        "payment_upi": data.payment_upi,
        "payment_method": "UPI",
        "status": "active",
        "registered_at": now
    }
    if supa.is_supabase_configured():
        return supa.supabase_insert("workers", row)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO workers (id, cohort_id, name, phone, payment_upi, payment_method, status, registered_at)
        VALUES (?, ?, ?, ?, ?, 'UPI', 'active', ?);
    """, (worker_id, data.cohort_id, data.name, data.phone, data.payment_upi, now))
    
    # Update covered workers count on active policies for this cohort
    cursor.execute("""
        UPDATE active_policies 
        SET covered_workers_count = (SELECT COUNT(*) FROM workers WHERE cohort_id = ?)
        WHERE cohort_id = ?;
    """, (data.cohort_id, data.cohort_id))
    
    conn.commit()
    cursor.execute("SELECT * FROM workers WHERE id = ?;", (worker_id,))
    row = dict(cursor.fetchone())
    conn.close()
    return row

def get_policy_templates() -> List[Dict[str, Any]]:
    if supa.is_supabase_configured():
        return supa.supabase_select("policy_templates", order="premium_monthly_inr.asc")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM policy_templates ORDER BY premium_monthly_inr ASC;")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def create_policy_template(data: PolicyTemplateCreate) -> Dict[str, Any]:
    tmpl_id = f"pol-tmpl-{uuid.uuid4().hex[:8]}"
    row = {
        "id": tmpl_id,
        "title": data.title,
        "sector": data.sector,
        "temperature_threshold_c": data.temperature_threshold_c,
        "duration_days": data.duration_days,
        "payout_amount_inr": data.payout_amount_inr,
        "premium_monthly_inr": data.premium_monthly_inr,
        "provider_name": data.provider_name,
        "description": data.description
    }
    if supa.is_supabase_configured():
        return supa.supabase_insert("policy_templates", row)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO policy_templates (id, title, sector, temperature_threshold_c, duration_days, payout_amount_inr, premium_monthly_inr, provider_name, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (tmpl_id, data.title, data.sector, data.temperature_threshold_c, data.duration_days, data.payout_amount_inr, data.premium_monthly_inr, data.provider_name, data.description))
    conn.commit()
    cursor.execute("SELECT * FROM policy_templates WHERE id = ?;", (tmpl_id,))
    res = dict(cursor.fetchone())
    conn.close()
    return res

def buy_policy(data: BuyPolicyRequest) -> Dict[str, Any]:
    active_id = f"act-pol-{uuid.uuid4().hex[:8]}"
    start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    end_date = "2026-12-31"

    if supa.is_supabase_configured():
        # Get worker count for this cohort
        workers = supa.supabase_select("workers", match={"cohort_id": data.cohort_id}) or []
        cnt = len(workers)

        row = {
            "id": active_id,
            "cohort_id": data.cohort_id,
            "policy_template_id": data.policy_template_id,
            "start_date": start_date,
            "end_date": end_date,
            "covered_workers_count": cnt,
            "status": "active"
        }
        supa.supabase_insert("active_policies", row)

        # Retrieve template & cohort for returned object
        tmpl_list = supa.supabase_select("policy_templates", match={"id": data.policy_template_id}) or []
        cohort_list = supa.supabase_select("cohorts", match={"id": data.cohort_id}) or []

        tmpl = tmpl_list[0] if len(tmpl_list) > 0 else {}
        cohort = cohort_list[0] if len(cohort_list) > 0 else {}

        return {
            **row,
            "title": tmpl.get("title", "Heatwave Policy"),
            "temperature_threshold_c": tmpl.get("temperature_threshold_c", 42.5),
            "payout_amount_inr": tmpl.get("payout_amount_inr", 750),
            "provider_name": tmpl.get("provider_name", "Parametric Insurer"),
            "cohort_name": cohort.get("name", "Cohort")
        }

    conn = get_db()
    cursor = conn.cursor()

    # Get worker count
    cursor.execute("SELECT COUNT(*) as cnt FROM workers WHERE cohort_id = ?;", (data.cohort_id,))
    cnt = cursor.fetchone()["cnt"]

    cursor.execute("""
        INSERT INTO active_policies (id, cohort_id, policy_template_id, start_date, end_date, covered_workers_count, status)
        VALUES (?, ?, ?, ?, ?, ?, 'active');
    """, (active_id, data.cohort_id, data.policy_template_id, start_date, end_date, cnt))
    conn.commit()

    cursor.execute("""
        SELECT ap.*, pt.title, pt.temperature_threshold_c, pt.payout_amount_inr, pt.provider_name, c.name as cohort_name
        FROM active_policies ap
        JOIN policy_templates pt ON ap.policy_template_id = pt.id
        JOIN cohorts c ON ap.cohort_id = c.id
        WHERE ap.id = ?;
    """, (active_id,))
    row = dict(cursor.fetchone())
    conn.close()
    return row

def get_active_policies_for_cohort(cohort_id: str) -> List[Dict[str, Any]]:
    if supa.is_supabase_configured():
        pols = supa.supabase_select("active_policies", match={"cohort_id": cohort_id, "status": "active"})
        all_templates = supa.supabase_select("policy_templates")
        tmpl_map = {t["id"]: t for t in all_templates}

        res = []
        for p in pols:
            t = tmpl_map.get(p.get("policy_template_id"), {})
            res.append({
                **p,
                "title": t.get("title", "Heat Policy"),
                "sector": t.get("sector", "delivery"),
                "temperature_threshold_c": t.get("temperature_threshold_c", 42.5),
                "payout_amount_inr": t.get("payout_amount_inr", 750),
                "provider_name": t.get("provider_name", "Insurer"),
                "description": t.get("description", "")
            })
        return res

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ap.*, pt.title, pt.sector, pt.temperature_threshold_c, pt.payout_amount_inr, pt.provider_name, pt.description
        FROM active_policies ap
        JOIN policy_templates pt ON ap.policy_template_id = pt.id
        WHERE ap.cohort_id = ? AND ap.status = 'active';
    """, (cohort_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_all_active_policies(manager_email: Optional[str] = None) -> List[Dict[str, Any]]:
    if supa.is_supabase_configured():
        pols = supa.supabase_select("active_policies", match={"status": "active"})
        all_cohorts = get_all_cohorts(manager_email)
        cohort_map = {c["id"]: c for c in all_cohorts}

        if manager_email:
            pols = [p for p in pols if p.get("cohort_id") in cohort_map]

        all_templates = supa.supabase_select("policy_templates")
        tmpl_map = {t["id"]: t for t in all_templates}

        result = []
        for p in pols:
            cid = p.get("cohort_id")
            tid = p.get("policy_template_id")
            c = cohort_map.get(cid, {})
            t = tmpl_map.get(tid, {})

            result.append({
                **p,
                "title": t.get("title", "Parametric Heat Shield"),
                "sector": t.get("sector", "delivery"),
                "temperature_threshold_c": t.get("temperature_threshold_c", 42.5),
                "payout_amount_inr": t.get("payout_amount_inr", 750),
                "provider_name": t.get("provider_name", "ICICI Lombard"),
                "cohort_name": c.get("name", "Cohort"),
                "manager_name": c.get("manager_name", "Site Lead")
            })

        return result

    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT ap.*, pt.title, pt.sector, pt.temperature_threshold_c, pt.payout_amount_inr, pt.provider_name, c.name as cohort_name, c.manager_name
        FROM active_policies ap
        JOIN policy_templates pt ON ap.policy_template_id = pt.id
        JOIN cohorts c ON ap.cohort_id = c.id
    """
    params = []
    if manager_email:
        query += " WHERE c.manager_email = ?"
        params.append(manager_email)
    
    query += " ORDER BY ap.start_date DESC;"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def trigger_payout_simulation(data: TriggerSimulateRequest) -> Dict[str, Any]:
    """Evaluates simulated weather against active policies for a cohort. Creates pending PayoutEvent if threshold crossed."""
    conn = get_db()
    cursor = conn.cursor()

    # Find active policies for this cohort
    cursor.execute("""
        SELECT ap.id as active_policy_id, ap.cohort_id, pt.temperature_threshold_c, pt.payout_amount_inr, pt.title
        FROM active_policies ap
        JOIN policy_templates pt ON ap.policy_template_id = pt.id
        WHERE ap.cohort_id = ? AND ap.status = 'active';
    """, (data.cohort_id,))
    policies = [dict(r) for r in cursor.fetchall()]

    if not policies:
        conn.close()
        return {"triggered": False, "reason": "No active policies found for this cohort."}

    triggered_events = []
    now = datetime.now(timezone.utc).isoformat()

    for pol in policies:
        if data.simulated_temp_c >= pol["temperature_threshold_c"]:
            # Count workers
            cursor.execute("SELECT COUNT(*) as cnt FROM workers WHERE cohort_id = ?;", (data.cohort_id,))
            worker_cnt = max(1, cursor.fetchone()["cnt"])

            per_worker = pol["payout_amount_inr"]
            total_amt = per_worker * worker_cnt
            evt_id = f"evt-{uuid.uuid4().hex[:8]}"

            cursor.execute("""
                INSERT INTO payout_events (id, active_policy_id, cohort_id, trigger_temperature_c, trigger_date, total_amount_inr, per_worker_amount_inr, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_approval');
            """, (evt_id, pol["active_policy_id"], data.cohort_id, data.simulated_temp_c, now, total_amt, per_worker))
            
            triggered_events.append({
                "event_id": evt_id,
                "policy_title": pol["title"],
                "trigger_temp": data.simulated_temp_c,
                "threshold": pol["temperature_threshold_c"],
                "total_amount_inr": total_amt,
                "worker_count": worker_cnt
            })

    conn.commit()
    conn.close()
    return {"triggered": len(triggered_events) > 0, "events": triggered_events}

def get_payout_events(cohort_id: Optional[str] = None, manager_email: Optional[str] = None) -> List[Dict[str, Any]]:
    if supa.is_supabase_configured():
        events = supa.supabase_select("payout_events", order="trigger_date.desc")
        if manager_email:
            cohorts = get_all_cohorts(manager_email)
            cohort_ids = [c["id"] for c in cohorts]
            events = [e for e in events if e.get("cohort_id") in cohort_ids]
        return events

    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT pe.*, c.name as cohort_name, c.manager_name, c.sector, pt.title as policy_title, pt.provider_name,
               (SELECT COUNT(*) FROM workers w WHERE w.cohort_id = pe.cohort_id) as worker_count
        FROM payout_events pe
        JOIN cohorts c ON pe.cohort_id = c.id
        JOIN active_policies ap ON pe.active_policy_id = ap.id
        JOIN policy_templates pt ON ap.policy_template_id = pt.id
    """
    params = []
    conditions = []
    if cohort_id:
        conditions.append("pe.cohort_id = ?")
        params.append(cohort_id)
    if manager_email:
        conditions.append("c.manager_email = ?")
        params.append(manager_email)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY pe.trigger_date DESC;"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def approve_payout_event(event_id: str, approved_by: str) -> Dict[str, Any]:
    """Manager hits one-tap approval. Changes status to 'disbursed' and updates timestamps."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        UPDATE payout_events
        SET status = 'disbursed', approved_at = ?, approved_by = ?
        WHERE id = ? AND status = 'pending_approval';
    """, (now, approved_by, event_id))

    conn.commit()

    cursor.execute("""
        SELECT pe.*, c.name as cohort_name, pt.title as policy_title,
               (SELECT COUNT(*) FROM workers w WHERE w.cohort_id = pe.cohort_id) as worker_count
        FROM payout_events pe
        JOIN cohorts c ON pe.cohort_id = c.id
        JOIN active_policies ap ON pe.active_policy_id = ap.id
        JOIN policy_templates pt ON ap.policy_template_id = pt.id
        WHERE pe.id = ?;
    """, (event_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Payout event {event_id} not found or already processed.")
    return dict(row)

def get_overall_stats(manager_email: Optional[str] = None) -> Dict[str, Any]:
    if supa.is_supabase_configured():
        cohorts = get_all_cohorts(manager_email)
        cohort_ids = [c["id"] for c in cohorts]
        workers = supa.supabase_select("workers")
        if manager_email:
            workers = [w for w in workers if w.get("cohort_id") in cohort_ids]
        
        active_pols = supa.supabase_select("active_policies", match={"status": "active"})
        if manager_email:
            active_pols = [ap for ap in active_pols if ap.get("cohort_id") in cohort_ids]

        payouts = supa.supabase_select("payout_events")
        if manager_email:
            payouts = [pe for pe in payouts if pe.get("cohort_id") in cohort_ids]

        disbursed = sum(pe.get("total_amount_inr", 0) for pe in payouts if pe.get("status") == "disbursed")
        pending = sum(1 for pe in payouts if pe.get("status") == "pending_approval")

        return {
            "total_cohorts": len(cohorts),
            "total_workers": len(workers),
            "total_active_policies": len(active_pols),
            "total_disbursed_inr": disbursed,
            "pending_approvals": pending
        }

    conn = get_db()
    cursor = conn.cursor()

    if manager_email:
        cursor.execute("SELECT COUNT(*) as cnt FROM cohorts WHERE manager_email = ?;", (manager_email,))
        total_cohorts = cursor.fetchone()["cnt"]

        cursor.execute("""
            SELECT COUNT(*) as cnt FROM workers 
            WHERE cohort_id IN (SELECT id FROM cohorts WHERE manager_email = ?);
        """, (manager_email,))
        total_workers = cursor.fetchone()["cnt"]

        cursor.execute("""
            SELECT COUNT(*) as cnt FROM active_policies 
            WHERE status = 'active' AND cohort_id IN (SELECT id FROM cohorts WHERE manager_email = ?);
        """, (manager_email,))
        total_active_policies = cursor.fetchone()["cnt"]

        cursor.execute("""
            SELECT COALESCE(SUM(total_amount_inr), 0) as total FROM payout_events 
            WHERE status = 'disbursed' AND cohort_id IN (SELECT id FROM cohorts WHERE manager_email = ?);
        """, (manager_email,))
        total_disbursed = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) as cnt FROM payout_events 
            WHERE status = 'pending_approval' AND cohort_id IN (SELECT id FROM cohorts WHERE manager_email = ?);
        """, (manager_email,))
        pending_approvals = cursor.fetchone()["cnt"]
    else:
        cursor.execute("SELECT COUNT(*) as total_cohorts FROM cohorts;")
        total_cohorts = cursor.fetchone()["total_cohorts"]

        cursor.execute("SELECT COUNT(*) as total_workers FROM workers;")
        total_workers = cursor.fetchone()["total_workers"]

        cursor.execute("SELECT COUNT(*) as total_active_policies FROM active_policies WHERE status = 'active';")
        total_active_policies = cursor.fetchone()["total_active_policies"]

        cursor.execute("SELECT COALESCE(SUM(total_amount_inr), 0) as total FROM payout_events WHERE status = 'disbursed';")
        total_disbursed = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as cnt FROM payout_events WHERE status = 'pending_approval';")
        pending_approvals = cursor.fetchone()["cnt"]

    conn.close()

    return {
        "total_cohorts": total_cohorts,
        "total_workers": total_workers,
        "total_active_policies": total_active_policies,
        "total_disbursed_inr": total_disbursed,
        "pending_approvals": pending_approvals
    }
