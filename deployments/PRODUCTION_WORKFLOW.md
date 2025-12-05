# Production Deployment Workflow

This document describes the **actual production workflow** for Prefect deployments in the Clinical AI platform.

## Workflow Overview

```
┌─────────────┐
│   Frontend  │
│  (Business  │
│    Users)   │
└──────┬──────┘
       │ 1. Create/Update Connector
       │    (with schedule: "0 */4 * * *")
       ▼
┌─────────────────────┐
│  Spring Boot        │
│  Backend API        │
│  ConnectorService   │
└──────┬──────────────┘
       │ 2. Save to Database
       │    + Call PrefectService.createDeployment()
       ▼
┌─────────────────────┐
│  PrefectService     │
│  (Java)             │
└──────┬──────────────┘
       │ 3. Create Deployment via Prefect API
       │    POST /api/deployments/
       ▼
┌─────────────────────┐
│  Prefect Server     │
│  (Kubernetes)       │
└──────┬──────────────┘
       │ 4. Register Deployment
       │    (with schedule)
       ▼
┌─────────────────────┐
│  Prefect Scheduler  │
│  (runs on schedule) │
└─────────────────────┘
```

## Implementation Details

### 1. Initial Deployment (Helm Chart)

**Purpose**: Deploy Prefect Server and Worker infrastructure

```bash
# Deploy infrastructure
helm install clinical-ai-prefect ./helm/clinical-ai-prefect \
  -f ./helm/clinical-ai-prefect/values-production.yaml \
  --namespace clinical-ai
```

This creates:
- Prefect Server (orchestration)
- Prefect Worker (execution)
- Services, ConfigMaps, Secrets

**No flow deployments are created at this stage** - only infrastructure.

### 2. User Creates Connector (Frontend → Backend)

When a business user creates a connector via the frontend:

1. **Frontend** sends request to backend:
   ```json
   POST /api/v1/connectors
   {
     "name": "Customer Data Pipeline",
     "schedule": "0 */4 * * *",  // Every 4 hours
     "isActive": true,
     ...
   }
   ```

2. **Backend** (`ConnectorService.create()`):
   - Saves connector to database
   - Calls `prefectService.createDeployment()`
   - Stores `prefect_deployment_id` in database

3. **PrefectService** creates deployment via Prefect API

### 3. PrefectService Implementation

The `PrefectService.createDeployment()` method should:

**Implementation**: See `clinical-ai-server/src/main/java/com/nphase/redcapcloud/service/PrefectService.java`

The method:
- Builds deployment payload with schedule, parameters, and tags
- Calls Prefect API: `POST /api/deployments/`
- Returns deployment ID for storage in database
- Handles errors gracefully

#### updateDeploymentSchedule()
Updates an existing deployment's schedule when connector schedule changes.

**Implementation**: See `PrefectService.updateDeploymentSchedule()`

#### deleteDeployment()
Deletes a deployment when connector is deleted or deactivated.

**Implementation**: See `PrefectService.deleteDeployment()`

### 4. Prefect API Endpoint

The Prefect Server exposes a REST API at:
- **Kubernetes**: `http://clinical-ai-prefect-server.clinical-ai.svc.cluster.local:4200/api`
- **External**: Via Ingress or port-forward

**Deployment Creation Endpoint**:
```
POST /api/deployments/
Content-Type: application/json

{
  "name": "connector-1-pipeline",
  "flow_name": "run_connector_pipeline",
  "entrypoint": "flows/dlt_pipeline_flow.py:run_connector_pipeline",
  "work_pool_name": "default",
  "work_queue_name": "default",
  "parameters": {
    "connector_id": 1
  },
  "schedule": {
    "cron": "0 */4 * * *",
    "timezone": "UTC"
  },
  "tags": ["connector-1", "scheduled"]
}
```

**Response**:
```json
{
  "id": "deployment-uuid-here",
  "name": "connector-1-pipeline",
  "flow_name": "run_connector_pipeline",
  ...
}
```

## Complete Implementation Guide

### Step 1: Update PrefectService.java

Replace the placeholder `createDeployment()` method with actual Prefect API calls.

### Step 2: Handle Deployment Updates ✅ **Implemented**

The `ConnectorService.update()` method now:
- Detects schedule changes
- Calls `PrefectService.updateDeploymentSchedule()` to update via Prefect API
- Handles deployment recreation if update fails

### Step 3: Handle Deployment Deletion ✅ **Implemented**

The `ConnectorService.delete()` method now:
- Checks for existing deployment ID
- Calls `PrefectService.deleteDeployment()` to delete via Prefect API
- Continues with connector deletion even if deployment deletion fails

## Deployment Lifecycle

### Create Connector
1. User creates connector in frontend with schedule
2. Backend saves to database
3. Backend calls Prefect API to create deployment
4. Deployment ID stored in `cai_connectors.prefect_deployment_id`
5. Prefect Server schedules flow runs

### Update Connector Schedule
1. User updates connector schedule in frontend
2. Backend updates database
3. Backend calls Prefect API to update deployment schedule
4. Prefect Server updates schedule

### Deactivate Connector
1. User deactivates connector in frontend
2. Backend updates `is_active = false`
3. Backend calls Prefect API to pause/delete deployment
4. Prefect Server stops scheduling

### Delete Connector
1. User deletes connector in frontend
2. Backend deletes from database
3. Backend calls Prefect API to delete deployment
4. Prefect Server removes deployment

## Error Handling

### Deployment Creation Fails
- Log error
- Save connector without `prefect_deployment_id`
- Allow manual retry or admin intervention
- Don't block connector creation

### Prefect Server Unavailable
- Retry with exponential backoff
- Queue deployment creation for later
- Alert operations team

### Invalid Schedule
- Validate cron expression before API call
- Return user-friendly error message
- Don't create deployment

## Testing

### Local Development
```bash
# Start Prefect Server locally
prefect server start

# Test deployment creation
curl -X POST http://localhost:4200/api/deployments/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test-deployment",
    "flow_name": "run_connector_pipeline",
    "entrypoint": "flows/dlt_pipeline_flow.py:run_connector_pipeline",
    "parameters": {"connector_id": 1},
    "schedule": {"cron": "0 */4 * * *", "timezone": "UTC"}
  }'
```

### Production Testing
```bash
# Port-forward to Prefect Server
kubectl port-forward -n clinical-ai svc/clinical-ai-prefect-server 4200:4200

# Test via backend API
curl -X POST http://localhost:8080/api/v1/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Connector",
    "schedule": "0 */4 * * *",
    "isActive": true,
    ...
  }'
```

## Monitoring

### Check Deployments
```bash
# Via Prefect UI
# Navigate to http://prefect-server:4200/deployments

# Via API
curl http://prefect-server:4200/api/deployments/
```

### Check Scheduled Runs
```bash
# Via Prefect UI
# Navigate to http://prefect-server:4200/flow-runs

# Via API
curl http://prefect-server:4200/api/flow_runs/
```

## Summary

**Initial Setup**: Helm chart deploys infrastructure only

**Runtime**: Backend creates/updates/deletes deployments programmatically via Prefect API when:
- Users create connectors (with schedules)
- Users update connector schedules
- Users deactivate/delete connectors

**No static deployment files needed** - everything is dynamic and database-driven.

