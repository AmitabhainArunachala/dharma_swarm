"""Provider and accelerator command pack for the modular DGC CLI."""

from __future__ import annotations

import argparse


def cmd_provider_smoke(
    *,
    ollama_model: str | None = None,
    nim_model: str | None = None,
    qwen_provider: str | None = None,
    qwen_task: str | None = None,
    telemetry_db: str | None = None,
    as_json: bool = False,
) -> int:
    from dharma_swarm import dgc_cli

    return dgc_cli.cmd_provider_smoke(
        ollama_model=ollama_model,
        nim_model=nim_model,
        qwen_provider=qwen_provider,
        qwen_task=qwen_task,
        telemetry_db=telemetry_db,
        as_json=as_json,
    )


def cmd_provider_matrix(
    *,
    profile: str,
    corpus: str,
    max_targets: int | None,
    max_prompts: int | None,
    timeout_seconds: float,
    concurrency: int,
    budget_units: int | None,
    artifact_dir: str | None,
    include_unavailable: bool,
    write_artifacts: bool,
    as_json: bool = False,
) -> int:
    from dharma_swarm import dgc_cli

    return dgc_cli.cmd_provider_matrix(
        profile=profile,
        corpus=corpus,
        max_targets=max_targets,
        max_prompts=max_prompts,
        timeout_seconds=timeout_seconds,
        concurrency=concurrency,
        budget_units=budget_units,
        artifact_dir=artifact_dir,
        include_unavailable=include_unavailable,
        write_artifacts=write_artifacts,
        as_json=as_json,
    )


def cmd_rag_health(*, service: str = "rag", check_dependencies: bool = True) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_rag_health(service=service, check_dependencies=check_dependencies)


def cmd_rag_search(*, query: str, top_k: int = 5, collection: str | None = None) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_rag_search(query=query, top_k=top_k, collection=collection)


def cmd_rag_chat(*, prompt: str, model: str | None = None) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_rag_chat(prompt=prompt, model=model)


def cmd_flywheel_jobs() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_flywheel_jobs()


