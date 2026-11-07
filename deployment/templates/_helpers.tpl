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
