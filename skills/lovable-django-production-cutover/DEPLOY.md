# Deploy

This file covers repo-specific Scope 4 mechanics only. It is not the source of
deployment policy.

Use [RULES.md](../../RULES.md) for:

- scope classification: Section 4
- deployment invariants and verification requirements: Section 5
- reporting and close-out: Section 7

Use this file only after the non-deployment cutover work is already green under
those rules.

## 1. Confirm the workflow builds a fresh SPA artifact first

Inspect:

- [infra/run-cloud-run-workflow.ps1](../../infra/run-cloud-run-workflow.ps1)
- [infra/build-lovable-production-frontend.ps1](../../infra/build-lovable-production-frontend.ps1)

The repo-specific requirement is that `run-cloud-run-workflow.ps1` invokes the
Lovable production build before any Docker image build step.

If the pre-step is missing, wire it in using the existing workflow style:

```powershell
$buildScript = Join-Path $scriptDirectory "build-lovable-production-frontend.ps1"
$buildArgs = @("-RepoRoot", $repoRoot)
if ($isVerbose) { $buildArgs += "-Verbose" }
Invoke-ScriptStep -StepName "1/6 build-lovable-production-frontend" -PowerShellExe $powerShellExe -ScriptPath $buildScript -Arguments $buildArgs
```

Then renumber later steps to match the workflow.

## 2. Confirm SPA-era smoke path overrides exist

Inspect the deploy argument assembly in:

- [infra/run-cloud-run-workflow.ps1](../../infra/run-cloud-run-workflow.ps1)
- [infra/deploy-cloud-run.ps1](../../infra/deploy-cloud-run.ps1)

This repo's production-SPA workflow expects smoke-path overrides for the shell
route and a backend-owned route. If they are missing from the workflow args, add:

```powershell
"-SmokeCssPath", "/",
"-SmokeJsPath", "/sitemap.xml",
```

## 3. Check env wiring in the existing workflow style

If the cutover introduced a new deploy-time value, inspect the env-loading logic
in `run-cloud-run-workflow.ps1` and follow the existing `Get-DotEnvValue`
pattern. Use [RULES.md](../../RULES.md) Section 5 for which secrets/settings
must be present; this file does not redefine that list.

## 4. Execute the workflow

When the cutover and deployment gates from [RULES.md](../../RULES.md) are
already satisfied, run:

```powershell
pwsh -File infra/run-cloud-run-workflow.ps1 -Verbose
```

Capture:

- exit code
- deployed service URL
- which workflow files changed, if any

## 5. Close out through the repo contract

- Report deployment work using [RULES.md](../../RULES.md) Section 7.
- Run the `lovable/` exit gate from [RULES.md](../../RULES.md) Section 2 before
  treating the session as complete.
