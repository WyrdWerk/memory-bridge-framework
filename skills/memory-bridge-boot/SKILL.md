---
name: memory-bridge-boot
description: Lightweight awareness boot for the Agentic Memory Hub. Syncs remote, counts conversations, checks skill installation, verifies MCP readiness, confirms readiness.
---

# memory-bridge-boot — Agentic Memory Hub Awareness Protocol

**Purpose:** Boot into awareness of the Agentic Memory Hub. Sync with remote, count conversations, check skill installation, verify MCP readiness, confirm readiness — without context bloat.

**When to use:** Start of a session in the agentic-memory-hub repo, or when user says "memory-bridge-boot", "boot memory bridge", or "sync memory hub".

---

## EXECUTION SEQUENCE

### Step 1: Repo Detection

```
🔍 VERIFYING — Agentic Memory Hub repo
```

Search for the repo by checking ANY of:
- File `.cross-agent-memory` exists in a directory
- `SKILL.md` with `skill: memory-bridge` in its frontmatter
- Git remote URL containing `agentic-memory-hub`

Check these locations: `~/`, `~/projects/`, `~/memory-bridge-framework/`, current working directory.

**If not found:** Clone it.
```bash
git clone https://github.com/<YOUR_USERNAME>/memory-bridge-framework.git
```
Then enter the directory.

**If found:** Note the exact path. Proceed.

### Step 2: Remote Sync

```
🔍 VERIFYING — Remote sync
```

```bash
git pull origin main
```

If no remote configured:
```bash
git remote add origin https://github.com/<YOUR_USERNAME>/memory-bridge-framework.git
git pull origin main
```

Verify: on `main` branch, up to date with `origin/main`. If behind, pull again. If ahead, note unpushed local commits.

### Step 3: GitHub CLI Verification

```
🔍 VERIFYING — GitHub CLI
```

```bash
gh auth status
gh repo view --json name,updatedAt,pushedAt,defaultBranchRef
```

If `gh` is missing or unauthenticated: note the gap, continue without blocking.

### Step 4: Read the Specification

Read these files in full from the repo root:
- `SKILL.md` — canonical memory-bridge spec (file structure, format, triggers, workflow)
- `README.md` — quick-start per agent
- `templates/conversation.md` — conversation template

### Step 5: Count Conversations

```
🔍 VERIFYING — Conversation inventory
```

Glob for `conversations/**/*.md` and count the total number of files. Extract agent IDs and dates from filenames only (format: `YYYYMMDD-HHMMSS-{agent}.md`). Do NOT read conversation contents — this avoids context bloat while confirming awareness of the repo's state.

### Step 6: Check Skill Installation for THIS Agent

Identify which agent you are. Then check if the memory-bridge skill is installed:

| Agent | Check this path |
|-------|----------------|
| OpenCode | `~/.config/opencode/skills/memory-bridge/SKILL.md` |
| Claude Code | `.claude/CLAUDE.md` in repo OR `~/.claude/CLAUDE.md` |
| Cursor | `.cursorrules` in repo |
| Codex | `.codex/CODEX.md` in repo |

| Pi | `.pi/PI.md` in repo |
| Hermes | `.hermes/HERMES.md` in repo |

**If NOT found:** Install it. Copy the relevant per-agent instructions file from the repo root to the correct location. Then confirm installation.

**If found:** Confirm with agent ID.

### Step 7: Read-only Skill Parity Check

Run a read-only parity check for the **6 canonical distributed skills** against this agent's local installed copies:

```bash
./bin/memory-bridge skill-parity --agent {your_id}
```

The 6 skills are: memory-bridge, memory-bridge-boot, memory-bridge-index, memory-bridge-digest, memory-bridge-import, llm-wiki-compile.

**CRITICAL:** The parity check only reports "drifted" — it does NOT tell you direction (local ahead vs canonical ahead) or verify the files are actually different. Always verify before claiming direction in output.

**Report in one brief line:**
- If OK: "Skill parity: OK"
- If drift detected: "Skill parity: drift detected — verification needed" (DO NOT say "local ahead" without checking)

Do NOT sync here. If drift is detected, note it and continue to Step 9 output.

#### If User Asks "What's the Drift?" (Or You Need to Verify)

When drift is detected, immediately verify with diff + md5sum before claiming direction:

```bash
cd ~/memory-bridge-framework
diff -u skills/{skill-name}/SKILL.md ~/.hermes/skills/{skill-name}/SKILL.md | head -80
```

**Interpretation guide:**

| Pattern | Meaning | Action |
|---------|---------|--------|
| `--- skills/...` `+++ ~/.hermes/...` with `+` lines | **Local is AHEAD** — your improvements not yet in canonical | Recommend syncing canonical → local repo when ready |
| `--- skills/...` `+++ ~/.hermes/...` with `-` lines | **Local is BEHIND** — canonical has updates you lack | Recommend updating local skills from canonical |

