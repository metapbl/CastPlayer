# After a file edit: run per-extension checks on the edited files; on failure, return the output to the agent (exit 2).
# Works for Claude Code (Edit/Write/NotebookEdit: tool_input.file_path) and Codex (apply_patch: paths inside tool_input.command).
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
# Check commands per extension. The edited file path is appended last. Empty means do nothing.
# Filled in the docs stage from PRD §6 "per-file checks". Example: '.py' = @('ruff check', 'pyright')
# shortcut: commands are split on spaces only, so arguments cannot contain spaces. Switch to arrays if that is ever needed.
$checks = @{
    '.py' = @('.venv\Scripts\ruff.exe check', 'pyright')   # PRD §6 (D063). pyright는 전역 npm 설치본, 설정은 pyrightconfig.json (D068)
}
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$cwd = if ($data.cwd) { $data.cwd } else { (Get-Location).Path }
# Project root: Claude Code sets CLAUDE_PROJECT_DIR; otherwise the git root of the session folder.
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { git -C $cwd rev-parse --show-toplevel 2>$null }
if (-not $root) { $root = $cwd }
# git reports the resolved root (macOS: /private/var/...) while cwd may use a symlink (/var/...); rebuild cwd on git's root.
elseif (-not $env:CLAUDE_PROJECT_DIR) { $cwd = Join-Path $root (git -C $cwd rev-parse --show-prefix 2>$null) }
$ti = $data.tool_input
$paths = @($ti.file_path, $ti.notebook_path) | Where-Object { $_ }
if ($ti.command -and $data.tool_name -eq 'apply_patch') {
    $paths += [regex]::Matches([string]$ti.command, '(?m)^\*\*\* (?:(?:Add|Update) File|Move to): (.+?)\s*$') | ForEach-Object { $_.Groups[1].Value }
}
$base = [IO.Path]::GetFullPath($root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
$files = foreach ($p in $paths) {
    $full = [IO.Path]::GetFullPath($p, $cwd)
    if ($full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path $full)) { $full }
}
if (-not $files) { exit 0 }
# Mark the turn so the end-of-turn check (finish.ps1) runs. Leave an existing marker alone: it holds finish's block count.
# Files changed by shell commands never reach this hook.
$mark = Join-Path $root '.metarche/.unchecked'
if (-not (Test-Path $mark)) { New-Item -ItemType File -Force $mark | Out-Null }
Set-Location $root
$failed = foreach ($full in $files) {
    foreach ($cmd in @($checks[[IO.Path]::GetExtension($full)])) {
        if (-not $cmd) { continue }
        $exe, $rest = -split $cmd
        $args_ = @($rest | Where-Object { $_ })   # a single argument arrives as a string and would splat into characters
        if (-not (Get-Command $exe)) { "[metarche] check tool not found: $exe. Install it or remove it from .metarche/hooks/check.ps1."; continue }
        $out = & $exe @args_ $full 2>&1
        if ($LASTEXITCODE -ne 0) { "[metarche] check failed: $cmd $full"; $out | Select-Object -First 30 }
    }
}
if ($failed) { [Console]::Error.WriteLine(($failed -join "`n")); exit 2 }
exit 0
