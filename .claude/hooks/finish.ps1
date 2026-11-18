# Stop: if a file was edited (.claude/.unchecked), run the project-wide checks; on failure, return the output to Claude (exit 2).
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
# Project-wide check commands. No file path is appended. Empty means do nothing.
# Filled in the docs stage from PRD §6 "end-of-turn checks". Example: @('cargo clippy --workspace --all-targets -- -D warnings')
$finish = @(
    '.venv\Scripts\python -m tools.cast_test --selftest'   # PRD §6 (D078). --log 없이: 로그 파일을 남기지 않는다
)
$limit = 2   # most times the same failure blocks; past that the marker is removed so the next turn (even a question) is not blocked
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $data.cwd }
$mark = Join-Path $root '.claude/.unchecked'   # hidden on macOS and Linux, so removing it needs -Force
if (-not (Test-Path $mark)) { exit 0 }
if (-not $finish) { Remove-Item -Force $mark; exit 0 }
Set-Location $root
$failed = foreach ($cmd in $finish) {
    $exe, $rest = -split $cmd
    $args_ = @($rest | Where-Object { $_ })
    if (-not (Get-Command $exe)) { "[metarche] check tool not found: $exe. Install it or remove it from .claude/hooks/finish.ps1."; continue }
    $out = & $exe @args_ 2>&1
    if ($LASTEXITCODE -ne 0) { "[metarche] end-of-turn check failed: $cmd"; $out | Select-Object -Last 40 }
}
if (-not $failed) { Remove-Item -Force $mark; exit 0 }
# The marker holds the block count (check.ps1 creates it only when missing, so it survives while fixing).
$n = [int](Get-Content $mark -Raw) + 1
if ($n -gt $limit) { Remove-Item -Force $mark; exit 0 }
Set-Content $mark $n
$failed = @($failed) + "[metarche] end-of-turn check $n/$limit. If the fix is unclear or would contradict the user's request, do not fix it; ask the user. After $limit failures this stops blocking, so report any remaining failure to the user."
[Console]::Error.WriteLine(($failed -join "`n"))
exit 2