def cmd_flywheel_export(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_flywheel_export(**kwargs)


def cmd_flywheel_record(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_flywheel_record(**kwargs)


def cmd_flywheel_start(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_flywheel_start(**kwargs)


def cmd_flywheel_get(job_id: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_flywheel_get(job_id)


def cmd_flywheel_cancel(job_id: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_flywheel_cancel(job_id)


def cmd_flywheel_delete(job_id: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_flywheel_delete(job_id)


def cmd_flywheel_watch(job_id: str, poll_sec: float, timeout_sec: float) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_flywheel_watch(job_id, poll_sec, timeout_sec)


def cmd_reciprocity_health() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_reciprocity_health()


def cmd_reciprocity_summary() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_reciprocity_summary()


def cmd_reciprocity_publish(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_reciprocity_publish(**kwargs)


def cmd_reciprocity_record(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_reciprocity_record(**kwargs)


def cmd_ouroboros_connections(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_ouroboros_connections(**kwargs)


def cmd_ouroboros_record(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_ouroboros_record(**kwargs)


def build_provider_smoke_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("provider-smoke", help="Probe local and external provider lanes")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--ollama-model", default=None, help="Override Ollama model")
    parser.add_argument("--nim-model", default=None, help="Override NVIDIA NIM model")
    parser.add_argument("--qwen-provider", default=None, help="Force a Qwen3.5 Surgical Coder dashboard smoke against a specific provider")
    parser.add_argument("--qwen-task", default=None, help="Override the read-only Qwen dashboard smoke task")
    parser.add_argument("--telemetry-db", default=None, help="Persist probe outcomes into the canonical telemetry DB at this path")


def handle_provider_smoke(args: argparse.Namespace) -> int:
    return cmd_provider_smoke(
        ollama_model=args.ollama_model,
        nim_model=args.nim_model,
        qwen_provider=args.qwen_provider,
        qwen_task=args.qwen_task,
        telemetry_db=args.telemetry_db,
        as_json=args.json,
    )


def build_provider_matrix_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("provider-matrix", help="Run the live provider/model matrix harness")
    parser.add_argument("--profile", choices=["quick", "live25", "certified_fast"], default="live25")
    parser.add_argument("--corpus", choices=["deployment", "workspace"], default="deployment")
    parser.add_argument("--max-targets", type=int, default=None)
    parser.add_argument("--max-prompts", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--budget-units", type=int, default=40)
    parser.add_argument("--artifact-dir", default=None)
    parser.add_argument("--include-unavailable", action="store_true")
    parser.add_argument("--no-artifacts", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")


def handle_provider_matrix(args: argparse.Namespace) -> int:
    return cmd_provider_matrix(
        profile=args.profile,
        corpus=args.corpus,
        max_targets=args.max_targets,
        max_prompts=args.max_prompts,
        timeout_seconds=args.timeout_seconds,
        concurrency=args.concurrency,
        budget_units=args.budget_units,
        artifact_dir=args.artifact_dir,
        include_unavailable=args.include_unavailable,
        write_artifacts=not args.no_artifacts,
        as_json=args.json,
    )


def build_rag_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("rag", help="NVIDIA RAG integration commands")
    rag_sub = parser.add_subparsers(dest="rag_cmd")

    p_rh = rag_sub.add_parser("health", help="Check rag/ingestor health")
    p_rh.add_argument("--service", choices=["rag", "ingest"], default="rag")
    p_rh.add_argument("--no-deps", action="store_true", help="Skip dependency checks")

    p_rs = rag_sub.add_parser("search", help="Query RAG search endpoint")
    p_rs.add_argument("query", nargs="+")
    p_rs.add_argument("--top-k", type=int, default=5)
    p_rs.add_argument("--collection", default=None)

    p_rc = rag_sub.add_parser("chat", help="Run grounded chat completion")
    p_rc.add_argument("prompt", nargs="+")
    p_rc.add_argument("--model", default=None)


def handle_rag(args: argparse.Namespace) -> None:
    try:
        match args.rag_cmd:
            case "health":
                cmd_rag_health(service=args.service, check_dependencies=not args.no_deps)
            case "search":
                cmd_rag_search(query=" ".join(args.query), top_k=args.top_k, collection=args.collection)
            case "chat":
                cmd_rag_chat(prompt=" ".join(args.prompt), model=args.model)
            case _:
                raise SystemExit(2)
    except Exception as e:
        print(f"RAG command failed: {e}")
        raise SystemExit(2) from e


def build_flywheel_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("flywheel", help="NVIDIA Data Flywheel commands")
    fw_sub = parser.add_subparsers(dest="flywheel_cmd")

    fw_sub.add_parser("jobs", help="List flywheel jobs")

    p_fwe = fw_sub.add_parser("export", help="Build a local canonical flywheel export")
    p_fwe.add_argument("--run-id", required=True)
    p_fwe.add_argument("--workload-id", required=True)
    p_fwe.add_argument("--client-id", required=True)
    p_fwe.add_argument("--trace-id", default=None)
    p_fwe.add_argument("--db-path", default=None)
    p_fwe.add_argument("--event-log-dir", default=None)
    p_fwe.add_argument("--export-root", default=None)

    p_fwr = fw_sub.add_parser("record", help="Record a flywheel job result into canonical runtime truth")
    p_fwr.add_argument("job_id")
    p_fwr.add_argument("--workload-id", default=None)
    p_fwr.add_argument("--client-id", default=None)
    p_fwr.add_argument("--run-id", default=None)
    p_fwr.add_argument("--session-id", default=None)
    p_fwr.add_argument("--task-id", default=None)
    p_fwr.add_argument("--trace-id", default=None)
    p_fwr.add_argument("--db-path", default=None)
    p_fwr.add_argument("--event-log-dir", default=None)
    p_fwr.add_argument("--workspace-root", default=None)
    p_fwr.add_argument("--provenance-root", default=None)

    p_fws = fw_sub.add_parser("start", help="Start a flywheel job")
    p_fws.add_argument("--workload-id", required=True)
    p_fws.add_argument("--client-id", required=True)
    p_fws.add_argument("--eval-size", type=int, default=20)
    p_fws.add_argument("--val-ratio", type=float, default=0.1)
    p_fws.add_argument("--min-total-records", type=int, default=50)
    p_fws.add_argument("--limit", type=int, default=10000)
    p_fws.add_argument("--run-id", default=None)
    p_fws.add_argument("--trace-id", default=None)
    p_fws.add_argument("--db-path", default=None)
    p_fws.add_argument("--event-log-dir", default=None)
    p_fws.add_argument("--export-root", default=None)

    p_fwg = fw_sub.add_parser("get", help="Get flywheel job details")
    p_fwg.add_argument("job_id")

    p_fwc = fw_sub.add_parser("cancel", help="Cancel flywheel job")
    p_fwc.add_argument("job_id")

    p_fwd = fw_sub.add_parser("delete", help="Delete flywheel job")
    p_fwd.add_argument("job_id")

    p_fww = fw_sub.add_parser("watch", help="Wait for job completion")
    p_fww.add_argument("job_id")
    p_fww.add_argument("--poll-sec", type=float, default=5.0)
    p_fww.add_argument("--timeout-sec", type=float, default=1800.0)


def handle_flywheel(args: argparse.Namespace) -> None:
    try:
        match args.flywheel_cmd:
            case "jobs":
                cmd_flywheel_jobs()
            case "export":
                cmd_flywheel_export(
                    run_id=args.run_id,
                    workload_id=args.workload_id,
                    client_id=args.client_id,
                    trace_id=args.trace_id,
                    db_path=args.db_path,
                    event_log_dir=args.event_log_dir,
                    export_root=args.export_root,
                )
            case "record":
                cmd_flywheel_record(
                    job_id=args.job_id,
                    workload_id=args.workload_id,
                    client_id=args.client_id,
                    run_id=args.run_id,
                    session_id=args.session_id,
                    task_id=args.task_id,
                    trace_id=args.trace_id,
                    db_path=args.db_path,
                    event_log_dir=args.event_log_dir,
                    workspace_root=args.workspace_root,
                    provenance_root=args.provenance_root,
                )
            case "start":
                cmd_flywheel_start(
                    workload_id=args.workload_id,
                    client_id=args.client_id,
                    eval_size=args.eval_size,
                    val_ratio=args.val_ratio,
                    min_total_records=args.min_total_records,
                    limit=args.limit,
                    run_id=args.run_id,
                    trace_id=args.trace_id,
                    db_path=args.db_path,
                    event_log_dir=args.event_log_dir,
                    export_root=args.export_root,
                )
            case "get":
                cmd_flywheel_get(args.job_id)
            case "cancel":
                cmd_flywheel_cancel(args.job_id)
            case "delete":
                cmd_flywheel_delete(args.job_id)
            case "watch":
                cmd_flywheel_watch(args.job_id, args.poll_sec, args.timeout_sec)
            case _:
                raise SystemExit(2)
    except Exception as e:
        print(f"Flywheel command failed: {e}")
        raise SystemExit(2) from e


def build_reciprocity_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("reciprocity", help="Planetary Reciprocity Commons commands")
    reciprocity_sub = parser.add_subparsers(dest="reciprocity_cmd")

    reciprocity_sub.add_parser("health", help="Check reciprocity service health")
    reciprocity_sub.add_parser("summary", help="Fetch the current ledger summary")

    p_recp = reciprocity_sub.add_parser("publish", help="Publish a reciprocity record to the service")
    p_recp.add_argument("publish_type", choices=["activity", "obligation", "project", "outcome"])
    p_recp_payload = p_recp.add_mutually_exclusive_group(required=True)
    p_recp_payload.add_argument("--json", dest="publish_json", default=None, help="Inline JSON object payload")
    p_recp_payload.add_argument("--file", dest="publish_file", default=None, help="Path to a JSON payload file")

    p_recr = reciprocity_sub.add_parser("record", help="Record the current reciprocity ledger summary into canonical runtime truth")
    p_recr.add_argument("--run-id", default=None)
    p_recr.add_argument("--session-id", default=None)
    p_recr.add_argument("--task-id", default=None)
    p_recr.add_argument("--trace-id", default=None)
    p_recr.add_argument("--summary-type", default="ledger_summary")
    p_recr_payload = p_recr.add_mutually_exclusive_group(required=False)
    p_recr_payload.add_argument("--json", dest="record_json", default=None, help="Inline JSON ledger summary payload to record instead of fetching live")
    p_recr_payload.add_argument("--file", dest="record_file", default=None, help="Path to a JSON ledger summary payload file to record instead of fetching live")
    p_recr.add_argument("--db-path", default=None)
    p_recr.add_argument("--event-log-dir", default=None)
    p_recr.add_argument("--workspace-root", default=None)
    p_recr.add_argument("--provenance-root", default=None)


def handle_reciprocity(args: argparse.Namespace) -> None:
    try:
        match args.reciprocity_cmd:
            case "health":
                cmd_reciprocity_health()
            case "summary":
                cmd_reciprocity_summary()
            case "publish":
                cmd_reciprocity_publish(
                    record_type=args.publish_type,
                    json_payload=args.publish_json,
                    file_path=args.publish_file,
                )
            case "record":
                cmd_reciprocity_record(
                    run_id=args.run_id,
                    session_id=args.session_id,
                    task_id=args.task_id,
                    trace_id=args.trace_id,
                    summary_type=args.summary_type,
                    json_payload=args.record_json,
                    file_path=args.record_file,
                    db_path=args.db_path,
                    event_log_dir=args.event_log_dir,
                    workspace_root=args.workspace_root,
                    provenance_root=args.provenance_root,
                )
            case _:
                raise SystemExit(2)
    except Exception as e:
        print(f"Reciprocity command failed: {e}")
        raise SystemExit(2) from e


def build_ouroboros_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ouroboros", help="Behavioral self-observation tools")
    ouro_sub = parser.add_subparsers(dest="ouroboros_cmd")

    p_ouro_conn = ouro_sub.add_parser("connections", help="Profile module docstrings and surface H0/H1 behavioral structure")
    p_ouro_conn.add_argument("--package-dir", default=None)
    p_ouro_conn.add_argument("--threshold", type=float, default=0.08)
    p_ouro_conn.add_argument("--disagreement-threshold", type=float, default=0.1)
    p_ouro_conn.add_argument("--min-text-length", type=int, default=50)
    p_ouro_conn.add_argument("--limit", type=int, default=15)
    p_ouro_conn.add_argument("--json", dest="as_json", action="store_true")

    p_ouro_record = ouro_sub.add_parser("record", help="Record the latest ouroboros observation into canonical runtime truth")
    p_ouro_record.add_argument("--run-id", default=None)
    p_ouro_record.add_argument("--session-id", default=None)
    p_ouro_record.add_argument("--task-id", default=None)
    p_ouro_record.add_argument("--trace-id", default=None)
    p_ouro_record.add_argument("--log-path", default=None)
    p_ouro_record.add_argument("--cycle-id", default=None)
    p_ouro_record_payload = p_ouro_record.add_mutually_exclusive_group(required=False)
    p_ouro_record_payload.add_argument("--json", dest="observation_json", default=None, help="Inline JSON ouroboros observation payload to record instead of reading the log")
    p_ouro_record_payload.add_argument("--file", dest="observation_file", default=None, help="Path to a JSON ouroboros observation payload file to record instead of reading the log")
    p_ouro_record.add_argument("--db-path", default=None)
    p_ouro_record.add_argument("--event-log-dir", default=None)
    p_ouro_record.add_argument("--workspace-root", default=None)
    p_ouro_record.add_argument("--provenance-root", default=None)


def handle_ouroboros(args: argparse.Namespace) -> None:
    try:
        match args.ouroboros_cmd:
            case "connections":
                cmd_ouroboros_connections(
                    package_dir=args.package_dir,
                    threshold=args.threshold,
                    disagreement_threshold=args.disagreement_threshold,
                    min_text_length=args.min_text_length,
                    limit=args.limit,
                    as_json=args.as_json,
                )
            case "record":
                cmd_ouroboros_record(
                    run_id=args.run_id,
                    session_id=args.session_id,
                    task_id=args.task_id,
                    trace_id=args.trace_id,
                    log_path=args.log_path,
                    cycle_id=args.cycle_id,
                    json_payload=args.observation_json,
                    file_path=args.observation_file,
                    db_path=args.db_path,
                    event_log_dir=args.event_log_dir,
                    workspace_root=args.workspace_root,
                    provenance_root=args.provenance_root,
                )
            case _:
                raise SystemExit(2)
    except Exception as e:
        print(f"Ouroboros command failed: {e}")
        raise SystemExit(2) from e
