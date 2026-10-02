#!/bin/sh
# Generates /env.js (runtime config, D7) and the security headers from CHASKI_* variables.
set -eu

# Values are URLs/ids: refuse quotes, backslashes and angle brackets instead of escaping them.
esc() {
  case "$1" in
    *\"* | *\\* | *\<* | *\>*)
      echo "40-chaski-env: invalid character in a CHASKI_* value" >&2
      exit 1
      ;;
  esac
  printf '%s' "$1"
}

AUTH_MODE=$(esc "${CHASKI_AUTH_MODE:-dev}")
ENV_NAME=$(esc "${CHASKI_ENV:-DEV}")
CUENTAS=$(esc "${CHASKI_CUENTAS_API_URL:-http://localhost:8001}")
CORE=$(esc "${CHASKI_CORE_API_URL:-http://localhost:8002}")
IA=$(esc "${CHASKI_IA_API_URL:-http://localhost:8003}")
CLIENT_ID=$(esc "${CHASKI_ENTRA_CLIENT_ID:-}")
TENANT_ID=$(esc "${CHASKI_ENTRA_TENANT_ID:-}")
API_SCOPE=$(esc "${CHASKI_ENTRA_API_SCOPE:-}")
POWERBI=$(esc "${CHASKI_POWERBI_EMBED_URL:-}")

cat > /usr/share/nginx/html/env.js <<JS
window.__CHASKI_CONFIG__ = {
  authMode: "${AUTH_MODE}",
  env: "${ENV_NAME}",
  cuentasApiUrl: "${CUENTAS}",
  coreApiUrl: "${CORE}",
  iaApiUrl: "${IA}",
  entraClientId: "${CLIENT_ID}",
  entraTenantId: "${TENANT_ID}",
  entraApiScope: "${API_SCOPE}",
  powerbiEmbedUrl: "${POWERBI}"
};
JS

# Only the scheme://host[:port] part of each URL goes into the CSP.
origin() { printf '%s' "$1" | sed -E 's#^(https?://[^/]+).*#\1#'; }
CONNECT="'self' $(origin "$CUENTAS") $(origin "$CORE") $(origin "$IA") https://login.microsoftonline.com"

cat > /tmp/chaski-headers.conf <<NGX
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(self), microphone=(), geolocation=()" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src ${CONNECT}; frame-src https://app.powerbi.com https://login.microsoftonline.com; worker-src 'self'; manifest-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
NGX
