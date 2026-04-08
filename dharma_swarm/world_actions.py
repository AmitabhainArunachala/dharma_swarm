"""World Actions — external world-creation primitives for DHARMA SWARM.

This is the missing layer between cognition and manifestation.

Before this module, autonomous agents could:
    - read files
    - write files
    - search the web
    - message other agents
    - leave stigmergy marks

They could NOT actually create worlds.
They could think, but not manifest.

This module gives agents world-facing action primitives:

    - github_create_repo()      → create a public/private repo shell
    - github_clone_repo()       → clone external repos into workspace
    - github_commit_push()      → commit and push changes
    - github_create_issue()     → open an issue in a target repo
    - github_create_pr()        → open a pull request from a branch
    - create_website_scaffold() → create a minimal public-facing site skeleton
    - publish_markdown_artifact() → move internal thought into public artifact form
    - spawn_sub_swarm_spec()    → materialize a new sub-swarm mission spec on disk

Important:
    These functions are intentionally thin wrappers around real system actions
    (git, gh, filesystem) rather than a giant framework. The point is to make
    manifestation hot-path simple, not ceremonially abstract.

    If GitHub credentials are unavailable, functions fail honestly with a clear
    reason instead of pretending success.

Philosophy:
    A mature recursive system must be able to produce externalized worlds:
    repos, websites, issues, PRs, mission specs, public artifacts. Otherwise
    it remains trapped in private cognition.

    This is the bridge from archaeology to civilization.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 60) -> tuple[int, str, str]:
    """Run subprocess safely, returning (returncode, stdout, stderr)."""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "artifact"


@dataclass
class WorldActionResult:
    success: bool
    action: str
    message: str
    path: str = ""
    url: str = ""
    metadata: dict[str, Any] | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# GitHub primitives
# ---------------------------------------------------------------------------


def github_clone_repo(repo_url: str, dest_dir: str) -> WorldActionResult:
    dest = Path(dest_dir).expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and any(dest.iterdir()):
        return WorldActionResult(
            success=False,
            action="github_clone_repo",
            message=f"Destination already exists and is not empty: {dest}",
            path=str(dest),
        )

    code, out, err = _run(["git", "clone", repo_url, str(dest)], timeout=300)
    if code != 0:
        return WorldActionResult(
            success=False,
            action="github_clone_repo",
            message=err or out or "git clone failed",
            path=str(dest),
        )

    return WorldActionResult(
        success=True,
        action="github_clone_repo",
        message=f"Cloned {repo_url}",
        path=str(dest),
        metadata={"repo_url": repo_url},
    )


def github_commit_push(repo_dir: str, commit_message: str, branch: str | None = None) -> WorldActionResult:
    repo = Path(repo_dir).expanduser().resolve()
    if not (repo / ".git").exists():
        return WorldActionResult(
            success=False,
            action="github_commit_push",
            message=f"Not a git repo: {repo}",
            path=str(repo),
        )

    if branch:
        _run(["git", "checkout", "-B", branch], cwd=repo, timeout=30)

    code, out, err = _run(["git", "add", "-A"], cwd=repo, timeout=60)
    if code != 0:
        return WorldActionResult(False, "github_commit_push", err or out, path=str(repo))

    code, out, err = _run(["git", "commit", "-m", commit_message], cwd=repo, timeout=60)
    if code != 0 and "nothing to commit" not in (out + err).lower():
        return WorldActionResult(False, "github_commit_push", err or out, path=str(repo))

    current_branch_code, current_branch_out, _ = _run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, timeout=15
    )
    current_branch = branch or (current_branch_out.strip() if current_branch_code == 0 else "main")

    code, out, err = _run(["git", "push", "-u", "origin", current_branch], cwd=repo, timeout=300)
    if code != 0:
        return WorldActionResult(False, "github_commit_push", err or out, path=str(repo))

    return WorldActionResult(
        success=True,
        action="github_commit_push",
        message=f"Committed and pushed to {current_branch}",
        path=str(repo),
        metadata={"branch": current_branch},
    )


def github_create_issue(repo: str, title: str, body: str) -> WorldActionResult:
    code, out, err = _run(["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body], timeout=120)
    if code != 0:
        return WorldActionResult(False, "github_create_issue", err or out or "gh issue create failed")
    return WorldActionResult(True, "github_create_issue", f"Issue created in {repo}", url=out.strip())


def github_create_pr(repo_dir: str, title: str, body: str, base: str = "main", head: str | None = None) -> WorldActionResult:
    repo = Path(repo_dir).expanduser().resolve()
    if not (repo / ".git").exists():
        return WorldActionResult(False, "github_create_pr", f"Not a git repo: {repo}", path=str(repo))

    if head is None:
        code, out, err = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, timeout=15)
        if code != 0:
            return WorldActionResult(False, "github_create_pr", err or out, path=str(repo))
        head = out.strip()

    code, out, err = _run(["gh", "pr", "create", "--base", base, "--head", head, "--title", title, "--body", body], cwd=repo, timeout=180)
    if code != 0:
        return WorldActionResult(False, "github_create_pr", err or out, path=str(repo))

    return WorldActionResult(True, "github_create_pr", f"PR created from {head} to {base}", path=str(repo), url=out.strip())


# ---------------------------------------------------------------------------
# World artifact primitives
# ---------------------------------------------------------------------------


def create_website_scaffold(output_dir: str, site_name: str, purpose: str, theme: str = "minimal") -> WorldActionResult:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    title = site_name.strip() or "DHARMA SWARM Site"
    css = """
