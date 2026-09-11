"""Regression tests for graceful parametric data fallback."""

import socket

import backend.supabase_client as supa


def test_unresolvable_supabase_endpoint_is_treated_as_unconfigured(monkeypatch):
    monkeypatch.setattr(supa, "SUPABASE_URL", "https://missing-project.supabase.co")
    monkeypatch.setattr(supa, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: (_ for _ in ()).throw(socket.gaierror("name or service not known")),
    )
    monkeypatch.setattr(supa, "_supabase_endpoint_status", None)

    assert supa.is_supabase_configured() is False
