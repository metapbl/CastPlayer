# At session start: put the head of docs/PROGRESS.md (above <!-- head:end -->, at most 40 lines) into context.
# Claude Code and Codex both add plain stdout from a SessionStart hook to the context.
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$cwd = if ($data.cwd) { $data.cwd } else { (Get-Location).Path }
# Project root: Claude Code sets CLAUDE_PROJECT_DIR; otherwise the git root of the session folder.
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { git -C $cwd rev-parse --show-toplevel 2>$null }
if (-not $root) { $root = $cwd }
$file = Join-Path $root 'docs/PROGRESS.md'
if (-not (Test-Path $file)) { exit 0 }
$head = foreach ($line in Get-Content $file -Encoding utf8 -TotalCount 60) {
    if ($line -match '<!--\s*head:end') { break }
    $line
}
'[metarche] head of docs/PROGRESS.md (injected automatically)'
@($head) | Select-Object -First 40
# Read the last commit from git: written into the file, it would lag behind after every wrap commit.
$last = git -C $root log -1 --format='%h %s' 2>$null
if ($LASTEXITCODE -eq 0 -and $last) { "- Last commit (git): $last" }
exit 0
