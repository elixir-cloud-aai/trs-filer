{{- /* "true" if the chart creates the OpenShift Route (`route.enabled`,
the Ingress disabled and the cluster serving Routes), else empty; used by
the Route and NOTES.txt. `dig`, so that upgrades with `--reuse-values` from
charts without `trs_filer.route` keep the Route */}}
{{- define "trs-filer.route" -}}
{{- if and (dig "route" "enabled" true .Values.trs_filer) (not .Values.trs_filer.ingress.enabled) (.Capabilities.APIVersions.Has "route.openshift.io/v1") -}}
true
{{- end -}}
{{- end -}}

{{- /* Security context from the values; call with a dict of the root context
(`root`) and the context (`context`, empty if unset). On OpenShift, which
assigns user and group IDs from the namespace's range (and rejects others
under the default security context constraints), these IDs are omitted, as
in FOCA's library chart */}}
{{- define "trs-filer.securityContext" -}}
{{- $context := .context | default dict -}}
{{- if .root.Capabilities.APIVersions.Has "security.openshift.io/v1" -}}
{{- $context = omit $context "runAsUser" "runAsGroup" "fsGroup" -}}
{{- end -}}
{{- toYaml $context -}}
{{- end -}}

{{- /* `emptyDir` volume source (flow style) limited to a size (a quantity,
e.g., `64Mi`, or a number of bytes), or without a limit if empty; call with
the size */}}
{{- define "trs-filer.emptyDir" -}}
{{- if . -}}
{sizeLimit: {{ . | quote }}}
{{- else -}}
{}
{{- end -}}
{{- end -}}

{{- /* "true" if MongoDB requires credentials (`mongodb.auth.enabled`), else
empty; off if unset (`dig`), e.g., for upgrades with `--reuse-values` from
charts without the value, whose MongoDB has no users */}}
{{- define "trs-filer.mongodbAuth" -}}
{{- if dig "auth" "enabled" false .Values.mongodb -}}
true
{{- end -}}
{{- end -}}

{{- /* Name of the existing Secret with MongoDB's credentials; fails if unset */}}
{{- define "trs-filer.mongodbSecret" -}}
{{- required "mongodb.auth.existingSecret must be set if mongodb.auth.enabled (the name of a Secret with the keys root-username, root-password, username and password; see the chart's README, Authentication); for existing databases without authentication, create the users first" (dig "auth" "existingSecret" "" .Values.mongodb) -}}
{{- end -}}

{{- /* Environment variables from keys of the Secret with MongoDB's
credentials; call with a dict of the root context (`root`) and a dict
mapping variable names to keys (`vars`), rendered in alphabetical order */}}
{{- define "trs-filer.mongodbSecretEnv" -}}
{{- $secret := include "trs-filer.mongodbSecret" .root -}}
{{- range $name, $key := .vars }}
- name: {{ $name }}
  valueFrom:
    secretKeyRef:
      name: {{ $secret | quote }}
      key: {{ $key }}
{{- end }}
{{- end -}}
