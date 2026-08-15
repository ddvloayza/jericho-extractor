#!/usr/bin/env bash
# Agrega a ~/.aws/config la sesion SSO de Intelica y un perfil por cuenta.
#
# Con SSO este archivo NO lleva secretos: solo la URL del portal, la region y
# el mapeo cuenta/rol. Los tokens se cachean aparte en ~/.aws/sso/cache/. Por
# eso se puede versionar y compartir; ~/.aws/credentials, en cambio, nunca.
#
# Es aditivo y no pisa nada: hace backup, y si la sesion ya existe, aborta en
# vez de duplicarla.
#
# Uso:
#   ./setup-aws-profiles.sh
#   aws sso login --sso-session itl-sso

set -euo pipefail

SSO_SESSION="itl-sso"
SSO_START_URL="https://d-9067d6cad4.awsapps.com/start/"
SSO_REGION="eu-south-2"
SSO_ROLE="ItlAWSAllAdm"

CONFIG="${HOME}/.aws/config"

# cuenta:account_id:region(es separadas por coma)
# Los IDs salieron del inventario ya extraido. Portal-QA se agrega abajo,
# aparte, porque todavia no tiene ID conocido.
CUENTAS=(
  "portal-prod:610944808410:eu-south-2"
  "portal-dev:891376942769:eu-south-2"
  "interchange-prod:818835242461:eu-south-2"
  "interchange-dev:861276092327:eu-south-2"
  "analytics-prod:831926623233:eu-south-2"
  "analytics-dev:221082197632:eu-south-2"
  "intelica-network:954976322048:eu-south-2"
  "audit:060795899335:us-east-1"
)

mkdir -p "$(dirname "${CONFIG}")"
touch "${CONFIG}"

if grep -q "^\[sso-session ${SSO_SESSION}\]" "${CONFIG}"; then
  echo "Ya existe [sso-session ${SSO_SESSION}] en ${CONFIG}." >&2
  echo "No se toca nada. Revisalo a mano si queres regenerarlo." >&2
  exit 1
fi

BACKUP="${CONFIG}.bak-$(date +%Y%m%d-%H%M%S)"
cp "${CONFIG}" "${BACKUP}"
echo "Backup: ${BACKUP}"

{
  echo ""
  echo "[sso-session ${SSO_SESSION}]"
  echo "sso_start_url = ${SSO_START_URL}"
  echo "sso_region = ${SSO_REGION}"
  echo "sso_registration_scopes = sso:account:access"

  for entrada in "${CUENTAS[@]}"; do
    IFS=':' read -r perfil cuenta region <<< "${entrada}"
    echo ""
    echo "[profile ${perfil}]"
    echo "sso_session = ${SSO_SESSION}"
    echo "sso_account_id = ${cuenta}"
    echo "sso_role_name = ${SSO_ROLE}"
    echo "region = ${region}"
    echo "output = json"
  done

  echo ""
  echo "# Portal-QA: descomentar y completar sso_account_id cuando se sepa."
  echo "# [profile portal-qa]"
  echo "# sso_session = ${SSO_SESSION}"
  echo "# sso_account_id = "
  echo "# sso_role_name = ${SSO_ROLE}"
  echo "# region = eu-south-2"
  echo "# output = json"
} >> "${CONFIG}"

echo "Agregados: 1 sesion SSO + ${#CUENTAS[@]} perfiles (Portal-QA queda comentado)."
echo ""
echo "Siguiente paso:"
echo "  aws sso login --sso-session ${SSO_SESSION}"
echo ""
echo "Y para verificar que cada perfil resuelve:"
echo "  for p in $(printf '%s ' "${CUENTAS[@]%%:*}"); do"
echo "    echo -n \"\$p: \"; aws sts get-caller-identity --profile \"\$p\" --query Account --output text 2>&1 | tail -1"
echo "  done"
