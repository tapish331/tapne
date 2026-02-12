## GCP Artifact Registry Commands (Tapne)

This doc is the “one sheet” for **creating, authenticating, pushing, and verifying** Docker images in **Google Cloud Artifact Registry**.

**Project:** `tapne-487110`  
**Region (near Bengaluru):** `asia-south1`  
**Artifact Registry repo:** `tapne`  
**Registry host:** `asia-south1-docker.pkg.dev`  
**Example image name:** `tapne-web`

---

# 1) First-time setup

## 1.1 Prereqs (one-time per machine)
### Install / update gcloud
```bash
gcloud --version
gcloud components update
```

### Login
```bash
gcloud auth login
```

### Set default project (recommended)
```bash
gcloud config set project tapne-487110
```

Verify:
```bash
gcloud config get-value project
```

---

## 1.2 Enable Artifact Registry API (one-time per project)
```bash
gcloud services enable artifactregistry.googleapis.com --project tapne-487110
```

---

## 1.3 Create a Docker repository (one-time per region per repo)
```bash
gcloud artifacts repositories create tapne \
  --project tapne-487110 \
  --repository-format docker \
  --location asia-south1 \
  --description "Tapne container images"
```

Verify repo exists:
```bash
gcloud artifacts repositories list --project tapne-487110 --location asia-south1
```

### Idempotent note (already exists)
If `create` returns `ALREADY_EXISTS`, the repo is already usable. Treat that as success and continue with push/pull steps.

---

## 1.4 Configure Docker auth for Artifact Registry (one-time per machine)
This writes Docker credential helper config so `docker push/pull` works.

```bash
gcloud auth configure-docker asia-south1-docker.pkg.dev
```

---

## 1.5 Build → Tag → Push (typical first push)
### Build locally
```bash
docker build -f infra/Dockerfile.web -t tapne-web:cloudrun-check .
```

### Tag for Artifact Registry
```bash
docker tag tapne-web:cloudrun-check \
  asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:cloudrun-check
```

### Push
```bash
docker push asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:cloudrun-check
```

---

## 1.6 Verify registry manifest platform (recommended after push)
```bash
docker manifest inspect asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:cloudrun-check
```

You should see at least one `platform` entry with:
- `os: linux`
- `architecture: amd64`

Note: an additional `unknown/unknown` manifest entry is usually normal (BuildKit provenance/attestation) and is not a Cloud Run blocker as long as `linux/amd64` is present.

---

## 1.7 Verify the image exists in the registry
List images:
```bash
gcloud artifacts docker images list \
  asia-south1-docker.pkg.dev/tapne-487110/tapne \
  --include-tags
```

Show tags for a specific image:
```bash
gcloud artifacts docker tags list \
  asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web
```

(You can also verify by pulling it:)
```bash
docker pull asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:cloudrun-check
```

---

## 1.8 Run your readiness checker with registry checks
```bash
bash infra/check-cloud-run-web-image.sh \
  --image tapne-web:cloudrun-check \
  --artifact-image asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:cloudrun-check \
  --service tapne-web \
  --region asia-south1
```

### PowerShell note (important!)
PowerShell **does not** use `\` for line continuation. Use backticks **`** or put it on one line.

Example with backticks:
```powershell
bash infra/check-cloud-run-web-image.sh `
  --image tapne-web:cloudrun-check `
  --artifact-image asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:cloudrun-check `
  --service tapne-web `
  --region asia-south1
```

---

# 2) Maintenance (day-to-day)

## 2.1 “I’m on a new machine, I need to push/pull again”
```bash
gcloud auth login
gcloud config set project tapne-487110
gcloud auth configure-docker asia-south1-docker.pkg.dev
```

---

## 2.2 Push a new version (recommended tagging style)
Use something unique like a **git SHA** (better than reusing `latest`):

