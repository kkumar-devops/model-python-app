# Accessing Prefect UI for Deployment Verification

Yes, the current package **fully supports** accessing Prefect UI to verify deployments. Prefect Server serves both the API and UI on the same port (4200).

## Quick Access Methods

### 1. Port-Forward (Development/Testing)

The simplest method for local access:

```bash
# Port-forward to Prefect Server
kubectl port-forward -n clinical-ai svc/clinical-ai-prefect-server 4200:4200

# Then open in your browser:
# http://localhost:4200
```

**What you can verify:**
- ✅ View all deployments
- ✅ See deployment schedules
- ✅ Monitor flow runs
- ✅ View execution logs
- ✅ Check deployment status
- ✅ See run history

### 2. Ingress (Production)

For production access, enable Ingress in the Helm chart:

#### Update values.yaml

```yaml
server:
  ingress:
    enabled: true
    className: "nginx"  # or your ingress controller
    annotations:
      kubernetes.io/ingress.class: nginx
      cert-manager.io/cluster-issuer: letsencrypt-prod  # for TLS
    hosts:
      - host: prefect.yourdomain.com
        path: /
        pathType: Prefix
    tls:
      - secretName: prefect-tls
        hosts:
          - prefect.yourdomain.com
```

#### Install/Upgrade

```bash
helm upgrade --install clinical-ai-prefect ./helm/clinical-ai-prefect \
  -f ./helm/clinical-ai-prefect/values-production.yaml \
  --namespace clinical-ai
```

Then access at: `https://prefect.yourdomain.com`

### 3. NodePort (Alternative)

If you need direct access without Ingress:

```yaml
server:
  service:
    type: NodePort
    port: 4200
    targetPort: 4200
```

Access via: `http://<node-ip>:<nodeport>`

## What to Verify in Prefect UI

### 1. Deployments Tab

Navigate to **Deployments** to see:
- All connector deployments created by the backend
- Deployment names (e.g., `connector-1`, `connector-2`)
- Schedules (cron expressions)
- Status (Active/Inactive)
- Last run time
- Next scheduled run

**URL**: `http://localhost:4200/deployments`

### 2. Flow Runs Tab

Navigate to **Flow Runs** to see:
- All executed flow runs
- Run status (Running, Completed, Failed)
- Execution time
- Logs
- Parameters used

**URL**: `http://localhost:4200/flow-runs`

### 3. Work Pools Tab

Navigate to **Work Pools** to see:
- Available work pools
- Worker status
- Queue status
- Concurrency limits

**URL**: `http://localhost:4200/work-pools`

### 4. Individual Deployment Details

Click on any deployment to see:
- Full deployment configuration
- Schedule details
- Recent runs
- Run history
- Tags

## Verification Checklist

After creating a connector via the backend API, verify in Prefect UI:

- [ ] Deployment appears in Deployments list
- [ ] Deployment name matches `connector-{id}`
- [ ] Schedule matches the connector's schedule
- [ ] Deployment is active (if connector is active)
- [ ] Tags include `connector-{id}` and `scheduled`
- [ ] Parameters include `connector_id`
- [ ] Flow name is `run_connector_pipeline`

## Example Verification Workflow

### Step 1: Create Connector

```bash
curl -X POST http://localhost:8080/api/v1/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Connector",
    "schedule": "0 */4 * * *",
    "isActive": true,
    ...
  }'
```

Response includes `prefectDeploymentId`.

### Step 2: Access Prefect UI

```bash
kubectl port-forward -n clinical-ai svc/clinical-ai-prefect-server 4200:4200
```

Open `http://localhost:4200` in browser.

### Step 3: Verify Deployment

1. Go to **Deployments** tab
2. Find deployment named `connector-{id}`
3. Verify:
   - Schedule: `0 */4 * * *`
   - Status: Active
   - Flow: `run_connector_pipeline`
   - Tags: `connector-{id}`, `scheduled`

### Step 4: Verify Schedule Execution

1. Wait for scheduled time (or trigger manually)
2. Go to **Flow Runs** tab
3. Verify run appears with:
   - Status: Completed/Running
   - Deployment: `connector-{id}`
   - Parameters: `{"connector_id": {id}}`

## API Alternative

You can also verify deployments via the Prefect API:

```bash
# Port-forward first
kubectl port-forward -n clinical-ai svc/clinical-ai-prefect-server 4200:4200

# List all deployments
curl http://localhost:4200/api/deployments/

# Get specific deployment
curl http://localhost:4200/api/deployments/{deployment-id}

# List flow runs
curl http://localhost:4200/api/flow_runs/
```

## Troubleshooting

### UI Not Loading

1. **Check port-forward is active:**
   ```bash
   kubectl get pods -n clinical-ai -l app=clinical-ai-prefect-server
   ```

2. **Verify service is running:**
   ```bash
   kubectl get svc -n clinical-ai clinical-ai-prefect-server
   ```

3. **Check Prefect Server logs:**
   ```bash
   kubectl logs -n clinical-ai -l app=clinical-ai-prefect-server
   ```

### Deployments Not Visible

1. **Verify deployment was created:**
   ```bash
   # Check backend logs
   kubectl logs -n clinical-ai -l app=clinical-ai-server | grep "Prefect deployment"
   ```

2. **Check Prefect API:**
   ```bash
   curl http://localhost:4200/api/deployments/ | jq
   ```

3. **Verify connector has deployment ID:**
   ```sql
   SELECT id, name, prefect_deployment_id, is_active 
   FROM cai_connectors;
   ```

## Security Considerations

### Production Access

For production, use:
- **Ingress with TLS** (recommended)
- **VPN/Private Network** access
- **Authentication** (if Prefect Cloud features enabled)
- **Network Policies** to restrict access

### Development Access

For development:
- Port-forward is acceptable
- Consider using a bastion host
- Use temporary access tokens if needed

## Summary

✅ **Yes, Prefect UI is fully accessible** for deployment verification

**Access Methods:**
1. Port-forward (development) - `kubectl port-forward ... 4200:4200`
2. Ingress (production) - Configure in Helm values
3. NodePort (alternative) - Change service type

**What you can verify:**
- All deployments created by backend
- Deployment schedules and status
- Flow run history and logs
- Work pool and worker status

The Prefect Server serves both API and UI on port 4200, so all deployment management features are available through the web interface.

