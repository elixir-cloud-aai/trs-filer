{{- /* "true" if the chart creates the OpenShift Route (`route.enabled`,
the Ingress disabled and the cluster serving Routes), else empty; used by
the Route and NOTES.txt. `dig`, so that upgrades with `--reuse-values` from
charts without `trs_filer.route` keep the Route */}}
{{- define "trs-filer.route" -}}
{{- if and (dig "route" "enabled" true .Values.trs_filer) (not .Values.trs_filer.ingress.enabled) (.Capabilities.APIVersions.Has "route.openshift.io/v1") -}}
true
{{- end -}}
{{- end -}}

{{- /* Addresses whose `X-Forwarded-*` headers the app trusts (Gunicorn's
`FORWARDED_ALLOW_IPS`), from `trs_filer.forwardedAllowIps`: a string of
comma-separated entries or a list of strings, joined with commas; every
address (`*`) if unset (`dig`, so that upgrades with `--reuse-values` from
charts without the value keep the earlier behaviour). Spaces around entries
and empty entries are dropped, as Gunicorn ignores them; fails on entries
with spaces inside (which Gunicorn would reject), on other types, and if
nothing is left, as Gunicorn would trust no address */}}
{{- define "trs-filer.forwardedAllowIps" -}}
{{- $value := dig "forwardedAllowIps" "*" .Values.trs_filer -}}
{{- $items := list -}}
{{- if kindIs "string" $value -}}
{{- $items = splitList "," $value -}}
{{- else if kindIs "slice" $value -}}
{{- range $value -}}
{{- if not (kindIs "string" .) -}}
{{- fail "trs_filer.forwardedAllowIps must be a string or a list of strings" -}}
{{- end -}}
{{- $items = concat $items (splitList "," .) -}}
{{- end -}}
{{- else -}}
{{- fail "trs_filer.forwardedAllowIps must be a string or a list of strings" -}}
{{- end -}}
{{- $ips := list -}}
{{- range $items -}}
{{- $ip := trim . -}}
{{- if regexMatch `\s` $ip -}}
{{- fail (printf "trs_filer.forwardedAllowIps: %q must not contain spaces" $ip) -}}
{{- end -}}
{{- if $ip -}}
{{- $ips = append $ips $ip -}}
{{- end -}}
{{- end -}}
{{- if not $ips -}}
{{- fail "trs_filer.forwardedAllowIps must not be empty: set the addresses of the ingress controller or router, or \"*\" for every address" -}}
{{- end -}}
{{- join "," $ips -}}
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
