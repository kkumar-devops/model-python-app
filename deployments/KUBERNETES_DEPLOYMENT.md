# Deploying Prefect Deployments in Kubernetes Production

This document explains how to deploy Prefect deployment YAML files (`deployments/*.yaml`) in a production Kubernetes cluster.

**⚠️ Note**: This document is for **static deployment files**. In the actual production workflow, deployments are created **programmatically via the backend API** when users create connectors. See [`PRODUCTION_WORKFLOW.md`](./PRODUCTION_WORKFLOW.md) for the actual production workflow.

## Overview

The `prefect deploy` CLI command shown in the README works for local development, but in **production Kubernetes environments**, you need different approaches.

**However**, in this project, deployments are typically created **programmatically** from the Spring Boot backend when business users create connectors via the frontend. Static deployment files are only needed for:
- Initial seed deployments
- Testing
- Backup/documentation

## Methods for Production Deployment

### Method 1: Init Container (Recommended for Static Deployments)

Use a Kubernetes **Init Container** to register deployments when the Prefect Worker pod starts.

#### Step 1: Create Deployment Registration Script

Create `scripts/register-deployments.py`:

```python
#!/usr/bin/env python3
"""
Register Prefect deployments from YAML files.
Run as init container in Kubernetes.
"""
import os
import sys
import yaml
from pathlib import Path
from prefect import serve
from prefect.deployments import Deployment
from prefect.flows import load_flow_from_entrypoint

def register_deployment_from_yaml(yaml_path: str):
    """Register a deployment from a YAML file."""
    with open(yaml_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Load the flow
    flow = load_flow_from_entrypoint(config['entrypoint'])
    
    # Create deployment
    deployment = Deployment.build_from_flow(
        flow=flow,
        name=config['name'],
        work_pool_name=config.get('work_pool_name', 'default'),
        work_queue_name=config.get('work_queue_name', 'default'),
        parameters=config.get('parameters', {}),
        schedule=config.get('schedule'),
        tags=config.get('tags', []),
    )
    
    # Apply deployment
    deployment.apply()
    print(f"✅ Registered deployment: {config['name']}")

def main():
    """Register all deployments from deployments/ directory."""
    deployments_dir = Path('/prefect/deployments')
    
    if not deployments_dir.exists():
        print("⚠️  No deployments directory found, skipping registration")
        return
    
    yaml_files = list(deployments_dir.glob('*.yaml')) + list(deployments_dir.glob('*.yml'))
    
    if not yaml_files:
        print("⚠️  No deployment YAML files found")
        return
    
    print(f"📦 Found {len(yaml_files)} deployment file(s)")
    
    for yaml_file in yaml_files:
        try:
            print(f"📄 Processing: {yaml_file.name}")
            register_deployment_from_yaml(str(yaml_file))
        except Exception as e:
            print(f"❌ Failed to register {yaml_file.name}: {e}")
            # Continue with other deployments
            continue
    
    print("✅ Deployment registration complete")

if __name__ == '__main__':
    main()
```

#### Step 2: Update Dockerfile

Add the script to your Dockerfile:

```dockerfile
# Copy deployment registration script
COPY scripts/register-deployments.py /prefect/scripts/
COPY deployments/ /prefect/deployments/
RUN chmod +x /prefect/scripts/register-deployments.py
```

#### Step 3: Add Init Container to Helm Chart

Update `helm/clinical-ai-prefect/templates/worker-deployment.yaml`:

```yaml
spec:
  template:
    spec:
      # Add init container
      initContainers:
      - name: register-deployments
        image: "{{ .Values.worker.image.repository }}:{{ .Values.worker.image.tag }}"
        imagePullPolicy: {{ .Values.worker.image.pullPolicy }}
        command: ["python", "/prefect/scripts/register-deployments.py"]
        env:
        - name: PREFECT_API_URL
          valueFrom:
            configMapKeyRef:
              name: {{ include "clinical-ai-prefect.configMapName" . }}
              key: prefect-api-url
        volumeMounts:
        - name: deployments
          mountPath: /prefect/deployments
          readOnly: true
      containers:
      # ... existing container config ...
      volumes:
      - name: deployments
        configMap:
          name: {{ include "clinical-ai-prefect.fullname" . }}-deployments
```

#### Step 4: Create ConfigMap for Deployments

Create `helm/clinical-ai-prefect/templates/deployments-configmap.yaml`:

```yaml
{{- if .Values.deployments.enabled }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "clinical-ai-prefect.fullname" . }}-deployments
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "clinical-ai-prefect.labels" . | nindent 4 }}
data:
  {{- range $path, $content := .Files.Glob "deployments/*.yaml" }}
  {{ base $path }}: |
{{ $.Files.Get $path | indent 4 }}
  {{- end }}
{{- end }}
```

### Method 2: Kubernetes Job (Recommended for Dynamic Deployments)

Create a Kubernetes Job that runs once to register deployments.

#### Create Job Template

`helm/clinical-ai-prefect/templates/deployment-registration-job.yaml`:

