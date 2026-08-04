param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("codex", "claude", "openclaw")]
  [string]$Platform
)

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$codexMarketplace = Join-Path $repoRoot ".agents/plugins"
$claudeMarketplace = Join-Path $repoRoot ".claude-plugin"
$pluginName = "autoscirub"
$marketplaceName = "autoscirub-local"

function Ensure-Command {
  param([string]$Name)
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Missing command: $Name"
  }
}

switch ($Platform) {
  "codex" {
    Ensure-Command codex
    codex plugin marketplace add $codexMarketplace
    codex plugin add "$pluginName@$marketplaceName"
  }
  "claude" {
    Ensure-Command claude
    claude plugin marketplace add $claudeMarketplace
    claude plugin install "$pluginName@$marketplaceName"
  }
  "openclaw" {
    Ensure-Command openclaw
    try {
      openclaw plugins install $repoRoot --marketplace $claudeMarketplace
    } catch {
      openclaw skills install (Join-Path $repoRoot "plugins/autoscirub/skills/autoscirub")
    }
  }
}
