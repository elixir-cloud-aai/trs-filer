#!/bin/sh
#
# This script is meant to be run inside a Kubernetes pod
#
###############################################################################

if [ -z "$CONFIG_MAP_NAME" -o -z "$APISERVER" -o -z "$HOST_NAME" -o -z "$APP_NAME" ];
then
	echo "CONFIG_MAP_NAME, APISERVER, HOST_NAME, and APP_NAME env vars required"
	env
	exit 1
fi

# The base config, installed with the package; found via the package, so
# that no path depends on the image's Python version. An empty path, if the
# package isn't installed, fails below (exit 4)
if [ -z "$APP_CONFIG_PATH" ];
then
  APP_CONFIG_PATH=$(python3 -c 'import importlib.util, os; spec = importlib.util.find_spec("trs_filer"); print(os.path.join(spec.submodule_search_locations[0], "config.yaml") if spec else "")')
fi

if [ -z "$MONGO_HOST" ];
then
  MONGO_HOST='mongodb'
fi

echo "Inputs:"
echo " CONFIG MAP NAME: $CONFIG_MAP_NAME"
echo " API SERVER:      $APISERVER"
echo " APP CONFIG PATH: $APP_CONFIG_PATH"
echo " WES APP NAME:    $APP_NAME"
echo " HOST NAME:       $HOST_NAME"
echo " MONGO_HOST:      $MONGO_HOST"

NAMESPACE=$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)

if [ -z "$NAMESPACE" ];
then
  echo "ERROR: Cannot get the namespace from '/var/run/secrets/kubernetes.io'" >&2
  echo "This script is meant to be run inside a Kubernetes pod only." >&2
  exit 6
fi

echo "Current Kubernetes namespace: $NAMESPACE"; echo

echo " * Getting current default configuration"

APP_CONFIG=$(yq --arg HOST_NAME "$HOST_NAME" \
    --arg MONGO_HOST "$MONGO_HOST" \
    '.custom.service.url_prefix = "https" |
     .custom.service.external_host = $HOST_NAME |
     .custom.service.external_port = 443 |
     .db.host = $MONGO_HOST' \
    "$APP_CONFIG_PATH") || exit 4

echo " * Getting current configMap"
curl -s \
  --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
  -H "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
  -X GET \
  -H "Accept: application/json, */*" \
  -o /tmp/configmap.json \
  -w "Return HTTP/code: %{http_code}\n\n" \
"https://$APISERVER/api/v1/namespaces/${NAMESPACE}/configmaps/${CONFIG_MAP_NAME}"

echo " * Validating JSON file recevied:"; echo
jq . /tmp/configmap.json || exit 2

echo " JSON file is valid";echo

echo " * Creating update for secret"
jq --arg APP_CONFIG "$APP_CONFIG" '.data."config.yaml" = $APP_CONFIG' /tmp/configmap.json >/tmp/configmap-patch.json || exit 5

echo " * Validating JSON file patched:"; echo
jq . /tmp/configmap-patch.json || exit 3

echo " JSON file is valid";echo

# Update Config map
echo " * Updating config map"
curl -s \
  --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
  -H "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
  -X PATCH \
  -H "Accept: application/json, */*" \
  -H "Content-Type: application/strategic-merge-patch+json" \
  -d @/tmp/configmap-patch.json "https://$APISERVER/api/v1/namespaces/${NAMESPACE}/configmaps/${CONFIG_MAP_NAME}" \
  -o /dev/null

echo " * Deleting current $APP_NAME pod"
curl -s \
  --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
  -H "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
  -X GET \
  -H "Accept: application/json, */*" \
  "https://$APISERVER/api/v1/namespaces/${NAMESPACE}/pods/" | \
jq '.items | .[] | .metadata.name ' -r | grep "^${APP_NAME}-" | \
while read pod;
do
  echo "   - Deleting: $pod"
  curl -s \
    --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
    -H "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
    -X DELETE \
    -H "Accept: application/json, */*" \
    -o /dev/null \
    "https://$APISERVER/api/v1/namespaces/${NAMESPACE}/pods/$pod"
done

echo " All Done"
