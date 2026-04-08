#!/usr/bin/env bash
# Set up a custom domain front door for Cloud Run using an external HTTPS load balancer.
# Mac equivalent of infra/setup-custom-domain.ps1
#
# Usage:
#   bash infra/setup-custom-domain.sh --verbose
#   bash infra/setup-custom-domain.sh \
#     --project-id tapne-487110 --region asia-south1 \
#     --service-name tapne-web --domain tapnetravel.com --www-domain www.tapnetravel.com
set -Eeuo pipefail
export CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK=1

PROJECT_ID="tapne-487110"
REGION="asia-south1"
SERVICE_NAME="tapne-web"
DOMAIN="tapnetravel.com"
WWW_DOMAIN="www.tapnetravel.com"
LB_SCOPE="global"           # global | regional
RESOURCE_PREFIX=""
NETWORK="default"
ENABLE_HTTP=0               # add HTTP-to-HTTPS redirect listener
UPDATE_CLOUDFLARE_DNS=0
CLOUDFLARE_API_TOKEN=""
CLOUDFLARE_ZONE_ID=""
CLOUDFLARE_PROXIED=0
WAIT_FOR_CERT=1
CERT_WAIT_TIMEOUT=1800      # seconds
CERT_POLL_INTERVAL=15       # seconds
HARDEN_INGRESS=1
CLOUD_RUN_INGRESS="internal-and-cloud-load-balancing"
VALIDATE_ONLY=0
SKIP_AUTH_LOGIN=0
VERBOSE=0

# ── Colours ───────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step()  { echo ""; echo -e "${CYAN}==> $*${NC}"; }
ok()    { echo -e "${GREEN}[OK] $*${NC}"; }
info()  { echo -e "${YELLOW}[INFO] $*${NC}"; }
die()   { echo -e "${RED}[FAILED] $*${NC}" >&2; exit 1; }

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)               PROJECT_ID="$2";             shift 2 ;;
    --region)                   REGION="$2";                 shift 2 ;;
    --service-name)             SERVICE_NAME="$2";           shift 2 ;;
    --domain)                   DOMAIN="$2";                 shift 2 ;;
    --www-domain)               WWW_DOMAIN="$2";             shift 2 ;;
    --lb-scope)                 LB_SCOPE="$2";               shift 2 ;;
    --resource-prefix)          RESOURCE_PREFIX="$2";        shift 2 ;;
    --network)                  NETWORK="$2";                shift 2 ;;
    --enable-http)              ENABLE_HTTP=1;               shift   ;;
    --update-cloudflare-dns)    UPDATE_CLOUDFLARE_DNS=1;     shift   ;;
    --cloudflare-api-token)     CLOUDFLARE_API_TOKEN="$2";   shift 2 ;;
    --cloudflare-zone-id)       CLOUDFLARE_ZONE_ID="$2";     shift 2 ;;
    --cloudflare-proxied)       CLOUDFLARE_PROXIED=1;        shift   ;;
    --no-wait-for-cert)         WAIT_FOR_CERT=0;             shift   ;;
    --cert-wait-timeout)        CERT_WAIT_TIMEOUT="$2";      shift 2 ;;
    --no-harden-ingress)        HARDEN_INGRESS=0;            shift   ;;
    --cloud-run-ingress)        CLOUD_RUN_INGRESS="$2";      shift 2 ;;
    --validate-only)            VALIDATE_ONLY=1;             shift   ;;
    --skip-auth-login)          SKIP_AUTH_LOGIN=1;           shift   ;;
    -v|--verbose)               VERBOSE=1;                   shift   ;;
    -h|--help)
      echo "Usage: $0 [--project-id ID] [--region R] [--service-name S]"
      echo "          [--domain D] [--www-domain W] [--lb-scope global|regional]"
      echo "          [--enable-http] [--no-wait-for-cert] [--no-harden-ingress]"
      echo "          [--update-cloudflare-dns --cloudflare-api-token T --cloudflare-zone-id Z]"
      echo "          [--validate-only] [--skip-auth-login] [--verbose]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

[[ "$VERBOSE" -eq 1 ]] && set -x

# ── Derived names ─────────────────────────────────────────────────────────────
PREFIX="${RESOURCE_PREFIX:-tapne}"
NEG_NAME="${PREFIX}-neg"
BACKEND_NAME="${PREFIX}-backend"
URL_MAP_NAME="${PREFIX}-url-map"
HTTPS_PROXY_NAME="${PREFIX}-https-proxy"
HTTP_PROXY_NAME="${PREFIX}-http-proxy"
SSL_CERT_NAME="${PREFIX}-cert"
STATIC_IP_NAME="${PREFIX}-ip"
HTTPS_RULE_NAME="${PREFIX}-https-rule"
HTTP_RULE_NAME="${PREFIX}-http-rule"
HTTP_REDIRECT_MAP_NAME="${PREFIX}-http-redirect"

