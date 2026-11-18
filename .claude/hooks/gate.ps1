# PreToolUse(Edit|Write|NotebookEdit): unless docs/PRD.md is approved, block edits outside docs/, .claude/ and CLAUDE.md.
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $data.cwd }
$prd = Join-Path $root 'docs/PRD.md'
if (-not (Test-Path $prd)) { exit 0 }
# '상태:' is the marker used by projects created before the English skill (upgrade U7 migrates it).
if ((Get-Content $prd -Encoding utf8 -TotalCount 5) -match '(Status|상태):\s*approved') { exit 0 }
$path = [string]($data.tool_input.file_path ?? $data.tool_input.notebook_path)
if (-not $path) { exit 0 }
# Resolve '..' so docs/../src cannot slip through.
$rel = [IO.Path]::GetFullPath($path, $root).Replace('\', '/')
# Resolve the root the same way so 8.3 short names (ADMINI~1 etc.) compare correctly.
$base = [IO.Path]::GetFullPath($root).Replace('\', '/').TrimEnd('/') + '/'
if ($rel.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) { $rel = $rel.Substring($base.Length) }
# Files under .claude/worktrees/ are code copies, so they are not allowed.
if ($rel -match '^(docs/|\.claude/(?!worktrees/)|CLAUDE(\.local)?\.md$)') { exit 0 }
[Console]::Error.WriteLine("[metarche] PRD not approved: editing $rel is blocked. Until docs/PRD.md is approved, only documents may change.")
exit 2
