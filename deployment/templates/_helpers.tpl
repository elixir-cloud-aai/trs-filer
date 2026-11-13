{{/*
Settings of the app for the templates of the library chart foca-common (see
`foca-common.checkSettings` and "Helm library chart" in FOCA's docs), as
YAML; the templates are called with a dict of the root context (`root`) and
these settings (`settings`). They follow the base config in the image
(`trs_filer/config.yaml`): its size limit of request bodies
(`server.max_content_length`), its token issuers (so the library requires an
audience, global or of each issuer: `requireAudience`), its access control,
enabled and enforced with admins required (so the library refuses to render
what the app would refuse on startup: `requireAccessControl`), its database
(`db.dbs`) and that of access control (`security.access_control.db_name`).
The generated config sets the public URL of the app (`custom.service`, for
the `url` of tools and versions) from `hostName`, with HTTPS on port 443, as
TLS is usually terminated by the ingress, the route or a proxy in front of
the cluster. Every template includes the settings, so the app's checks
(`trs-filer.validate`) run first, before those of the library and whichever
template Helm renders first.
*/}}
{{- define "trs-filer.settings" -}}
{{- include "trs-filer.validate" . -}}
valuesKey: trsFiler
maxContentLength: 1048576
requireAudience: true
requireAccessControl: true
mongodb:
  databases: [trsStore]
  accessControlDatabase: trsStore
config:
  custom:
    service:
      url_prefix: https
      external_host: {{ .Values.hostName | toJson }}
      external_port: 443
{{- end -}}

{{/*
Checks of the values and the release specific to this app; renders nothing.
Included by the settings (`trs-filer.settings`), so in every template, before
the library's checks (`foca-common.validate`); the checks of renamed and
removed values come first, so that they are reported instead of their
consequences (e.g., a missing `hostName` for `host_name`).
*/}}
{{- define "trs-filer.validate" -}}
{{- include "trs-filer.checkLegacyValues" . -}}
{{- $_ := required "hostName must be set to the public host name of the app (see deployment/README.md, Configuration)" .Values.hostName -}}
{{- end -}}

{{/*
Fails on values of the charts before foca-common (with the config Job),
which the chart would otherwise ignore; renders nothing.
*/}}
{{- define "trs-filer.checkLegacyValues" -}}
{{- $hint := "(see deployment/README.md, From earlier charts)" -}}
{{- /*
Keys renamed to camelCase, following Helm's conventions; the old keys would
otherwise be ignored
*/ -}}
{{- $renamed := dict
  "host_name" "host_name was renamed to hostName"
  "trs_filer" "trs_filer was renamed to trsFiler, and trs_filer.config moved to the top-level value config"
-}}
{{- range $old := keys $renamed | sortAlpha -}}
{{- if hasKey $.Values $old -}}
{{- fail (printf "%s (camelCase, following Helm conventions): rename it in the values file %s" (get $renamed $old) $hint) -}}
{{- end -}}
{{- end -}}
{{- if hasKey .Values "apiServer" -}}
{{- fail (printf "apiServer was removed with the config Job: the chart renders the config overlay itself; remove it from the values file %s" $hint) -}}
{{- end -}}
{{- $app := .Values.trsFiler -}}
{{- if kindIs "map" $app -}}
{{- $removed := dict
  "appName" "resource names are derived from the release name; set fullnameOverride to choose them at installation"
  "config" "the config overlay is the top-level value config"
  "forwardedAllowIps" "set FORWARDED_ALLOW_IPS in trsFiler.extraEnv to the addresses of the ingress controller or router instead (see deployment/README.md, Forwarded headers)"
-}}
{{- range $key := keys $removed | sortAlpha -}}
{{- if hasKey $app $key -}}
{{- fail (printf "trsFiler.%s was removed with the chart on foca-common: %s %s" $key (get $removed $key) $hint) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if and (kindIs "map" .Values.mongodb) (hasKey .Values.mongodb "dbName") -}}
{{- fail (printf "mongodb.dbName was removed with the chart on foca-common: the app's database is trsStore (that of the base config), so move existing data from trs-filer-db %s" $hint) -}}
{{- end -}}
{{- end -}}

{{/*
Fails on upgrades of releases of the charts before foca-common (with the
config Job), whose resources have other names and selectors: the
upgrade would start the app on a new, empty database (the old claim is kept,
`helm.sh/resource-policy: keep`), or fail on the immutable selector of the
app's Deployment; renders nothing. Releases are recognized by their
Deployments (`trs-filer.failIfLegacy`; not by claims, which uninstalling
such a release keeps). Included once (in the app's ConfigMap template), as it
looks up resources in the cluster. `lookup` finds nothing in `helm template`
and client-side dry runs.
*/}}
{{- define "trs-filer.checkUpgrade" -}}
{{- if .Release.IsUpgrade -}}
{{- $deployments := lookup "apps/v1" "Deployment" .Release.Namespace "" | default dict -}}
{{- range $resource := (get $deployments "items" | default list) -}}
{{- include "trs-filer.failIfLegacy" (dict "root" $ "resource" $resource) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Fails if a Deployment (looked up in the cluster) belongs to this release, but
was created by a chart before foca-common: without the label
`app.kubernetes.io/instance`. Call with a dict of the root context (`root`)
and the Deployment (`resource`).
*/}}
{{- define "trs-filer.failIfLegacy" -}}
{{- $owner := dig "metadata" "annotations" "meta.helm.sh/release-name" "" .resource -}}
{{- $labels := dig "metadata" "labels" dict .resource -}}
{{- if and (eq $owner .root.Release.Name) (not (hasKey $labels "app.kubernetes.io/instance")) -}}
{{- fail (printf "release %s was installed with a chart before foca-common (with the config Job), and upgrading it would start the app on a new, empty database (Deployment %s): uninstall it and install the current chart instead, moving the data as described in deployment/README.md (From earlier charts)" .root.Release.Name (dig "metadata" "name" "" .resource)) -}}
{{- end -}}
{{- end -}}