# Build unique sorted domain list
DOMAINS=()
for d in "$DOMAIN" "$WWW_DOMAIN"; do
  d="${d,,}"
  [[ -z "$d" ]] && continue
  already=0
  for existing in "${DOMAINS[@]:-}"; do [[ "$existing" == "$d" ]] && { already=1; break; }; done
  [[ "$already" -eq 0 ]] && DOMAINS+=("$d")
done
[[ "${#DOMAINS[@]}" -eq 0 ]] && die "At least one non-empty domain is required."

CANONICAL_HOST="${DOMAINS[0]}"

[[ "$VERBOSE" -eq 1 ]] && echo "[verbose] project=$PROJECT_ID region=$REGION service=$SERVICE_NAME domains=${DOMAINS[*]} lb-scope=$LB_SCOPE prefix=$PREFIX"

# ── Preflight ─────────────────────────────────────────────────────────────────
step "Preflight checks"
command -v gcloud >/dev/null 2>&1 || die "gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"
ok "gcloud is available."

[[ "$VALIDATE_ONLY" -eq 1 ]] && { ok "Validate-only mode: stopping here."; exit 0; }

# ── Auth ──────────────────────────────────────────────────────────────────────
step "Ensuring gcloud authentication"
ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1 || true)"
if [[ -z "$ACTIVE_ACCOUNT" ]]; then
  [[ "$SKIP_AUTH_LOGIN" -eq 1 ]] && die "No active gcloud account and --skip-auth-login was set."
  info "No active gcloud account. Launching interactive login..."
  gcloud auth login
  ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1 || true)"
fi
[[ -n "$ACTIVE_ACCOUNT" ]] || die "No active gcloud account after login."
ok "Using account: $ACTIVE_ACCOUNT"

gcloud config set project "$PROJECT_ID" --quiet

# ── Enable required APIs ──────────────────────────────────────────────────────
step "Enabling required GCP APIs"
gcloud services enable \
  compute.googleapis.com \
  certificatemanager.googleapis.com \
  --project="$PROJECT_ID" --quiet
ok "Required APIs enabled."

# ── Static IP ─────────────────────────────────────────────────────────────────
step "Ensuring static IP address: $STATIC_IP_NAME"
SCOPE_FLAG="--global"
[[ "$LB_SCOPE" == "regional" ]] && SCOPE_FLAG="--region=$REGION"

if gcloud compute addresses describe "$STATIC_IP_NAME" $SCOPE_FLAG \
    --project="$PROJECT_ID" --format='value(address)' >/dev/null 2>&1; then
  ok "Static IP already exists: $STATIC_IP_NAME"
else
  info "Creating static IP: $STATIC_IP_NAME"
  gcloud compute addresses create "$STATIC_IP_NAME" \
    $SCOPE_FLAG \
    --ip-version=IPV4 \
    --project="$PROJECT_ID" \
    --quiet
  ok "Static IP created: $STATIC_IP_NAME"
fi
STATIC_IP="$(gcloud compute addresses describe "$STATIC_IP_NAME" $SCOPE_FLAG \
  --project="$PROJECT_ID" --format='value(address)')"
info "Static IP address: $STATIC_IP"

# ── Serverless NEG ────────────────────────────────────────────────────────────
step "Ensuring Serverless NEG: $NEG_NAME"
if gcloud compute network-endpoint-groups describe "$NEG_NAME" \
    --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "NEG already exists: $NEG_NAME"
else
  info "Creating Serverless NEG: $NEG_NAME"
  gcloud compute network-endpoint-groups create "$NEG_NAME" \
    --region="$REGION" \
    --network-endpoint-type=serverless \
    --cloud-run-service="$SERVICE_NAME" \
    --project="$PROJECT_ID" \
    --quiet
  ok "NEG created: $NEG_NAME"
fi

# ── Backend service ───────────────────────────────────────────────────────────
step "Ensuring backend service: $BACKEND_NAME"
if gcloud compute backend-services describe "$BACKEND_NAME" \
    --global --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "Backend service already exists: $BACKEND_NAME"
else
  info "Creating backend service: $BACKEND_NAME"
  gcloud compute backend-services create "$BACKEND_NAME" \
    --global \
    --load-balancing-scheme=EXTERNAL_MANAGED \
    --project="$PROJECT_ID" \
    --quiet
  ok "Backend service created: $BACKEND_NAME"
