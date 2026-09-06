{{- define "notes.name" -}}
{{ .Release.Name }}
{{- end -}}

{{- define "notes.labels" -}}
app.kubernetes.io/name: notes
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: Helm
{{- end -}}

{{/* Scheme of the public URL. */}}
{{- define "notes.scheme" -}}
{{ if .Values.tls.enabled }}https{{ else }}http{{ end }}
{{- end -}}

{{/* The public base URL, as the browser sees it. */}}
{{- define "notes.publicUrl" -}}
{{ include "notes.scheme" . }}://{{ .Values.host }}
{{- end -}}

{{/* The token issuer. Must match exactly on both the browser and the API. */}}
{{- define "notes.issuer" -}}
{{ include "notes.publicUrl" . }}/auth/realms/{{ .Values.realm }}
{{- end -}}

{{/* Postgres host: the in-cluster service, or the managed endpoint. */}}
{{- define "notes.dbHost" -}}
{{- if .Values.postgres.enabled -}}
{{ .Release.Name }}-postgres
{{- else -}}
{{- required "postgres.host is required when postgres.enabled is false" .Values.postgres.host -}}
{{- end -}}
{{- end -}}

{{- define "notes.secretName" -}}
{{ .Values.secret.name | default (printf "%s-secrets" .Release.Name) }}
{{- end -}}
