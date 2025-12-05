# Flow Server Removal Guide

## Current Status: Flow Server Still Created (But Not Used)

**Yes, the Flow Server is still being created** in the current Kubernetes deployment configuration, even though the backend code no longer uses it.

## Where Flow Server is Still Configured

### 1. Dockerfile (Line 38)
```dockerfile
CMD ["/bin/sh", "-c", "nohup python flow_server.py > /tmp/flow_server.log 2>&1 & sleep 2 && exec prefect worker start --pool default --type process"]
```
**Status**: Starts Flow Server in background, then starts Prefect Worker

### 2. Kubernetes Deployment (`k8s/deployment.yaml`)
- **Line 26-28**: Container port 5000 exposed for flow-server
- **Line 85-86**: `FLOW_SERVER_PORT` environment variable set
- **Lines 94-109**: Health checks configured for port 5000

### 3. Kubernetes Service (`k8s/service.yaml`)
- **Lines 12-14**: Service exposes port 5000 for flow-server

### 4. Helm Chart Templates
- **worker-deployment.yaml**: Port 5000 and FLOW_SERVER_PORT configured
- **worker-service.yaml**: Port 5000 exposed
- **configmap.yaml**: flow-server-port configuration

## Impact

### Current Behavior
- ✅ Flow Server starts but is **not used** by backend
- ⚠️ Health checks may fail if Flow Server doesn't start
- ⚠️ Port 5000 is exposed but unused
- ⚠️ Unnecessary resource consumption

### Why This Happens
The Dockerfile CMD starts both services, but the backend now uses Prefect API instead of Flow Server.

## Recommended: Remove Flow Server

Since the backend now uses Prefect API, the Flow Server is no longer needed.

### Option 1: Quick Fix - Update Dockerfile Only

**Simplest approach**: Just update the Dockerfile to remove Flow Server startup.

```dockerfile
# OLD:
CMD ["/bin/sh", "-c", "nohup python flow_server.py > /tmp/flow_server.log 2>&1 & sleep 2 && exec prefect worker start --pool default --type process"]

# NEW:
CMD ["prefect", "worker", "start", "--pool", "default", "--type", "process"]
```

**Also update health check**:
```dockerfile
# OLD:
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# NEW: Remove health check (Prefect worker doesn't expose HTTP)
# Or use Prefect API health check instead
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f ${PREFECT_API_URL%/api}/health || exit 1
```

**Result**: Flow Server won't start, but Kubernetes configs still reference it (harmless but not clean).

### Option 2: Complete Removal (Recommended)

Remove Flow Server from all configurations.

#### Step 1: Update Dockerfile

```dockerfile
FROM prefecthq/prefect:2.14-python3.11

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install dlt and dependencies
COPY requirements.txt* ./
RUN if [ -f requirements.txt ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        pip install --no-cache-dir \
            dlt[filesystem]>=0.4.0 \
            dlt[postgres]>=0.4.0 \
            sqlalchemy>=2.0.0 \
            psycopg2-binary>=2.9.0 \
            s3fs>=2023.10.0; \
    fi

WORKDIR /prefect

# Copy flows directory (flow_server.py no longer needed)
COPY flows/ /prefect/flows/

# Health check using Prefect API (if accessible) or remove
# HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
#     CMD curl -f ${PREFECT_API_URL%/api}/health || exit 1

# Start Prefect worker only
CMD ["prefect", "worker", "start", "--pool", "default", "--type", "process"]
```

#### Step 2: Update Kubernetes Deployment

**File**: `k8s/deployment.yaml`

Remove:
- Container port 5000 (lines 26-28)
- `FLOW_SERVER_PORT` environment variable (lines 85-86)
- Health checks for port 5000 (lines 94-109)

**Updated**:
```yaml
containers:
- name: prefect-worker
  image: clinical-ai-prefect:latest
  imagePullPolicy: IfNotPresent
  # Remove port 5000
  env:
  - name: PREFECT_API_URL
    valueFrom:
      configMapKeyRef:
        name: clinical-ai-prefect-config
        key: prefect-api-url
  # ... other env vars ...
  # Remove FLOW_SERVER_PORT
  resources:
    requests:
      memory: "512Mi"
      cpu: "250m"
    limits:
      memory: "2Gi"
      cpu: "1000m"
  # Remove livenessProbe and readinessProbe for port 5000
  # Or use Prefect API health check if needed
```

#### Step 3: Update Kubernetes Service

**File**: `k8s/service.yaml`

Remove flow-server port:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: clinical-ai-prefect-worker
  namespace: clinical-ai
spec:
  type: ClusterIP
  # Remove flow-server port
  selector:
    app: clinical-ai-prefect-worker
```

#### Step 4: Update Helm Chart

**File**: `helm/clinical-ai-prefect/templates/worker-deployment.yaml`

Remove:
- Port 5000 (line 40-42)
- `FLOW_SERVER_PORT` env var (line 98-99)
- Health checks for port 5000 (or update to use Prefect API)

**File**: `helm/clinical-ai-prefect/templates/worker-service.yaml`

Remove flow-server port.

**File**: `helm/clinical-ai-prefect/values.yaml`

Remove or comment out:
```yaml
config:
  # flowServerPort: "5000"  # No longer needed
```

#### Step 5: Update ConfigMap

**File**: `k8s/configmap.yaml`

Remove:
```yaml
# flow-server-port: "5000"  # No longer needed
```

## Summary

### Current State
- ✅ Backend code: Uses Prefect API (updated)
- ⚠️ Dockerfile: Still starts Flow Server
- ⚠️ Kubernetes: Still exposes port 5000
- ⚠️ Health checks: Still check port 5000

### After Removal
- ✅ Backend code: Uses Prefect API
- ✅ Dockerfile: Only starts Prefect Worker
- ✅ Kubernetes: No Flow Server port
- ✅ Health checks: Removed or use Prefect API

## Recommendation

**Option 1 (Quick)**: Update Dockerfile only - Flow Server won't start, but configs still reference it (works but not clean).

**Option 2 (Complete)**: Remove from all configs - Clean architecture, no unused resources.

I recommend **Option 2** for production deployments.