fi

NEG_SELF_LINK="$(gcloud compute network-endpoint-groups describe "$NEG_NAME" \
  --region="$REGION" --project="$PROJECT_ID" --format='value(selfLink)')"
EXISTING_BACKENDS="$(gcloud compute backend-services describe "$BACKEND_NAME" \
  --global --project="$PROJECT_ID" --format='value(backends)' 2>/dev/null || true)"
if [[ "$EXISTING_BACKENDS" != *"$NEG_NAME"* ]]; then
  gcloud compute backend-services add-backend "$BACKEND_NAME" \
    --global \
    --network-endpoint-group="$NEG_NAME" \
    --network-endpoint-group-region="$REGION" \
    --project="$PROJECT_ID" \
    --quiet
  ok "NEG added to backend service."
else
  ok "NEG already attached to backend service."
fi

# ── URL map ───────────────────────────────────────────────────────────────────
step "Ensuring URL map: $URL_MAP_NAME"
if gcloud compute url-maps describe "$URL_MAP_NAME" \
    --global --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "URL map already exists: $URL_MAP_NAME"
else
  gcloud compute url-maps create "$URL_MAP_NAME" \
    --global \
    --default-service="$BACKEND_NAME" \
    --project="$PROJECT_ID" \
    --quiet
  ok "URL map created: $URL_MAP_NAME"
fi

# ── SSL certificate ───────────────────────────────────────────────────────────
step "Ensuring Google-managed SSL certificate: $SSL_CERT_NAME"
DOMAIN_LIST="$(IFS=','; echo "${DOMAINS[*]}")"
if gcloud compute ssl-certificates describe "$SSL_CERT_NAME" \
    --global --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "SSL certificate already exists: $SSL_CERT_NAME"
else
  info "Creating Google-managed SSL certificate for: $DOMAIN_LIST"
  gcloud compute ssl-certificates create "$SSL_CERT_NAME" \
    --global \
    --domains="$DOMAIN_LIST" \
    --project="$PROJECT_ID" \
    --quiet
  ok "SSL certificate created: $SSL_CERT_NAME"
fi

# ── HTTPS target proxy ────────────────────────────────────────────────────────
step "Ensuring HTTPS target proxy: $HTTPS_PROXY_NAME"
if gcloud compute target-https-proxies describe "$HTTPS_PROXY_NAME" \
    --global --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "HTTPS proxy already exists: $HTTPS_PROXY_NAME"
else
  gcloud compute target-https-proxies create "$HTTPS_PROXY_NAME" \
    --global \
    --url-map="$URL_MAP_NAME" \
    --ssl-certificates="$SSL_CERT_NAME" \
    --project="$PROJECT_ID" \
    --quiet
  ok "HTTPS proxy created: $HTTPS_PROXY_NAME"
fi

# ── HTTPS forwarding rule ─────────────────────────────────────────────────────
step "Ensuring HTTPS forwarding rule: $HTTPS_RULE_NAME"
if gcloud compute forwarding-rules describe "$HTTPS_RULE_NAME" \
    --global --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "HTTPS forwarding rule already exists: $HTTPS_RULE_NAME"
else
  gcloud compute forwarding-rules create "$HTTPS_RULE_NAME" \
    --global \
    --target-https-proxy="$HTTPS_PROXY_NAME" \
    --address="$STATIC_IP_NAME" \
    --ports=443 \
    --load-balancing-scheme=EXTERNAL_MANAGED \
    --project="$PROJECT_ID" \
    --quiet
  ok "HTTPS forwarding rule created: $HTTPS_RULE_NAME"
fi

# ── HTTP redirect (optional) ──────────────────────────────────────────────────
if [[ "$ENABLE_HTTP" -eq 1 ]]; then
  step "Ensuring HTTP-to-HTTPS redirect"
  if ! gcloud compute url-maps describe "$HTTP_REDIRECT_MAP_NAME" \
      --global --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud compute url-maps import "$HTTP_REDIRECT_MAP_NAME" \
      --global --project="$PROJECT_ID" --source /dev/stdin <<'EOF'
defaultUrlRedirect:
  httpsRedirect: true
  redirectResponseCode: MOVED_PERMANENTLY_DEFAULT
