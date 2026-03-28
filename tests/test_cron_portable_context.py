from __future__ import annotations

from dharma_swarm import cron_portable_context


def test_build_portable_job_prompt_defaults_to_raw_prompt_for_unknown_job():
    prompt = cron_portable_context.build_portable_job_prompt(
        {"id": "unknown-job", "prompt": "raw prompt"}
    )

    assert prompt == "raw prompt"


def test_build_portable_job_prompt_for_pulse_inlines_local_snapshot(monkeypatch):
    monkeypatch.setattr(
        cron_portable_context,
        "read_agni_state",
        lambda: {"working": "AGNI blocked on sync", "priorities_age_hours": 52.0},
    )
    monkeypatch.setattr(
        cron_portable_context,
        "read_trishula_inbox",
        lambda: "2 messages, most recent: ping.md",
    )
    monkeypatch.setattr(
        cron_portable_context,
        "read_memory_context",
        lambda *args, **kwargs: "[L4] witness memory",
    )
    monkeypatch.setattr(
        cron_portable_context,
        "read_agent_notes",
        lambda *args, **kwargs: "researcher: found something",
    )
    monkeypatch.setattr(
        cron_portable_context,
        "read_manifest",
        lambda: "Ecosystem: 77/79 paths exist.",
    )
    monkeypatch.setattr(
        cron_portable_context,
        "_assurance_critical_summary",
        lambda: "1 critical assurance finding across 3 latest scans.",
    )

    prompt = cron_portable_context.build_portable_job_prompt({"id": "pulse", "prompt": "raw"})

    assert "AGNI blocked on sync" in prompt
    assert "2 messages, most recent: ping.md" in prompt
    assert "witness memory" in prompt
    assert "researcher: found something" in prompt
    assert "1 critical assurance finding" in prompt
    assert "Do not invent file reads" in prompt


def test_build_portable_job_prompt_for_jk_pulse_summarizes_local_snapshot(tmp_path, monkeypatch):
    jk_dir = tmp_path / "jagat_kalyan"
    shared_dir = tmp_path / ".dharma" / "shared"
    jk_dir.mkdir(parents=True)
    shared_dir.mkdir(parents=True)
    (jk_dir / "app.py").write_text("app = 1\n", encoding="utf-8")
    (jk_dir / "matching.py").write_text("match = 1\n", encoding="utf-8")
    (jk_dir / "models.py").write_text("model = 1\n", encoding="utf-8")
    (shared_dir / "jk_alert.md").write_text("HIGH: grant deadline", encoding="utf-8")

    monkeypatch.setattr(cron_portable_context, "_JK_DIR", jk_dir)
    monkeypatch.setattr(cron_portable_context, "_SHARED_DIR", shared_dir)
    monkeypatch.setattr(cron_portable_context, "_file_age_days", lambda path: "1.5")

    prompt = cron_portable_context.build_portable_job_prompt({"id": "jk_pulse", "prompt": "raw"})

    assert '"app.py": true' in prompt.lower()
    assert "SCOUT_LOG age days: 1.5" in prompt
    assert "EVOLUTION_LOG age days: 1.5" in prompt
    assert "HIGH: grant deadline" in prompt


def test_build_portable_job_prompt_for_trishula_triage_summarizes_counts(tmp_path, monkeypatch):
    home = tmp_path
    inbox = home / "trishula" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "ack_1.md").write_text("ok", encoding="utf-8")
    (inbox / "diag_ping.md").write_text("ok", encoding="utf-8")
    (inbox / "urgent_message.md").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(cron_portable_context, "_HOME", home)

    prompt = cron_portable_context.build_portable_job_prompt({"id": "trishula_triage", "prompt": "raw"})

    assert "ack_messages=1" in prompt
    assert "substantive_messages=1" in prompt
    assert "diagnostic_messages=1" in prompt
    assert "urgent_message.md" in prompt


def test_persist_portable_job_output_writes_known_artifact(tmp_path, monkeypatch):
    shared_dir = tmp_path / ".dharma" / "shared"
    daemon_dir = tmp_path / "dgc-core" / "daemon"
    monkeypatch.setattr(cron_portable_context, "_SHARED_DIR", shared_dir)
    monkeypatch.setattr(cron_portable_context, "_DGC_DAEMON_DIR", daemon_dir)

    target = cron_portable_context.persist_portable_job_output(
        {"id": "morning_brief"},
        "hello world",
    )

    assert target == daemon_dir / "morning_brief.md"
    assert target.read_text(encoding="utf-8") == "hello world\n"
