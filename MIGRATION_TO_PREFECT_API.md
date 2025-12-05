# Migration from Flow Server to Prefect API

## ✅ Completed Changes

### 1. PrefectService.java - Updated `triggerManualRun()`

**Changed from**: Flow Server HTTP call (port 5000)
**Changed to**: Prefect API deployment flow run creation

**Key Changes**:
- Removed Flow Server URL and WebClient
- Now requires `deploymentId` parameter
- Uses Prefect API: `POST /api/deployments/{deployment_id}/create_flow_run`
- Returns flow run ID (instead of generic "triggered" message)
- Full Prefect orchestration and tracking

### 2. ConnectorService.java - Updated `triggerManualRun()`

**Changed**: Now retrieves deployment ID from connector before calling PrefectService
**Added**: Validation to ensure connector has a deployment

## 📋 Additional Items to Consider

### Optional: Remove Flow Server Infrastructure

The Flow Server is no longer needed, but you can keep it for now or remove it later.

#### Files/Configs That Reference Flow Server:

1. **Prefect Service (Kubernetes)**
   - `k8s/service.yaml` - Port 5000 for flow-server
   - `k8s/deployment.yaml` - Flow server container port and health checks
   - `helm/clinical-ai-prefect/templates/worker-service.yaml` - Flow server port
   - `helm/clinical-ai-prefect/templates/worker-deployment.yaml` - Flow server env vars

2. **Docker Configuration**
   - `Dockerfile` - Starts flow_server.py in background
   - `docker-compose.yml` - FLOW_SERVER_URL environment variable

3. **Configuration Files**
   - `k8s/configmap.yaml` - flow-server-port
   - `helm/clinical-ai-prefect/values.yaml` - flowServerPort config

4. **Documentation**
   - `README.md` - References to Flow Server
   - `DEPLOYMENT.md` - Flow Server testing instructions
   - `ARCHITECTURE_RUNTIME.md` - Flow Server documentation

5. **Code**
   - `flow_server.py` - The Flow Server implementation itself

### Recommended: Keep Flow Server for Now

**Why keep it**:
- ✅ Backward compatibility during transition
- ✅ Fallback option if Prefect API is unavailable
- ✅ No breaking changes to infrastructure
- ✅ Can be removed later if not needed

**Why remove it**:
- ✅ Cleaner architecture
- ✅ One less service to maintain
- ✅ Reduces complexity
- ✅ All flows go through Prefect (consistent)

## 🔄 Migration Steps (If Removing Flow Server)

### Step 1: Update Dockerfile

```dockerfile
# OLD:
CMD ["/bin/sh", "-c", "nohup python flow_server.py > /tmp/flow_server.log 2>&1 & sleep 2 && exec prefect worker start --pool default --type process"]

# NEW:
CMD ["prefect", "worker", "start", "--pool", "default", "--type", "process"]
```

### Step 2: Update Kubernetes Service

Remove flow-server port from `k8s/service.yaml`:

```yaml
# Remove this:
- name: flow-server
  port: 5000
  targetPort: 5000
```

### Step 3: Update Kubernetes Deployment

Remove flow-server references from `k8s/deployment.yaml`:
- Remove container port 5000
- Remove FLOW_SERVER_PORT environment variable
- Update health checks to use Prefect API instead

### Step 4: Update Helm Chart

Remove flow-server from:
- `helm/clinical-ai-prefect/templates/worker-service.yaml`
- `helm/clinical-ai-prefect/templates/worker-deployment.yaml`
- `helm/clinical-ai-prefect/values.yaml` (flowServerPort)

### Step 5: Update Docker Compose

Remove from `docker-compose.yml`:
- `FLOW_SERVER_URL` environment variable
- Port mapping `5000:5000`

### Step 6: Update Documentation

Update references in:
- `README.md` - Remove Flow Server sections
- `DEPLOYMENT.md` - Remove Flow Server testing
- `ARCHITECTURE_RUNTIME.md` - Update architecture diagram

## ✅ Current Status

**Code Changes**: ✅ Complete
- PrefectService uses Prefect API
- ConnectorService validates deployment exists

**Infrastructure**: ⚠️ Optional
- Flow Server still exists but is not used
- Can be removed when ready

**Documentation**: ⚠️ Needs Update
- Some docs still reference Flow Server
- Can be updated gradually

## 🎯 Summary

**What Changed**:
- ✅ `PrefectService.triggerManualRun()` now uses Prefect API
- ✅ Requires deployment ID (retrieved from connector)
- ✅ Returns flow run ID for tracking

**What's Optional**:
- ⚠️ Remove Flow Server infrastructure (can be done later)
- ⚠️ Update documentation (can be done gradually)

**What's Required**:
- ✅ Ensure connectors have deployments before manual trigger
- ✅ Prefect Server must be available for manual triggers

## Next Steps

1. **Test the new implementation**:
   - Create a connector with a deployment
   - Trigger manual run
   - Verify flow run appears in Prefect UI
   - Verify flow run ID is returned

2. **Monitor for issues**:
   - Check logs for any errors
   - Verify flow runs complete successfully
   - Ensure deployment IDs are present

3. **Optional cleanup** (when ready):
   - Remove Flow Server infrastructure
   - Update documentation
   - Remove `flow_server.py` if not needed