Report: which skills drifted, which direction, and 1-2 bullet summary of key differences (new sections, added pitfalls, etc.).

### Step 8: MCP Configuration + Live Health Check

Check that this agent has a local MCP config entry for `memory-bridge`, then run one lightweight live MCP probe against the configured endpoint.

Use the current agent's config path:

| Agent | Check this path | Default URL |
|-------|----------------|-------------|
| OpenCode | `~/.config/opencode/mcp_servers.json` | `http://<YOUR_VPS_TAILSCALE_IP>:8080/sse` |
| Claude Code | `~/.claude/mcp_servers.json` or project MCP config | `http://<YOUR_VPS_TAILSCALE_IP>:8080/sse` |
| Cursor | `~/.cursor/mcp.json` | `http://<YOUR_VPS_TAILSCALE_IP>:8080/sse` |
| Codex | `~/.codex/config.toml` | `http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp` |

| Pi | `~/.pi/agent/mcp.json` | `http://<YOUR_VPS_TAILSCALE_IP>:8080/sse` |
| Hermes | agent-local config under `.hermes/` | (runs server, doesn't connect as client) |

**Port mapping:**
- **:8080/sse** — SSE transport for Cursor, Claude, OpenCode, Pi, Droid
- **:8081/mcp** — Streamable HTTP transport for Codex

If `memory-bridge` is configured, run:

```bash
./bin/memory-bridge mcp-check --url {configured_url}
```

If a bearer token env var is used, pass it with `--bearer-token-env {ENV_VAR}`.

If MCP config is missing or the probe fails: warn and continue. Do NOT block boot.

### Step 9: Output Awareness Summary

```
✅ CONFIRMED — Memory Hub awareness complete
```

Produce this structured output:

#### REPO STATUS
- Local path
- Branch and sync state (up to date / behind by N / ahead by N)
- Total conversation count
- Date range (earliest to latest, from filenames)
- Agents with saved conversations (from filenames)

#### SKILL STATUS
Whether memory-bridge is installed for your agent ID, or was just installed during this boot.

#### MCP STATUS
- Config present / missing
- Live probe healthy / degraded

#### SKILL PARITY
- One brief line: OK or drift detected
  - "Skill parity: OK" — all 5 skills match
  - "Skill parity: drift detected — verification needed" — run diff/md5sum before claiming direction
  - "Skill parity: 1 skill needs sync (name)" — after verification, specific drift identified
  - "Skill parity: {N} skills drifted — see details above" — if user asked for diff output

### Step 10: Final confirmation

Optionally verify deterministic index/hash parity when `./bin/memory-bridge` exists:

```bash
./bin/memory-bridge check
```

**Note on MCP role:**
- **Hermes on VPS**: Runs the MCP server (both ports 8080 and 8081)
- **All other agents**: Connect as clients to the VPS-hosted server

End with a single line:

```
✅ Memory Bridge boot complete. {N} conversations indexed. Agent ID: {your_id}. Skill: installed/just-installed. MCP: healthy/degraded. Ready to save.
```

---

## ANTI-BLOAT RULES

- Do NOT read conversation contents. Count files and extract metadata from filenames only.
- Do not skip the skill installation check.
- Do not bloat the output with full parity details — one line only.
- Do not skip the remote sync. Stale local state defeats the purpose.
- Keep output minimal — repo status + skill status + one-line confirmation.

## PITFALLS (Hard-learned)

### Pitfall: Assuming "drift" means "local ahead"

**What went wrong:** After a user syncs skills from local to canonical, the parity check may still report "drift detected" for skills that are now actually identical (cached check, or timing). Reporting "local ahead" in the summary when you haven't verified is wrong and confusing.

**The rule:**
1. Parity check says "drift" → Report "drift detected — verification needed" in summary
2. Only say "local ahead" or "canonical ahead" AFTER running `diff` or `md5sum` to verify
3. Recent sync? Verify with `md5sum canonical/SKILL.md local/SKILL.md` — if hashes match, there's no actual drift

**Example from this session:**
- Parity check: "drifted=memory-bridge, memory-bridge-boot"
- Actual state after md5sum: `memory-bridge` identical (user had just synced it), only `memory-bridge-boot` truly drifted
- Wrong output: "Skill parity: DRIFT — local ahead (memory-bridge, memory-bridge-boot)"  ❌
- Right output: "Skill parity: drift detected — 1 skill needs sync (memory-bridge-boot)" after verification ✅

### Pitfall: Not verifying immediately when called out

When the user challenges your drift claim ("we just updated 5 minutes ago"), immediately run `diff` and `md5sum` to verify actual file state. Don't defend — verify.

### Pitfall: Checking only SKILL.md, missing references/ subdirectory

**What went wrong:** Ran `md5sum` on SKILL.md files, saw they matched, declared skills "identical." But the parity check was comparing **entire skill directories** — the `references/` subdirectory had 2 files locally that didn't exist in canonical.

**The rule:** Complete verification requires checking BOTH:
1. **SKILL.md content:** `md5sum canonical/SKILL.md local/SKILL.md`
2. **Directory structure:** `diff -r canonical/references/ local/references/` or `ls -la` both directories

**Verification sequence when drift is reported:**
```bash
# 1. Check main file
diff canonical/skills/{name}/SKILL.md ~/.hermes/skills/{name}/SKILL.md

# 2. Check references directory exists and has same files
ls canonical/skills/{name}/references/ 2>/dev/null || echo "Missing in canonical"
ls ~/.hermes/skills/{name}/references/ 2>/dev/null || echo "Missing locally"
diff -r canonical/skills/{name}/references/ ~/.hermes/skills/{name}/references/ 2>&1
```

**Remember:** "Drift" can mean missing files, not just different content. The parity tool compares directories, not just the main SKILL.md.

---

## MCP SERVER DEPLOYMENT (VPS-SIDE)

When deploying the Memory Bridge MCP server on a VPS for remote agents (Codex, Claude Code, etc.) over Tailscale:

### Dual-Transport Setup

The server supports both SSE (legacy) and Streamable HTTP (modern):

```bash
# Terminal 1: Legacy SSE endpoint (older MCP clients)
export MEMORY_BRIDGE_REPO=~/memory-bridge-framework
./bin/memory-bridge mcp --transport sse --host <YOUR_VPS_TAILSCALE_IP> --port 8080

# Terminal 2: Streamable HTTP endpoint (Codex, modern clients)
export MEMORY_BRIDGE_REPO=~/memory-bridge-framework
./bin/memory-bridge mcp --transport streamable-http --host 0.0.0.0 --port 8081
```

### Critical Pitfalls

| Issue | Symptom | Fix |
|-------|---------|-----|
| `--repo` flag rejected | `error: unrecognized arguments: --repo` | Use `MEMORY_BRIDGE_REPO` env var instead |
| mcp-check JSON parse error | `json.decoder.JSONDecodeError` on Streamable HTTP | Manual curl verification works; built-in check expects pure JSON but server returns SSE-wrapped JSON |
| Port already in use | `Address already in use` | Check with `ss -tlnp \| grep 8080` and kill existing process |

### Manual Verification (When mcp-check Fails)

```bash
# Streamable HTTP endpoint test
curl -s -X POST http://<YOUR_VPS_TAILSCALE_IP>:8081/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {"name": "test", "version": "1.0"}
    }
  }'

# Expected: SSE-formatted JSON response with protocolVersion and serverInfo
```

### Background Process Management

```bash
# Start in background (no systemd yet)
export MEMORY_BRIDGE_REPO=~/memory-bridge-framework
./bin/memory-bridge mcp --transport streamable-http --host 0.0.0.0 --port 8081 &

# Verify it's running
ss -tlnp | grep 8081
ps aux | grep "memory-bridge mcp"
```

---

## ERROR HANDLING

| Situation | Response |
|-----------|----------|
| Repo not found anywhere | Clone from GitHub. If clone fails, report and stop. |
| `git pull` fails | Check network, check SSH key. Report error, continue with local state. |
| `gh` not available | Note gap, continue. Do not block. |
| Zero conversations in repo | Report empty repo. Skill check still runs. |
| Skill not installed for this agent | Install it, then confirm. Do not skip. |
| MCP config missing or probe fails | Mark MCP degraded, include one remediation hint, continue. |
| `--repo` flag rejected by mcp subcommand | Use `MEMORY_BRIDGE_REPO` env var instead (see MCP Server Deployment section) |
| mcp-check fails on Streamable HTTP with JSON error | Use manual curl with `Accept: application/json, text/event-stream` header (see MCP Server Deployment section) |
| User asks to review/merge a PR | **Always check if PR modifies conversation files.** Use `memory-bridge/references/clean-merge-pattern.md` if PR deletes/truncates conversation files. |

---

## RELATIONSHIP TO OTHER SKILLS

- **memory-bridge** (the save skill): This boot skill confirms repo awareness and readiness. The save skill writes new conversations. Boot confirms, save writes.
- **boot-session**: That boots the Solvency Stack session context. This boots the memory hub. They serve different purposes and can run independently.

---

## REFERENCES

- `references/mcp-streamable-http-deployment.md` — MCP server setup with dual-port configuration (SSE on :8080, Streamable HTTP on :8081) for Tailscale-connected agents.
- `references/drift-investigation-and-resolution.md` — Complete workflow for investigating skill drift (local ahead vs behind) and executing sync in either direction.
- `references/skill-sync-verification.md` — Step-by-step verification when parity check reports drift, including directory structure comparison.
