"""Memory Bridge CLI (stdlib only; run via `PYTHONPATH=<repo>/scripts python3 -m memory_bridge`)."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib import parse as urlparse
from urllib import request as urlrequest

from . import __version__
from .index_build import build_index
from .importer import import_with_format_detection, make_import_document
from .parsers import ParseError
from .parse_conv import glob_conversations, parse_conversation
from .search_lex import search_conversations

# Import MCP server components for the 'mcp' subcommand
try:
    from .mcp_server import MCP_AVAILABLE, mcp as mcp_app, get_repo_root
    _HAS_MCP = MCP_AVAILABLE
except Exception:
    _HAS_MCP = False

_TOTAL_LINE = re.compile(r"^\s*Total conversations:\s*(\d+)\s*$", re.MULTILINE)
_LAST_REBUILD = re.compile(r"^\s*Last rebuilt:\s*(.+)$", re.MULTILINE)
_TIMESTAMP_SAFE = re.compile(r"[^0-9A-Za-z_-]+")

_CANONICAL_DISTRIBUTED_SKILLS = (
    "memory-bridge",
    "memory-bridge-boot",
    "memory-bridge-index",
    "memory-bridge-digest",
    "memory-bridge-import",
    "llm-wiki-compile",
)

AWARENESS_PATHS = {
    "claude": ".claude/CLAUDE.md",
    "codex": ".codex/CODEX.md",
    "opencode": ".opencode/OPENCODE.md",
    "cursor": ".cursorrules",
    "hermes": ".hermes/HERMES.md",
    "pi": ".pi/PI.md",
    "droid": ".factory/DROID.md",
}

AGENT_SKILL_ROOTS = {
    "claude": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".codex" / "skills",
    "opencode": Path.home() / ".config" / "opencode" / "skills",
    "cursor": Path.home() / ".cursor" / "skills",
    "hermes": Path.home() / ".hermes" / "skills",
    "pi": Path.home() / ".pi" / "agent" / "skills",
    "droid": Path.home() / ".agents" / "skills",
}

_AGENT_SKILL_DIRS = {
    "claude": Path.home() / ".claude" / "skills",
    "cursor": Path.home() / ".cursor" / "skills",
    "opencode": Path.home() / ".config" / "opencode" / "skills",
    "codex": Path.home() / ".codex" / "skills",
    "pi": Path.home() / ".pi" / "agent" / "skills",
    "hermes": Path.home() / ".hermes" / "skills",
    "droid": Path.home() / ".agents" / "skills",
}


@dataclass(frozen=True)
class SyncResult:
    target_type: str
    agent: str
    path: Path
    status: str
    changed_items: tuple[str, ...] = ()
    backup_root: Path | None = None
    detail: str = ""


def discover_repo(cli_root: Path | None, cwd: Path) -> Path:
    if cli_root is not None:
        return cli_root.resolve()
    for candidate in [cwd.resolve(), *cwd.resolve().parents]:
        if (candidate / ".cross-agent-memory").exists():
            return candidate
        hub_spec = candidate / "SKILL.md"
        if hub_spec.is_file():
            head = hub_spec.read_text(encoding="utf-8", errors="replace")
            flattened = head.replace("\n", " ").lower()
            if "skill: memory-bridge" in flattened:
                return candidate
    raise SystemExit(f"memory-bridge: could not find repo containing .cross-agent-memory (cwd={cwd})")


def index_snapshot(repo: Path) -> tuple[int | None, str | None]:
    idx_path = repo / "INDEX.md"
    if not idx_path.is_file():
        return None, None
    blob = idx_path.read_text(encoding="utf-8", errors="replace")
    tm = _TOTAL_LINE.search(blob)
    stamp = _LAST_REBUILD.search(blob)
    totals = int(tm.group(1)) if tm else None
    rebuilt = stamp.group(1).strip() if stamp else None
    return totals, rebuilt


def cmd_status(repo: Path) -> int:
    disk_n = len(glob_conversations(repo))
    hdr_n, rebuilt = index_snapshot(repo)
    print(f"Repo root               : {repo}")
    print(f"Conversations on disk   : {disk_n}")
    print(f"INDEX.md total entries  : {hdr_n if hdr_n is not None else '(no INDEX.md)'}")
    print(f"INDEX.md rebuilt label  : {rebuilt if rebuilt else '(unknown)'}")
    return 0


def cmd_health(repo: Path) -> int:
    py = shutil.which("python3") or "(missing)"
    print(f"Repo root               : {repo}")
    print(f"python3                 : {py}")
    print(f"Python runtime          : {sys.version.split()[0]}")
    git_bin = shutil.which("git")
    if git_bin:
        proc = subprocess.run(["git", "--version"], capture_output=True, text=True)
        txt = proc.stdout.strip() if proc.stdout else repr(proc.returncode)
        print(f"git                     : {txt}")
    else:
        print("git                     : (missing)")
    aa = repo / "config" / "topic_aliases.json"
    mf = repo / ".index" / "manifest.json"
    print(f"topic_aliases.json      : {'present' if aa.is_file() else 'MISSING'}")
    print(f".index/manifest.json    : {'present' if mf.is_file() else 'MISSING'}")
    return 0


def cmd_index_check(repo: Path, as_json: bool) -> int:
    disk_n = len(glob_conversations(repo))
    hdr_n, rebuilt = index_snapshot(repo)
    stale = hdr_n is None or hdr_n != disk_n
    if as_json:
        print(
            json.dumps(
                {
                    "disk_count": disk_n,
                    "index_header_count": hdr_n,
                    "rebuilt_label": rebuilt,
                    "status": "stale" if stale else "fresh",
                },
                indent=2,
            )
        )
    else:
        print(f"Disk conversations      : {disk_n}")
        print(f"INDEX header total      : {hdr_n if hdr_n is not None else '(missing)'}")
        print(f"Last rebuilt stamp      : {rebuilt if rebuilt else '(unknown)'}")
        print(f"STATUS                  : {'STALE — run rebuild' if stale else 'FRESH'}")
    return 2 if stale else 0


def cmd_index_rebuild(repo: Path, sidecars: bool) -> int:
    info = build_index(repo, write_sidecars=sidecars)
    print(
        f'rebuilt IST={info["rebuilt_at_ist"]} convs={info["conversation_count"]} '
        f'open_sessions={info["with_open_items"]}'
    )
    return 0


def cmd_search(repo: Path, tokens: list[str], limit: int) -> int:
    query = " ".join(tokens)
    hits = search_conversations(repo, query, limit=limit)
    print(f'Lexical search for "{query}" — {len(hits)} hits\n')
    if not hits:
        print("(no hits — edit config/topic_aliases.json)")
        return 0
    for score, rel in hits:
        pc = parse_conversation(repo, rel)
        oc = len(pc.open_actions) + len(pc.open_decisions)
        topics = ""
        tops = pc.frontmatter.get("topics")
        if isinstance(tops, list):
            topics = ",".join(str(x) for x in tops)
        print(f"{score:.1f}\topen={oc}\t{rel}")
        if topics:
            print(f"           topics={topics}")
    print()
    return 0


def cmd_digest(repo: Path, tokens: list[str], limit: int) -> int:
    topic = " ".join(tokens)
    hits = search_conversations(repo, topic, limit=max(limit * 6, limit))
    rel_paths = [r for _, r in hits][:limit]
    if not rel_paths:
        all_paths = sorted(glob_conversations(repo))
        rel_paths = all_paths[-limit:] if len(all_paths) > limit else list(all_paths)

    print(f'DIGEST — "{topic}" (max {len(rel_paths)} files)\n')
    print("| # | Conversation | Agent | Open |")
    print("|---|--------------|-------|-----|")

    detail_blocks: list[str] = []

    for i, rel in enumerate(rel_paths, start=1):
        pc = parse_conversation(repo, rel)
        oc = len(pc.open_actions) + len(pc.open_decisions)
        fm_topics = pc.frontmatter.get("topics")
        tl = ",".join(str(x) for x in fm_topics) if isinstance(fm_topics, list) else ""
        print(f"| {i} | `{rel}` | {pc.agent_id} | {oc} |")
        blk = [f"### {rel} — agent={pc.agent_id}", f"_topics_: {tl or '(none)'}", ""]
        if pc.open_decisions:
            blk.append("**Pending decisions**")
            blk.extend([f"- [ ] {ln}" for ln in pc.open_decisions])
            blk.append("")
        if pc.open_actions:
            blk.append("**Open action items**")
            blk.extend([f"- [ ] {ln}" for ln in pc.open_actions])
            blk.append("")
        if not pc.open_decisions and not pc.open_actions:
            blk.append("(no open checklist markers found)")
            blk.append("")
        detail_blocks.append("\n".join(blk))

    print()
    print("\n".join(detail_blocks))
    return 0


def resolve_show(repo: Path, needle: str) -> str | None:
    lowered = needle.lower()
    all_paths = glob_conversations(repo)
    cand = [p for p in all_paths if lowered in p.lower()]
    if not cand:
        cand = [p for p in all_paths if lowered in Path(p).stem.lower()]
    cand.sort(reverse=True)
    return cand[0] if cand else None


def cmd_show(repo: Path, needle: str) -> int:
    rel = resolve_show(repo, needle)
    if not rel:
        print("show: no match")
        return 3
    print((repo / rel).read_text(encoding="utf-8", errors="replace").rstrip("\n"))
    return 0


def cmd_demo(repo: Path) -> int:
    build_index(repo, write_sidecars=True)
    _ = cmd_index_check(repo, as_json=False)
    print("(demo rebuild complete)")
    return 0


def cmd_import(repo: Path, files: list[Path], agent_id: str, fmt_hint: str, dry: bool, hub_user: str = "<YOUR_NAME>") -> int:
    had_error = False
    written = 0
    for path in files:
        if not path.is_file():
            print(f"skip (not file): {path}")
            continue
        
        # Try format-aware import first
        try:
            for target_rel, md in import_with_format_detection(
                path,
                agent_id,
                fmt_hint or None,
                hub_user=hub_user,
            ):
                dest = repo / target_rel
                prefix = "DRYRUN " if dry else ""
                print(f"{prefix}{dest.relative_to(repo)}")
                if not dry:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if not md.endswith("\n"):
                        md += "\n"
                    dest.write_text(md, encoding="utf-8")
                    written += 1
        except ParseError as e:
            print(f"parse error for {path}: {e}")
            if path.suffix.lower() not in {".md", ".markdown", ".txt", ".json"}:
                had_error = True
                continue
            print("falling back to raw text import...")
            blob = path.read_text(encoding="utf-8", errors="replace")
            target_rel, md = make_import_document(
                blob,
                agent_id=agent_id,
                imported_from=str(path.resolve()),
                source_format_hint=fmt_hint or "fallback-raw",
                hub_user=hub_user,
            )
            dest = repo / target_rel
            prefix = "DRYRUN " if dry else ""
            print(f"{prefix}{dest.relative_to(repo)} (fallback)")
            if not dry:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not md.endswith("\n"):
                    md += "\n"
                dest.write_text(md, encoding="utf-8")
                written += 1
    
    print(f"Imported files written: {written}")
    return 1 if had_error else 0


# ---------------------------------------------------------------------------
# Skill sync helpers (main branch)
# ---------------------------------------------------------------------------

def _safe_ref_name(ref: str) -> str:
    return _TIMESTAMP_SAFE.sub("-", ref).strip("-") or "ref"


def _git_capture(repo: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed"
        raise RuntimeError(msg)
    return proc.stdout


def _git_capture_bytes(repo: Path, args: list[str]) -> bytes:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        stdout = proc.stdout.decode("utf-8", errors="replace").strip()
        msg = stderr or stdout or f"git {' '.join(args)} failed"
        raise RuntimeError(msg)
    return proc.stdout


def _git_fetch(repo: Path) -> None:
    _git_capture(repo, ["fetch", "origin", "main"])


def _git_ref_text(repo: Path, ref: str, relpath: str) -> str:
    return _git_capture(repo, ["show", f"{ref}:{relpath}"])


def _git_ref_bytes(repo: Path, ref: str, relpath: str) -> bytes:
    return _git_capture_bytes(repo, ["show", f"{ref}:{relpath}"])


def _agent_list(raw: str) -> list[str]:
    agents = [item.strip() for item in raw.split(",") if item.strip()]
    if not agents:
        raise SystemExit("memory-bridge sync-skills: no agents selected")
    unknown = [agent for agent in agents if agent not in AGENT_SKILL_ROOTS]
    if unknown:
        raise SystemExit(f"memory-bridge sync-skills: unknown agents: {', '.join(unknown)}")
    return agents


def _git_list_tree(repo: Path, ref: str, relpath: str) -> list[str]:
    output = _git_capture(repo, ["ls-tree", "-r", "--name-only", ref, relpath])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _use_worktree_source(ref: str) -> bool:
    return ref.strip().lower() in {"worktree", "working-tree", "local"}


def _canonical_skill_names_from_ref(repo: Path, ref: str) -> list[str]:
    if _use_worktree_source(ref):
        return [path.name for path in canonical_memory_bridge_skills(repo)]
    output = _git_capture(repo, ["ls-tree", "-r", "--name-only", ref, "skills"])
    names: set[str] = set()
    for line in output.splitlines():
        relpath = line.strip()
        if not relpath:
            continue
        parts = Path(relpath).parts
        if len(parts) < 2:
            continue
        skill_name = parts[1]
        if skill_name in _CANONICAL_DISTRIBUTED_SKILLS:
            names.add(skill_name)
    if not names:
        raise RuntimeError(f"no canonical distributed skills found at {ref}:skills")
    missing = sorted(set(_CANONICAL_DISTRIBUTED_SKILLS) - names)
    if missing:
        raise RuntimeError(
            f"missing canonical distributed skills at {ref}:skills: {', '.join(missing)}"
        )
    return [skill_name for skill_name in _CANONICAL_DISTRIBUTED_SKILLS if skill_name in names]


def _load_skill_sources(repo: Path, ref: str) -> dict[str, dict[str, bytes]]:
    sources: dict[str, dict[str, bytes]] = {}
    for skill_name in _canonical_skill_names_from_ref(repo, ref):
        file_map: dict[str, bytes] = {}
        if _use_worktree_source(ref):
            skill_root = repo / "skills" / skill_name
            if not skill_root.is_dir():
                raise RuntimeError(f"missing source tree in worktree: {skill_root}")
            for path in sorted(p for p in skill_root.rglob("*") if p.is_file()):
                relpath = path.relative_to(repo).as_posix()
                file_map[relpath] = path.read_bytes()
        else:
            root = f"skills/{skill_name}"
            rel_files = _git_list_tree(repo, ref, root)
            if not rel_files:
                raise RuntimeError(f"missing source tree at {ref}:{root}")
            for relpath in rel_files:
                file_map[relpath] = _git_ref_bytes(repo, ref, relpath)
        sources[skill_name] = file_map
    return sources


def _awareness_source_paths(agents: list[str]) -> dict[str, str]:
    return {agent: AWARENESS_PATHS[agent] for agent in agents}


def _load_awareness_sources(repo: Path, ref: str, agents: list[str]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for relpath in _awareness_source_paths(agents).values():
        if _use_worktree_source(ref):
            sources[relpath] = (repo / relpath).read_text(encoding="utf-8", errors="replace")
        else:
            sources[relpath] = _git_ref_text(repo, ref, relpath)
    return sources


def _copy_tree(src: Path, dest: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _atomic_replace(src: Path, dest: Path) -> None:
    tmp = dest.with_name(f".{dest.name}.tmp-{next(tempfile._get_candidate_names())}")
    if tmp.exists():
        if tmp.is_dir():
            shutil.rmtree(tmp)
        else:
            tmp.unlink()
    shutil.move(str(src), str(tmp))
    if dest.exists():
        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    tmp.replace(dest)


def _write_text_atomic(dest: Path, content: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", dir=str(dest.parent))
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        tmp_path.replace(dest)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _write_bytes_atomic(dest: Path, content: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", dir=str(dest.parent))
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "wb") as handle:
            handle.write(content)
        tmp_path.replace(dest)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _backup_path(root: Path, relpath: str) -> Path:
    return root / relpath


def _backup_target(src: Path, backup_root: Path, relpath: str) -> None:
    backup_dest = _backup_path(backup_root, relpath)
    if backup_dest.exists():
        if backup_dest.is_dir():
            shutil.rmtree(backup_dest)
        else:
            backup_dest.unlink()
    backup_dest.parent.mkdir(parents=True, exist_ok=True)
    _copy_tree(src, backup_dest)


def _sync_agent_skills(
    agent: str,
    source_trees: dict[str, dict[str, bytes | str]],
    backup_root: Path | None,
    dry_run: bool,
) -> SyncResult:
    root = AGENT_SKILL_ROOTS[agent]
    if not root.exists():
        return SyncResult("skills", agent, root, "missing-target", detail="skill root not found")
    changed: list[str] = []
    for skill_name, tree in source_trees.items():
        skill_root = root / skill_name
        expected_files = {
            str(Path(*Path(relpath).parts[2:])): (
                content.encode("utf-8") if isinstance(content, str) else content
            )
            for relpath, content in tree.items()
        }
        current_files: dict[str, bytes] = {}
        if skill_root.exists():
            for path in sorted(p for p in skill_root.rglob("*") if p.is_file()):
                current_files[str(path.relative_to(skill_root))] = path.read_bytes()
        if current_files != expected_files:
            changed.append(skill_name)
    if not changed:
        return SyncResult("skills", agent, root, "already-current")
    if dry_run:
        return SyncResult("skills", agent, root, "updated", tuple(changed), backup_root=backup_root)

    if backup_root is not None:
        for skill_name in changed:
            skill_dir = root / skill_name
            if skill_dir.exists():
                _backup_target(skill_dir, backup_root, f"{agent}/{skill_name}")

    for skill_name in changed:
        skill_dir = root / skill_name
        stage_root = Path(tempfile.mkdtemp(prefix=f"memory-bridge-sync-{agent}-{skill_name}-"))
        try:
            stage_dest = stage_root / skill_name
            for relpath, content in source_trees[skill_name].items():
                file_rel = Path(*Path(relpath).parts[2:])
                payload = content.encode("utf-8") if isinstance(content, str) else content
                _write_bytes_atomic(stage_dest / file_rel, payload)
            root.mkdir(parents=True, exist_ok=True)
            _atomic_replace(stage_dest, skill_dir)
        finally:
            if stage_root.exists():
                shutil.rmtree(stage_root)
    return SyncResult("skills", agent, root, "updated", tuple(changed), backup_root=backup_root)


def _sync_awareness_file(
    repo: Path,
    agent: str,
    content: str,
    backup_root: Path | None,
    dry_run: bool,
) -> SyncResult:
    relpath = AWARENESS_PATHS[agent]
    dest = repo / relpath
    current = dest.read_text(encoding="utf-8", errors="replace") if dest.is_file() else None
    if current == content:
        return SyncResult("awareness", agent, dest, "already-current")
    if dry_run:
        return SyncResult("awareness", agent, dest, "updated", (relpath,), backup_root=backup_root)
    if backup_root is not None and dest.exists():
        _backup_target(dest, backup_root, f"repo/{relpath}")
    _write_text_atomic(dest, content)
    return SyncResult("awareness", agent, dest, "updated", (relpath,), backup_root=backup_root)


def cmd_sync_skills(
    repo: Path,
    *,
    agents: list[str],
    source_ref: str,
    backup: bool,
    dry_run: bool,
) -> int:
    if not _use_worktree_source(source_ref):
        _git_fetch(repo)
    skill_sources = _load_skill_sources(repo, source_ref)
    awareness_sources = _load_awareness_sources(repo, source_ref, agents)
    backup_root = None
    if backup and not dry_run:
        backup_root = (
            Path.home()
            / ".cache"
            / "memory-bridge-framework"
            / "skill-backups"
            / f"{_safe_ref_name(source_ref)}-{next(tempfile._get_candidate_names())}"
        )
        backup_root.mkdir(parents=True, exist_ok=True)

    results: list[SyncResult] = []
    for agent in agents:
        agent_backup = backup_root / agent if backup_root is not None else None
        results.append(_sync_agent_skills(agent, skill_sources, agent_backup, dry_run))
        awareness_backup = backup_root / "awareness" if backup_root is not None else None
        results.append(
            _sync_awareness_file(
                repo,
                agent,
                awareness_sources[AWARENESS_PATHS[agent]],
                awareness_backup,
                dry_run,
            )
        )

    for result in results:
        items = f" items={','.join(result.changed_items)}" if result.changed_items else ""
        backup_txt = f" backup={result.backup_root}" if result.backup_root else ""
        detail = f" detail={result.detail}" if result.detail else ""
        print(
            f"{result.target_type}:{result.agent} status={result.status} path={result.path}"
            f"{items}{backup_txt}{detail}"
        )

    if any(result.status == "failed" for result in results):
        return 1
    if any(result.status == "missing-target" for result in results):
        return 3
    return 0


# ---------------------------------------------------------------------------
# Skill parity helpers (PR #3)
# ---------------------------------------------------------------------------

def canonical_memory_bridge_skills(repo: Path) -> list[Path]:
    skills_dir = repo / "skills"
    if not skills_dir.is_dir():
        return []
    return [
        skills_dir / skill_name
        for skill_name in _CANONICAL_DISTRIBUTED_SKILLS
        if (skills_dir / skill_name).is_dir()
    ]


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dir_file_digests(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    out: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        out[path.relative_to(root).as_posix()] = _file_digest(path)
    return out


def evaluate_skill_parity(repo: Path, agent_id: str) -> dict[str, object]:
    canonical = canonical_memory_bridge_skills(repo)
    if agent_id not in _AGENT_SKILL_DIRS:
        return {
            "agent_id": agent_id,
            "target_dir": None,
            "canonical_count": len(canonical),
            "matched_count": 0,
            "missing": [s.name for s in canonical],
            "drifted": [],
            "ok": False,
        }
    target_root = _AGENT_SKILL_DIRS[agent_id]

    missing: list[str] = []
    drifted: list[str] = []
    matched = 0

    for skill_dir in canonical:
        target_dir = target_root / skill_dir.name
        expected = _dir_file_digests(skill_dir)
        actual = _dir_file_digests(target_dir)
        if not actual:
            missing.append(skill_dir.name)
            continue
        if expected != actual:
            drifted.append(skill_dir.name)
            continue
        matched += 1

    return {
        "agent_id": agent_id,
        "target_dir": str(target_root),
        "canonical_count": len(canonical),
        "matched_count": matched,
        "missing": missing,
        "drifted": drifted,
        "ok": not missing and not drifted and matched == len(canonical),
    }


def cmd_skill_parity(repo: Path, agent_id: str, as_json: bool) -> int:
    result = evaluate_skill_parity(repo, agent_id)
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        if result["ok"]:
            print(
                f"Skill parity: OK ({result['matched_count']}/{result['canonical_count']} canonical Memory Bridge skills match) "
                f"[agent={agent_id}]"
            )
        else:
            missing = ", ".join(result["missing"]) if result["missing"] else "none"
            drifted = ", ".join(result["drifted"]) if result["drifted"] else "none"
            print(
                f"Skill parity: DRIFT detected [agent={agent_id}] "
                f"missing={missing} drifted={drifted}"
            )
    return 0 if result["ok"] else 1


# ---------------------------------------------------------------------------
# MCP probe helpers (PR #3)
# ---------------------------------------------------------------------------

def _sse_read_event(stream, timeout: float = 30.0) -> tuple[str, str]:
    event_name = ""
    data_lines: list[str] = []
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"MCP SSE read timed out after {timeout:.1f}s")
        try:
            readable, _, _ = select.select([stream], [], [], min(remaining, 5.0))
            if not readable:
                continue
        except (io.UnsupportedOperation, OSError):
            pass
        raw = stream.readline()
        if not raw:
            raise RuntimeError("MCP SSE stream closed before expected response")
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if event_name or data_lines:
                return event_name or "message", "\n".join(data_lines)
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())


def _mcp_post_json(url: str, payload: dict[str, object], headers: dict[str, str], timeout: float) -> int:
    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=body,
        method="POST",
        headers={
            **headers,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return getattr(resp, "status", 200)


def _mcp_roundtrip_json(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, dict[str, object], dict[str, str]]:
    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=body,
        method="POST",
        headers={
            **headers,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", 200)
        raw = resp.read().decode("utf-8", errors="replace").strip()
        result = json.loads(raw) if raw else {}
        resp_headers = {str(k): str(v) for k, v in resp.headers.items()}
        return status, result, resp_headers


def _header_lookup(headers: dict[str, str], key: str) -> str:
    lowered = key.lower()
    for header_name, header_value in headers.items():
        if header_name.lower() == lowered:
            return header_value
    return ""


def probe_sse_endpoint(url: str, bearer_token: str = "", timeout: float = 5.0) -> dict[str, object]:
    headers = {"Accept": "text/event-stream"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    req = urlrequest.Request(url, headers=headers, method="GET")
    with urlrequest.urlopen(req, timeout=timeout) as stream:
        read_timeout = max(timeout * 6, 30.0)
        event_name, data = _sse_read_event(stream, timeout=read_timeout)
        if event_name != "endpoint":
            raise RuntimeError(f"Expected first SSE event 'endpoint', got '{event_name}'")
        message_url = urlparse.urljoin(url, data)

        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "memory-bridge-cli", "version": __version__},
            },
        }
        init_status = _mcp_post_json(message_url, init_payload, headers, timeout)

        while True:
            event_name, data = _sse_read_event(stream, timeout=read_timeout)
            if event_name != "message":
                continue
            message = json.loads(data)
            if message.get("id") == 1:
                break

        _mcp_post_json(
            message_url,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            headers,
            timeout,
        )
        list_status = _mcp_post_json(
            message_url,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers,
            timeout,
        )

        while True:
            event_name, data = _sse_read_event(stream, timeout=read_timeout)
            if event_name != "message":
                continue
            message = json.loads(data)
            if message.get("id") == 2:
                tools = (message.get("result") or {}).get("tools") or []
                return {
                    "ok": True,
                    "transport": "sse",
                    "endpoint": url,
                    "message_endpoint": message_url,
                    "initialize_http_status": init_status,
                    "tools_list_http_status": list_status,
                    "tool_count": len(tools),
                    "tool_names": [tool.get("name") for tool in tools],
                }


def probe_streamable_http_endpoint(
    url: str,
    bearer_token: str = "",
    timeout: float = 5.0,
) -> dict[str, object]:
    headers = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "memory-bridge-cli", "version": __version__},
        },
    }
    init_status, init_result, init_headers = _mcp_roundtrip_json(url, init_payload, headers, timeout)
    session_id = (
        _header_lookup(init_headers, "Mcp-Session-Id")
        or _header_lookup(init_headers, "X-Session-Id")
        or _header_lookup(init_headers, "X-Session-ID")
    )
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    _mcp_roundtrip_json(
        url,
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        headers,
        timeout,
    )
    list_status, list_result, _ = _mcp_roundtrip_json(
        url,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers,
        timeout,
    )
    tools = (list_result.get("result") or {}).get("tools") or []
    return {
        "ok": True,
        "transport": "streamable-http",
        "endpoint": url,
        "initialize_http_status": init_status,
        "initialize_result": init_result.get("result") or {},
        "tools_list_http_status": list_status,
        "tool_count": len(tools),
        "tool_names": [tool.get("name") for tool in tools],
        "session_id_present": bool(session_id),
    }


def probe_mcp_endpoint(
    url: str,
    bearer_token: str = "",
    timeout: float = 5.0,
    transport: str = "auto",
) -> dict[str, object]:
    selected_transport = transport
    if selected_transport == "auto":
        selected_transport = "sse" if url.rstrip("/").endswith("/sse") else "streamable-http"
    if selected_transport == "sse":
        return probe_sse_endpoint(url, bearer_token=bearer_token, timeout=timeout)
    if selected_transport == "streamable-http":
        return probe_streamable_http_endpoint(url, bearer_token=bearer_token, timeout=timeout)
    raise ValueError(f"Unsupported MCP transport for probe: {selected_transport}")


def cmd_mcp_check(url: str, bearer_token: str, timeout: float, as_json: bool, transport: str) -> int:
    result = probe_mcp_endpoint(url, bearer_token=bearer_token, timeout=timeout, transport=transport)
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        line = (
            f"MCP health: OK transport={result['transport']} endpoint={result['endpoint']} "
            f"tools={result['tool_count']}"
        )
        if "message_endpoint" in result:
            line += f" message_endpoint={result['message_endpoint']}"
        if result.get("session_id_present") is not None:
            line += f" session_id_present={result['session_id_present']}"
        print(line)
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memory-bridge", description="Local Memory Bridge tools (no APIs).")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--repo", type=Path, default=None, help="Explicit repo root")

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show conversation counts vs INDEX.md")
    sub.add_parser("health", help="Sanity check toolchain + config paths")
    sub.add_parser("demo", help="Rebuild index + sidecars, then check")

    chk = sub.add_parser("check", help="Compare disk vs INDEX.md header")
    chk.add_argument("--json", action="store_true")

    idx = sub.add_parser("index", help="Index operations")
    idx_sub = idx.add_subparsers(dest="idxcmd", required=True)
    idx_rb = idx_sub.add_parser(
        "rebuild", help="Rewrite INDEX.md (+ .index/ sidecars unless disabled)"
    )

    idx_rb.add_argument("--no-sidecars", action="store_true", help="Skip .index/ JSON manifests")

    idx_ck = idx_sub.add_parser(
        "check", help="Compare disk conversations vs INDEX.md header totals"
    )

    idx_ck.add_argument("--json", action="store_true")

    sr = sub.add_parser("search", help="Deterministic lexical search")
    sr.add_argument("query", nargs="+")
    sr.add_argument("--limit", type=int, default=25)

    dg = sub.add_parser("digest", help="Structured digest capped by --limit")
    dg.add_argument("topic", nargs="+")
    dg.add_argument("--limit", type=int, default=10)

    sh = sub.add_parser("show", help="Print conversation matching substring")
    sh.add_argument("needle")

    im = sub.add_parser("import", help="Convert export files -> canonical Markdown")
    im.add_argument("paths", nargs="+", type=Path)
    im.add_argument("--agent-id", default="import")
    im.add_argument("--format", dest="fmt", default="", help="Free-text importer hint label")
    im.add_argument("--user", default="<YOUR_NAME>", help="Hub owner username for frontmatter")
    im.add_argument("--dry-run", action="store_true")

    sync = sub.add_parser("sync-skills", help="Sync canonical memory-bridge skills into agent installs")
    sync.add_argument(
        "--agents",
        default="claude,codex,opencode,cursor,hermes,pi",
        help="Comma-separated agent ids",
    )
    sync.add_argument(
        "--source-ref",
        default="WORKTREE",
        help="Canonical source for skill content: WORKTREE (default) or a git ref such as origin/main",
    )
    sync.add_argument("--no-backup", action="store_true", help="Skip backup creation before overwriting")
    sync.add_argument("--dry-run", action="store_true", help="Report drift without writing files")

    parity = sub.add_parser("skill-parity", help="Read-only parity check for canonical Memory Bridge skills")
    parity.add_argument("--agent", choices=sorted(_AGENT_SKILL_DIRS), required=True)
    parity.add_argument("--json", action="store_true")

    mcp_check = sub.add_parser("mcp-check", help="Read-only live MCP probe against a configured endpoint")
    mcp_check.add_argument("--url", required=True)
    mcp_check.add_argument(
        "--transport",
        choices=["auto", "sse", "streamable-http"],
        default="auto",
        help="Probe transport. Defaults to auto-detect from the URL.",
    )
    mcp_check.add_argument("--bearer-token", default="")
    mcp_check.add_argument("--bearer-token-env", default="")
    mcp_check.add_argument("--timeout", type=float, default=5.0)
    mcp_check.add_argument("--json", action="store_true")

    # MCP server subcommand
    mcp = sub.add_parser("mcp", help="Run MCP server (stdio, SSE, or Streamable HTTP)")
    mcp.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport mode",
    )
    mcp.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host for remote HTTP transports (default: 127.0.0.1)",
    )
    mcp.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for remote HTTP transports (default: 8000)",
    )

    return p


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    cwd = Path.cwd()
    repo = discover_repo(ns.repo, cwd)
    cmd = ns.command

    if cmd == "status":
        return cmd_status(repo)
    if cmd == "health":
        return cmd_health(repo)
    if cmd == "demo":
        return cmd_demo(repo)
    if cmd == "check":
        return cmd_index_check(repo, as_json=getattr(ns, "json", False))
    if cmd == "index":
        if ns.idxcmd == "rebuild":
            return cmd_index_rebuild(repo, sidecars=(not getattr(ns, "no_sidecars", False)))
        if ns.idxcmd == "check":
            return cmd_index_check(repo, as_json=getattr(ns, "json", False))
        parser.error("unsupported index command")
        return 1
    if cmd == "search":
        return cmd_search(repo, ns.query, ns.limit)
    if cmd == "digest":
        return cmd_digest(repo, ns.topic, ns.limit)
    if cmd == "show":
        return cmd_show(repo, ns.needle)
    if cmd == "import":
        return cmd_import(repo, ns.paths, ns.agent_id, ns.fmt, ns.dry_run, hub_user=ns.user)
    if cmd == "sync-skills":
        try:
            return cmd_sync_skills(
                repo,
                agents=_agent_list(ns.agents),
                source_ref=ns.source_ref,
                backup=(not ns.no_backup),
                dry_run=ns.dry_run,
            )
        except RuntimeError as exc:
            print(f"sync-skills: {exc}", file=sys.stderr)
            return 1
    if cmd == "skill-parity":
        return cmd_skill_parity(repo, ns.agent, as_json=getattr(ns, "json", False))
    if cmd == "mcp-check":
        bearer_token = ns.bearer_token
        if not bearer_token and ns.bearer_token_env:
            bearer_token = os.environ.get(ns.bearer_token_env, "")
        return cmd_mcp_check(
            ns.url,
            bearer_token,
            ns.timeout,
            as_json=getattr(ns, "json", False),
            transport=ns.transport,
        )
    if cmd == "mcp":
        if not _HAS_MCP:
            print("Error: MCP server not available. Install with: pip install 'mcp[cli]'")
            return 1
        # Set repo path from the discovered repo
        os.environ["MEMORY_BRIDGE_REPO"] = str(repo)
        print(f"Memory Bridge MCP Server: {repo}", file=sys.stderr)
        if ns.transport in {"sse", "streamable-http"}:
            # Configure host/port for remote HTTP modes.
            mcp_app.settings.host = ns.host
            mcp_app.settings.port = ns.port
            # Allow any host on Tailscale network (defense in depth: Tailscale provides encryption)
            mcp_app.settings.transport_security.allowed_hosts = ["*", "<YOUR_VPS_TAILSCALE_IP>:*", "<YOUR_VPS_TAILSCALE_IP>"]
            if ns.transport == "sse":
                print(f"Starting SSE server on {ns.host}:{ns.port}", file=sys.stderr)
            else:
                print(f"Starting Streamable HTTP server on {ns.host}:{ns.port}", file=sys.stderr)
        mcp_app.run(transport=ns.transport)
        return 0
    parser.error(f"Unhandled command {cmd!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