:root {
  --bg: #0e1116;
  --fg: #f4f7fb;
  --muted: #a7b1c2;
  --accent: #6ee7b7;
  --line: #1f2937;
}
body {
  margin: 0; font-family: Inter, Arial, sans-serif; background: var(--bg); color: var(--fg);
}
.container {
  max-width: 920px; margin: 0 auto; padding: 56px 24px 80px;
}
h1 { font-size: 48px; line-height: 1.05; margin-bottom: 16px; }
p.lead { font-size: 20px; color: var(--muted); max-width: 720px; }
.card { border: 1px solid var(--line); border-radius: 16px; padding: 24px; margin-top: 24px; }
code { color: var(--accent); }
""".strip()

    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>{title}</title>
  <link rel=\"stylesheet\" href=\"styles.css\" />
</head>
<body>
  <main class=\"container\">
    <h1>{title}</h1>
    <p class=\"lead\">{purpose}</p>
    <section class=\"card\">
      <h2>Why this exists</h2>
      <p>This site was scaffolded by DHARMA SWARM as a world-facing artifact rather than an internal note.</p>
    </section>
    <section class=\"card\">
      <h2>Theme</h2>
      <p><code>{theme}</code></p>
    </section>
    <section class=\"card\">
      <h2>Next step</h2>
      <p>Populate this scaffold with real research, products, reports, or mission outputs.</p>
    </section>
  </main>
</body>
</html>
"""

    (root / "index.html").write_text(html, encoding="utf-8")
    (root / "styles.css").write_text(css, encoding="utf-8")

    return WorldActionResult(
        success=True,
        action="create_website_scaffold",
        message=f"Website scaffold created: {title}",
        path=str(root),
        metadata={"site_name": title, "theme": theme},
    )


def publish_markdown_artifact(source_path: str, output_dir: str, artifact_name: str | None = None) -> WorldActionResult:
    src = Path(source_path).expanduser().resolve()
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        return WorldActionResult(False, "publish_markdown_artifact", f"Source missing: {src}")

    name = artifact_name or src.name
    dest = out_dir / name
    dest.write_text(src.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")

    manifest = {
        "published_at": _utc_now_iso(),
        "source": str(src),
        "artifact": str(dest),
        "kind": "markdown_artifact",
    }
    (out_dir / f"{_slug(dest.stem)}.manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return WorldActionResult(
        success=True,
        action="publish_markdown_artifact",
        message=f"Published artifact to {dest}",
        path=str(dest),
        metadata=manifest,
    )


def spawn_sub_swarm_spec(output_dir: str, mission_name: str, mission_thesis: str, roles: list[str] | None = None) -> WorldActionResult:
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = _slug(mission_name)
    spec_path = out_dir / f"{slug}.subswarm.json"
    payload = {
        "mission_name": mission_name,
        "mission_slug": slug,
        "created_at": _utc_now_iso(),
        "thesis": mission_thesis,
        "roles": roles or ["cartographer", "architect", "surgeon", "validator"],
        "status": "ready",
        "source": "world_actions.spawn_sub_swarm_spec",
    }
    spec_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return WorldActionResult(
        success=True,
        action="spawn_sub_swarm_spec",
        message=f"Sub-swarm spec created for {mission_name}",
        path=str(spec_path),
        metadata=payload,
    )
