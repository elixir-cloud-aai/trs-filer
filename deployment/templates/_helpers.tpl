{{- /* "true" if the chart creates the OpenShift Route (`route.enabled`,
the Ingress disabled and the cluster serving Routes), else empty; used by
the Route and NOTES.txt. `dig`, so that upgrades with `--reuse-values` from
charts without `trs_filer.route` keep the Route */}}
{{- define "trs-filer.route" -}}
{{- if and (dig "route" "enabled" true .Values.trs_filer) (not .Values.trs_filer.ingress.enabled) (.Capabilities.APIVersions.Has "route.openshift.io/v1") -}}
true
{{- end -}}
{{- end -}}
