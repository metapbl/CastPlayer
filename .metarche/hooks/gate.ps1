# Before a file edit: unless docs/PRD.md is approved, block edits outside docs/, the agent folders and the instruction files.
# Works for Claude Code (Edit/Write/NotebookEdit: tool_input.file_path) and Codex (apply_patch: paths inside tool_input.command).
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$cwd = if ($data.cwd) { $data.cwd } else { (Get-Location).Path }
# Project root: Claude Code sets CLAUDE_PROJECT_DIR; otherwise the git root of the session folder.
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { git -C $cwd rev-parse --show-toplevel 2>$null }
if (-not $root) { $root = $cwd }
# git reports the resolved root (macOS: /private/var/...) while cwd may use a symlink (/var/...); rebuild cwd on git's root.
elseif (-not $env:CLAUDE_PROJECT_DIR) { $cwd = Join-Path $root (git -C $cwd rev-parse --show-prefix 2>$null) }
$prd = Join-Path $root 'docs/PRD.md'
if (-not (Test-Path $prd)) { exit 0 }
# '상태:' is the marker used by projects created before the English skill (upgrade U7 migrates it).
if ((Get-Content $prd -Encoding utf8 -TotalCount 5) -match '(Status|상태):\s*approved') { exit 0 }
$ti = $data.tool_input
$paths = @($ti.file_path, $ti.notebook_path) | Where-Object { $_ }
if ($ti.command -and $data.tool_name -eq 'apply_patch') {
    $paths += [regex]::Matches([string]$ti.command, '(?m)^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+?)\s*$') | ForEach-Object { $_.Groups[1].Value }
}
# Resolve the root the same way as the paths so 8.3 short names (ADMINI~1 etc.) compare correctly.
$base = [IO.Path]::GetFullPath($root).Replace('\', '/').TrimEnd('/') + '/'
$blocked = foreach ($p in $paths) {
    # GetFullPath resolves '..', so docs/../src cannot slip through.
    $rel = [IO.Path]::GetFullPath($p, $cwd).Replace('\', '/')
    if ($rel.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) { $rel = $rel.Substring($base.Length) }
    # Files under .claude/worktrees/ are code copies, so they are not allowed.
    if ($rel -notmatch '^(docs/|\.metarche/|\.codex/|\.agents/|\.claude/(?!worktrees/)|(AGENTS|CLAUDE|CLAUDE\.local)\.md$)') { $rel }
}
if (-not $blocked) { exit 0 }
[Console]::Error.WriteLine("[metarche] PRD not approved: editing $($blocked -join ', ') is blocked. Until docs/PRD.md is approved, only documents may change.")
exit 2