EOF
    ok "HTTP redirect URL map created: $HTTP_REDIRECT_MAP_NAME"
  fi

  if ! gcloud compute target-http-proxies describe "$HTTP_PROXY_NAME" \
      --global --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud compute target-http-proxies create "$HTTP_PROXY_NAME" \
      --global --url-map="$HTTP_REDIRECT_MAP_NAME" \
      --project="$PROJECT_ID" --quiet
  fi

  if ! gcloud compute forwarding-rules describe "$HTTP_RULE_NAME" \
      --global --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud compute forwarding-rules create "$HTTP_RULE_NAME" \
      --global \
      --target-http-proxy="$HTTP_PROXY_NAME" \
      --address="$STATIC_IP_NAME" \
      --ports=80 \
      --load-balancing-scheme=EXTERNAL_MANAGED \
      --project="$PROJECT_ID" --quiet
  fi
  ok "HTTP-to-HTTPS redirect configured."
fi

# ── Harden Cloud Run ingress ──────────────────────────────────────────────────
if [[ "$HARDEN_INGRESS" -eq 1 ]]; then
  step "Hardening Cloud Run ingress to: $CLOUD_RUN_INGRESS"
  gcloud run services update "$SERVICE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --ingress="$CLOUD_RUN_INGRESS" \
    --quiet
  ok "Cloud Run ingress set to: $CLOUD_RUN_INGRESS"
fi

# ── Cloudflare DNS update (optional) ──────────────────────────────────────────
if [[ "$UPDATE_CLOUDFLARE_DNS" -eq 1 ]]; then
  step "Updating Cloudflare DNS"
  [[ -z "$CLOUDFLARE_API_TOKEN" || -z "$CLOUDFLARE_ZONE_ID" ]] \
    && die "--cloudflare-api-token and --cloudflare-zone-id are required with --update-cloudflare-dns"

  CF_PROXY="${CLOUDFLARE_PROXIED:-false}"
  [[ "$CLOUDFLARE_PROXIED" -eq 1 ]] && CF_PROXY="true"

  _cf_upsert() {
    local type="$1" name="$2" content="$3"
    local existing_id
    existing_id="$(curl -sf "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records?type=${type}&name=${name}" \
      -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
      | python3 -c "import sys,json; recs=json.load(sys.stdin).get('result',[]); print(recs[0]['id'] if recs else '')" 2>/dev/null || true)"

    local body="{\"type\":\"${type}\",\"name\":\"${name}\",\"content\":\"${content}\",\"proxied\":${CF_PROXY},\"ttl\":1}"
    if [[ -n "$existing_id" ]]; then
      curl -sf -X PUT "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records/${existing_id}" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "$body" >/dev/null
      info "Updated $type $name → $content"
    else
      curl -sf -X POST "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "$body" >/dev/null
      info "Created $type $name → $content"
    fi
  }

  _cf_upsert "A" "$DOMAIN" "$STATIC_IP"
  [[ -n "$WWW_DOMAIN" ]] && _cf_upsert "CNAME" "$WWW_DOMAIN" "$DOMAIN"
  ok "Cloudflare DNS updated."
fi

# ── Wait for SSL certificate ──────────────────────────────────────────────────
if [[ "$WAIT_FOR_CERT" -eq 1 ]]; then
  step "Waiting for SSL certificate to become ACTIVE (timeout: ${CERT_WAIT_TIMEOUT}s)"
  deadline=$(( $(date +%s) + CERT_WAIT_TIMEOUT ))
  while true; do
    STATUS="$(gcloud compute ssl-certificates describe "$SSL_CERT_NAME" \
      --global --project="$PROJECT_ID" --format='value(managed.status)' 2>/dev/null || true)"
    [[ "$STATUS" == "ACTIVE" ]] && { ok "SSL certificate is ACTIVE."; break; }
    now=$(date +%s)
    if [[ $now -ge $deadline ]]; then
      echo ""
      info "Certificate status: $STATUS"
      info "DNS A record for $CANONICAL_HOST must point to: $STATIC_IP"
      info "SSL provisioning can take up to 60 minutes after DNS propagation."
      echo "[WARN] Certificate did not become ACTIVE within timeout. Check GCP Console." >&2
      break
    fi
    printf '.'
    sleep "$CERT_POLL_INTERVAL"
  done
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}Custom domain setup summary:${NC}"
echo "  Static IP:    $STATIC_IP"
echo "  Domains:      ${DOMAINS[*]}"
echo "  SSL cert:     $SSL_CERT_NAME"
echo "  Backend:      $BACKEND_NAME"
echo "  Ingress:      $CLOUD_RUN_INGRESS"
echo ""
echo "  Point your DNS A record to: $STATIC_IP"
echo "  Then wait up to ~60 min for SSL to activate."
echo ""
ok "Custom domain setup completed."
