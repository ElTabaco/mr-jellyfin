{{/* Resource name prefix. */}}
{{- define "jf.fullname" -}}
{{- default .Release.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels. "app" is used by the cluster Prometheus relabelling. */}}
{{- define "jf.labels" -}}
app: {{ include "jf.fullname" . }}
app.kubernetes.io/name: jellyfin
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/part-of: mr-do-jellyfin
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "jf.selectorLabels" -}}
app: {{ include "jf.fullname" . }}
app.kubernetes.io/name: jellyfin
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* image reference repo:tag@digest; digest and tag are mandatory. */}}
{{- define "jf.image" -}}
{{- $tag := required "image tag is required (never 'latest')" .tag -}}
{{- if eq $tag "latest" }}{{ fail "image tag 'latest' is not allowed" }}{{ end -}}
{{- $digest := required "image digest is required" .digest -}}
{{- printf "%s:%s@%s" .repository $tag $digest -}}
{{- end -}}

{{/* Annotations that keep storage objects when Argo CD prunes or Helm uninstalls. */}}
{{- define "jf.keepAnnotations" -}}
helm.sh/resource-policy: keep
argocd.argoproj.io/sync-options: Prune=false,Delete=false
{{- end -}}

{{- define "jf.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: {{ .Values.securityContext.runAsUser }}
runAsGroup: {{ .Values.securityContext.runAsGroup }}
fsGroup: {{ .Values.securityContext.fsGroup }}
fsGroupChangePolicy: OnRootMismatch
{{- $groups := .Values.securityContext.supplementalGroups | default list -}}
{{- if .Values.gpu.enabled }}{{ $groups = append $groups .Values.gpu.renderGroupId }}{{ end }}
{{- with $groups }}
supplementalGroups:
{{- toYaml . | nindent 2 }}
{{- end }}
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "jf.containerSecurityContext" -}}
allowPrivilegeEscalation: false
privileged: false
capabilities:
  drop: ["ALL"]
{{- end -}}

{{/* Required storage values; message prefix PENDING marks values still to be supplied. */}}
{{- define "jf.mediaServer" -}}
{{- required "PENDING(phase2): persistence.media.server (NAS NFS host name) is not set" .Values.persistence.media.server -}}
{{- end -}}
{{- define "jf.mediaPath" -}}
{{- required "PENDING(phase2): persistence.media.path (NAS NFS export) is not set" .Values.persistence.media.path -}}
{{- end -}}
{{- define "jf.configNode" -}}
{{- required "persistence.config.node is required" .Values.persistence.config.node -}}
{{- end -}}
{{- define "jf.cacheNode" -}}
{{- required "persistence.cache.node is required" .Values.persistence.cache.node -}}
{{- end -}}