```bash
GIT_SHA=$(git rev-parse --short HEAD)
docker build -f infra/Dockerfile.web -t tapne-web:$GIT_SHA .
docker tag tapne-web:$GIT_SHA asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:$GIT_SHA
docker push asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:$GIT_SHA
```

Optional: also tag a moving label like `staging`:
```bash
docker tag tapne-web:$GIT_SHA asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:staging
docker push asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:staging
```

---

## 2.3 List what’s in the registry
Repos:
```bash
gcloud artifacts repositories list --project tapne-487110 --location asia-south1
```

Images (+ tags):
```bash
gcloud artifacts docker images list \
  asia-south1-docker.pkg.dev/tapne-487110/tapne \
  --include-tags
```

Tags for one image:
```bash
gcloud artifacts docker tags list \
  asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web
```

---

## 2.4 Delete old tags/images (cleanup)
Delete a **tag** reference:
```bash
gcloud artifacts docker tags delete \
  asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:cloudrun-check \
  --quiet
```

Delete an **image digest** (more final):
1) Find digest:
```bash
gcloud artifacts docker images list \
  asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web --include-tags
```

2) Delete by digest:
```bash
gcloud artifacts docker images delete \
  asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web@sha256:REPLACE_ME \
  --quiet
```

---

## 2.5 IAM: grant someone else push/pull access (no password sharing)
Grant pull-only:
```bash
gcloud projects add-iam-policy-binding tapne-487110 \
  --member="user:teammate@gmail.com" \
  --role="roles/artifactregistry.reader"
```

Grant push:
```bash
gcloud projects add-iam-policy-binding tapne-487110 \
  --member="user:teammate@gmail.com" \
  --role="roles/artifactregistry.writer"
```

View current bindings:
```bash
gcloud projects get-iam-policy tapne-487110
```

---

## 2.6 Common failures & fixes
### “Unauthenticated / denied”
- Re-run:
```bash
gcloud auth login
gcloud auth configure-docker asia-south1-docker.pkg.dev
```
- Confirm project:
```bash
gcloud config get-value project
```
- Confirm IAM role: they need `artifactregistry.reader` (pull) or `artifactregistry.writer` (push).

### “API not enabled”
```bash
gcloud services enable artifactregistry.googleapis.com --project tapne-487110
```

### “docker-credential-desktop.exe: exec format error” (WSL/Git Bash)
This is a shell mismatch issue (Linux shell trying to execute Windows credential helper directly).

Preferred fixes:
1. Run push/manifest commands from PowerShell.
2. Or run Git Bash from PowerShell (so Windows Docker credential helpers work correctly).

Temporary build-only workaround (public base images):
```bash
export DOCKER_CONFIG="$(mktemp -d)"
printf '{\n  "auths": {}\n}\n' > "$DOCKER_CONFIG/config.json"
docker build -f infra/Dockerfile.web -t tapne-web:cloudrun-check .
unset DOCKER_CONFIG
```

After using temporary helper-free config, restore normal auth before push:
```bash
gcloud auth configure-docker asia-south1-docker.pkg.dev
```

---

# 3) CI / Non-Interactive Auth

## 3.1 Service account flow (simple CI baseline)
Create service account:
```bash
gcloud iam service-accounts create ar-pusher --project tapne-487110
```

Grant Artifact Registry writer:
```bash
gcloud projects add-iam-policy-binding tapne-487110 \
  --member="serviceAccount:ar-pusher@tapne-487110.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
```

Activate account in CI and configure Docker helper:
```bash
gcloud auth activate-service-account --key-file "$GOOGLE_APPLICATION_CREDENTIALS"
gcloud auth configure-docker asia-south1-docker.pkg.dev --quiet
```

## 3.2 Workload identity federation (recommended for long-term CI)
Prefer workload identity federation (no long-lived JSON keys).  
Use your CI provider’s OIDC token to impersonate a Google service account with `roles/artifactregistry.writer`, then run:
```bash
gcloud auth configure-docker asia-south1-docker.pkg.dev --quiet
```
