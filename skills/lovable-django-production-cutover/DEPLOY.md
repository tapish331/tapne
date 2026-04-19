# Deploy

This file preserves the original deployment intent while moving it out of the
main operator runbook.

Use this file only after the cutover itself is passing:

- `git -C lovable pull --ff-only` succeeded
- `git -C lovable status` is clean
- the production build passes
- live shell verification passes
- real browser verification passes

## Goal

Update the Cloud Run workflow only where needed, then deploy.

## 1. Confirm The Workflow Builds A Fresh Lovable Artifact

`setup-faithful-local.ps1` builds the Docker image but does not guarantee a fresh
Lovable production artifact unless `run-cloud-run-workflow.ps1` invokes
`build-lovable-production-frontend.ps1` first.

Check whether the workflow already builds the artifact before image build.

If the pre-step is missing, modify `run-cloud-run-workflow.ps1` like this:

1. Add:

```powershell
$buildScript = Join-Path $scriptDirectory "build-lovable-production-frontend.ps1"
```

2. Add:

```powershell
$buildArgs = @("-RepoRoot", $repoRoot)
if ($isVerbose) { $buildArgs += "-Verbose" }
```

3. Insert the first workflow step:

```powershell
Invoke-ScriptStep -StepName "1/6 build-lovable-production-frontend" -PowerShellExe $powerShellExe -ScriptPath $buildScript -Arguments $buildArgs
```

4. Renumber the remaining workflow steps accordingly.

## 2. Fix SPA-Era Smoke Paths If Needed

`deploy-cloud-run.ps1` old template defaults:

- `-SmokeCssPath /static/css/tapne.css`
- `-SmokeJsPath /static/js/tapne-ui.js`

These do not fit the Lovable SPA build.

Check whether `$deployArgs` already overrides them with valid SPA-era paths.

If missing, add:

```powershell
"-SmokeCssPath", "/",
"-SmokeJsPath", "/sitemap.xml",
```

Why:

- `/` proves the SPA shell is served
- `/sitemap.xml` proves backend-owned routes are still reachable

## 3. Check Required Secrets And Env Wiring

If the cutover introduced new settings or secrets, make sure the workflow passes
them through to the deployed service.

Always verify these existing values:

| Django setting | Secret Manager name | `.env` key | Required for |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | `tapne-google-client-id` | `GOOGLE_CLIENT_ID` | Google OAuth login button |
| `GOOGLE_CLIENT_SECRET` | `tapne-google-client-secret` | `GOOGLE_CLIENT_SECRET` | Google OAuth callback |
| `BASE_URL` | env-derived | derived from `CANONICAL_HOST` | OAuth redirect URI |

If a new value must flow from `.env` through the workflow, follow the existing
`Get-DotEnvValue` pattern in `run-cloud-run-workflow.ps1`.

## 4. Execute The Workflow

Once the workflow is correct and the cutover gates are already green, run:

```powershell
pwsh -File infra/run-cloud-run-workflow.ps1 -Verbose
```

Report:

- exit code
- deployed service URL
- which deployment sub-steps required changes

## Deployment Stop Rules

Do not deploy if any of these are still failing:

- `lovable/` is not clean after pull
- the build dirties `lovable/`
- mock logic leaked into the production bundle
- live shell checks fail
- browser checks fail
- a known user-visible failure still needs a Lovable prompt
