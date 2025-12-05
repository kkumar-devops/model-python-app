{{/*
Expand the name of the chart.
*/}}
{{- define "clinical-ai-prefect.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "clinical-ai-prefect.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "clinical-ai-prefect.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "clinical-ai-prefect.labels" -}}
helm.sh/chart: {{ include "clinical-ai-prefect.chart" . }}
{{ include "clinical-ai-prefect.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.labels }}
{{- toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "clinical-ai-prefect.selectorLabels" -}}
app.kubernetes.io/name: {{ include "clinical-ai-prefect.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
component: workflow-orchestration
{{- end }}

{{/*
Server selector labels
*/}}
{{- define "clinical-ai-prefect.server.selectorLabels" -}}
app.kubernetes.io/name: {{ include "clinical-ai-prefect.name" . }}-server
app.kubernetes.io/instance: {{ .Release.Name }}
component: workflow-orchestration
{{- end }}

{{/*
Worker selector labels
*/}}
{{- define "clinical-ai-prefect.worker.selectorLabels" -}}
app.kubernetes.io/name: {{ include "clinical-ai-prefect.name" . }}-worker
app.kubernetes.io/instance: {{ .Release.Name }}
component: workflow-orchestration
{{- end }}

{{/*
Generate Prefect API URL
*/}}
{{- define "clinical-ai-prefect.apiUrl" -}}
{{- if .Values.config.prefectApiUrl }}
{{- .Values.config.prefectApiUrl }}
{{- else }}
{{- printf "http://%s-server.%s.svc.cluster.local:%v/api" .Release.Name .Release.Namespace (.Values.server.service.port | int) }}
{{- end }}
{{- end }}

{{/*
Generate ConfigMap name
*/}}
{{- define "clinical-ai-prefect.configMapName" -}}
{{- printf "%s-config" (include "clinical-ai-prefect.fullname" .) }}
{{- end }}

{{/*
Resolve namespace from release or global default
*/}}
{{- define "clinical-ai-prefect.namespace" -}}
{{- if .Release.Namespace -}}
{{ .Release.Namespace }}
{{- else if .Values.global.namespace -}}
{{ .Values.global.namespace }}
{{- else -}}
default
{{- end -}}
{{- end }}

