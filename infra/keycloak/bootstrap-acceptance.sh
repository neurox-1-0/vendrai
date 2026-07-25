#!/usr/bin/env bash
set -euo pipefail

KCADM=/opt/keycloak/bin/kcadm.sh
SERVER=http://keycloak:8080

for attempt in $(seq 1 60); do
  if "$KCADM" config credentials \
    --server "$SERVER" \
    --realm master \
    --user "$KEYCLOAK_ADMIN" \
    --password "$KEYCLOAK_ADMIN_PASSWORD"; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "Keycloak did not become ready" >&2
    exit 1
  fi
  sleep 2
done

create_user() {
  username="$1"
  email="$2"
  role="$3"
  existing_id=$("$KCADM" get users -r neurox -q "username=$username" \
    --fields id --format csv --noquotes | sed -n '2p')
  if [ -z "$existing_id" ]; then
    "$KCADM" create users -r neurox \
      -s "username=$username" \
      -s "email=$email" \
      -s enabled=true \
      -s emailVerified=true
  fi
  "$KCADM" set-password -r neurox \
    --username "$username" \
    --new-password "$KEYCLOAK_E2E_USER_PASSWORD"
  "$KCADM" add-roles -r neurox \
    --uusername "$username" \
    --rolename "$role"
}

create_user requester requester@synthetic.neurox.local requester
create_user analyst analyst@synthetic.neurox.local analyst
create_user procurement procurement@synthetic.neurox.local procurement_approver
create_user compliance compliance@synthetic.neurox.local compliance_approver
create_user finance finance@synthetic.neurox.local finance_approver
create_user auditor auditor@synthetic.neurox.local auditor
create_user admin admin@synthetic.neurox.local admin

client_id=$("$KCADM" get clients -r neurox -q clientId=neurox-e2e \
  --fields id --format csv --noquotes | sed -n '2p')
if [ -z "$client_id" ]; then
  client_id=$("$KCADM" create clients -r neurox \
    -s clientId=neurox-e2e \
    -s enabled=true \
    -s publicClient=false \
    -s serviceAccountsEnabled=true \
    -s standardFlowEnabled=false \
    -s directAccessGrantsEnabled=true \
    -s "secret=$KEYCLOAK_E2E_CLIENT_SECRET" \
    -i)
else
  "$KCADM" update "clients/$client_id" -r neurox \
    -s "secret=$KEYCLOAK_E2E_CLIENT_SECRET"
fi

create_mapper() {
  mapper_name="$1"
  mapper_type="$2"
  shift 2
  existing=$("$KCADM" get "clients/$client_id/protocol-mappers/models" \
    -r neurox -q "name=$mapper_name" --fields id --format csv --noquotes \
    | sed -n '2p')
  if [ -z "$existing" ]; then
    "$KCADM" create "clients/$client_id/protocol-mappers/models" -r neurox \
      -s "name=$mapper_name" \
      -s protocol=openid-connect \
      -s "protocolMapper=$mapper_type" \
      "$@"
  fi
}

create_mapper tenant-id oidc-hardcoded-claim-mapper \
  -s 'config."claim.name"=tenant_id' \
  -s 'config."claim.value"=00000000-0000-0000-0000-000000000001' \
  -s 'config."jsonType.label"=String' \
  -s 'config."access.token.claim"=true' \
  -s 'config."id.token.claim"=true'

create_mapper audience-neurox-api oidc-audience-mapper \
  -s 'config."included.custom.audience"=neurox-api' \
  -s 'config."access.token.claim"=true'
