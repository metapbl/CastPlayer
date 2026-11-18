# PostToolUse(Edit|Write|NotebookEdit): run per-extension checks on the edited file; on failure, return the output to Claude (exit 2).
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
# Check commands per extension. The edited file path is appended last. Empty means do nothing.
# Filled in the docs stage from PRD §6 "per-file checks". Example: '.py' = @('ruff check', 'pyright')
# shortcut: commands are split on spaces only, so arguments cannot contain spaces. Switch to arrays if that is ever needed.
$checks = @{
    '.py' = @('.venv\Scripts\ruff.exe check', 'pyright')   # PRD §6 (D063). pyright는 전역 npm 설치본, 설정은 pyrightconfig.json (D068)
}
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $data.cwd }
$path = [string]($data.tool_input.file_path ?? $data.tool_input.notebook_path)
if (-not $path) { exit 0 }
$full = [IO.Path]::GetFullPath($path, $root)
$base = [IO.Path]::GetFullPath($root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path $full)) { exit 0 }
# Mark the turn so the end-of-turn check (finish.ps1) runs. Leave an existing marker alone: it holds finish's block count.
# Files changed by shell commands never reach this hook.
$mark = Join-Path $root '.claude/.unchecked'
if (-not (Test-Path $mark)) { New-Item -ItemType File -Force $mark | Out-Null }
$cmds = $checks[[IO.Path]::GetExtension($full)]
if (-not $cmds) { exit 0 }
Set-Location $root
$failed = foreach ($cmd in @($cmds)) {
    $exe, $rest = -split $cmd
    $args_ = @($rest | Where-Object { $_ })   # a single argument arrives as a string and would splat into characters
    if (-not (Get-Command $exe)) { "[metarche] check tool not found: $exe. Install it or remove it from .claude/hooks/check.ps1."; continue }
    $out = & $exe @args_ $full 2>&1
    if ($LASTEXITCODE -ne 0) { "[metarche] check failed: $cmd $full"; $out | Select-Object -First 30 }
}
if ($failed) { [Console]::Error.WriteLine(($failed -join "`n")); exit 2 }
exit 0
