{{- define "recordlane.name" -}}recordlane{{- end -}}
{{- define "recordlane.labels" -}}
app.kubernetes.io/name: recordlane
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}