```yaml
{{- if .Values.deployments.enabled }}
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "clinical-ai-prefect.fullname" . }}-register-deployments
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "clinical-ai-prefect.labels" . | nindent 4 }}
  annotations:
    "helm.sh/hook": post-install,post-upgrade
    "helm.sh/hook-weight": "1"
    "helm.sh/hook-delete-policy": before-hook-creation
spec:
  template:
    spec:
      restartPolicy: OnFailure
      serviceAccountName: {{ .Values.serviceAccount.name }}
      containers:
      - name: register-deployments
        image: "{{ .Values.worker.image.repository }}:{{ .Values.worker.image.tag }}"
        imagePullPolicy: {{ .Values.worker.image.pullPolicy }}
        command: ["python", "/prefect/scripts/register-deployments.py"]
        env:
        - name: PREFECT_API_URL
          valueFrom:
            configMapKeyRef:
              name: {{ include "clinical-ai-prefect.configMapName" . }}
              key: prefect-api-url
        volumeMounts:
        - name: deployments
          mountPath: /prefect/deployments
          readOnly: true
      volumes:
      - name: deployments
        configMap:
          name: {{ include "clinical-ai-prefect.fullname" . }}-deployments
{{- end }}
```

### Method 3: CI/CD Pipeline (Recommended for GitOps)

Register deployments as part of your CI/CD pipeline.

#### GitHub Actions Example

`.github/workflows/deploy-prefect-deployments.yml`:

```yaml
name: Deploy Prefect Deployments

on:
  push:
  branches: [main]
  paths:
    - 'clinical-ai-prefect/deployments/**'

jobs:
  register-deployments:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install Prefect
      run: |
        pip install prefect>=2.14.0
    
    - name: Configure Prefect
      run: |
        prefect config set PREFECT_API_URL=${{ secrets.PREFECT_API_URL }}
    
    - name: Register Deployments
      run: |
        cd clinical-ai-prefect
        for file in deployments/*.yaml; do
          if [ -f "$file" ]; then
            echo "Registering $file"
            prefect deploy "$file"
          fi
        done
```

### Method 4: Prefect API (Programmatic)

Use Prefect's REST API to create deployments programmatically.

#### Python Script

```python
import requests
import yaml
from pathlib import Path

PREFECT_API_URL = "http://prefect-server:4200/api"

def create_deployment_via_api(yaml_path: str):
    """Create deployment via Prefect API."""
    with open(yaml_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Build deployment payload
    payload = {
        "name": config['name'],
        "flow_name": config['flow_name'],
        "entrypoint": config['entrypoint'],
        "work_pool_name": config.get('work_pool_name', 'default'),
        "work_queue_name": config.get('work_queue_name', 'default'),
        "parameters": config.get('parameters', {}),
        "schedule": config.get('schedule'),
        "tags": config.get('tags', []),
    }
    
    # Create deployment
    response = requests.post(
        f"{PREFECT_API_URL}/deployments/",
        json=payload
    )
    response.raise_for_status()
    print(f"✅ Created deployment: {config['name']}")

# Run in Kubernetes Job or init container
for yaml_file in Path('/prefect/deployments').glob('*.yaml'):
    create_deployment_via_api(str(yaml_file))
```

## Recommended Approach for Your Use Case

Given your current architecture:

### Option A: Keep Dynamic (Current Approach) ✅ **Recommended**

**Don't use static deployment files** - continue with database-driven deployments:
- Flows triggered on-demand via API
- Connector configurations in database
- No scheduled deployments needed
- More flexible and easier to manage

### Option B: Hybrid Approach

If you need **some** scheduled deployments:

1. Use **Method 3 (CI/CD)** for static scheduled deployments
2. Keep dynamic triggering for on-demand flows
3. Store deployment YAML files in Git
4. Register via CI/CD pipeline on changes

### Option C: Full Static Deployments

If you want all deployments as static files:

1. Use **Method 1 (Init Container)** for automatic registration
2. Store all deployment YAML files in Git
3. Deploy via Helm chart
4. Deployments register automatically on pod startup

## Comparison

| Method | Use Case | Pros | Cons |
|--------|----------|------|------|
| **Init Container** | Static deployments, auto-register | Automatic, no manual steps | Runs on every pod restart |
| **Kubernetes Job** | One-time registration | Runs once, clean | Requires manual trigger or Helm hook |
| **CI/CD Pipeline** | GitOps, version control | Version controlled, automated | Requires CI/CD setup |
| **Prefect API** | Programmatic control | Full control, flexible | More complex, requires API access |
| **Current (Dynamic)** | On-demand execution | Most flexible, no files needed | No scheduled deployments |

## Example: Adding Scheduled Deployment Support

If you want to add scheduled deployments to your Helm chart:

### 1. Add to values.yaml

```yaml
deployments:
  enabled: true
  # Deployments will be loaded from deployments/ directory
```

### 2. Use Init Container Method

The init container approach ensures deployments are registered when the worker starts.

### 3. Update Deployment Files

Store deployment YAML files in the `deployments/` directory and they'll be automatically registered.

## Conclusion

**For your current setup**, the CLI method (`prefect deploy`) is **not suitable for production Kubernetes** because:

1. ❌ Requires manual execution
2. ❌ Needs Prefect CLI installed
3. ❌ Not automated or version-controlled
4. ❌ Doesn't integrate with Kubernetes lifecycle

**Recommended**: Continue with your current **database-driven, dynamic approach** unless you specifically need scheduled deployments. If you do need scheduled deployments, use **Method 1 (Init Container)** or **Method 3 (CI/CD)**.

