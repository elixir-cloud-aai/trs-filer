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
`FORWARDED_ALLOW_IPS`), from `trs_filer.forwardedAllowIps`: a string or a
list, joined with commas, without spaces and empty entries; every address (`*`) if unset (`dig`, so that
upgrades with `--reuse-values` from charts without the value keep the
earlier behaviour). Fails if empty, as Gunicorn would trust no address */}}
{{- define "trs-filer.forwardedAllowIps" -}}
{{- $ips := dig "forwardedAllowIps" "*" .Values.trs_filer -}}
{{- if kindIs "slice" $ips -}}
{{- $ips = join "," $ips -}}
{{- end -}}
{{- if not (kindIs "string" $ips) -}}
{{- fail "trs_filer.forwardedAllowIps must be a string or a list of strings" -}}
{{- end -}}
{{- /* Without spaces and empty entries, which Gunicorn ignores */ -}}
{{- $ips = join "," (compact (splitList "," (nospace $ips))) -}}
{{- if not $ips -}}
{{- fail "trs_filer.forwardedAllowIps must not be empty: set the addresses of the ingress controller or router, or \"*\" for every address" -}}
{{- end -}}
{{- $ips -}}
{{- end -}}
