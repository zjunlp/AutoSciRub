param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("codex", "claude", "openclaw")]
  [string]$Platform,
  [string]$SkillsDir,
  [switch]$Check,
  [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$installArgs = @((Join-Path $repoRoot "scripts/install.py"), $Platform)
if ($SkillsDir) { $installArgs += @("--skills-dir", $SkillsDir) }
if ($Check) { $installArgs += "--check" }
if ($DryRun) { $installArgs += "--dry-run" }
if (Get-Command python -ErrorAction SilentlyContinue) {
  & python @installArgs
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  & py -3 @installArgs
} else {
  throw "Python 3.10+ is required. Install Python, then rerun this command."
}
exit $LASTEXITCODE
