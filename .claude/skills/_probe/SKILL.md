---
name: _probe
description: SENTINEL-SCM-SKILL-PROBE-2026-05-17 — visibility test only, not for operational use.
allowed-tools: Read
disable-model-invocation: true
---

# Skill Visibility Probe

This Skill exists solely to verify that `.claude/skills/` is reachable from both main Claude context and Subagent contexts.

**Sentinel string:** `SCM-PROBE-LOADED-OK`

If you can read this, project-scope Skill loading is confirmed working.
Delete this Skill (`rm -rf .claude/skills/_probe/`) once Phase 1 verification is complete.
