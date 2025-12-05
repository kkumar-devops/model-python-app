# Manual Flow Trigger Options

## Yes, Prefect API Can Handle Manual Triggers! ✅

The Prefect API provides endpoints to manually trigger flow runs from deployments. This means you **don't need the Flow Server** if you use Prefect API.

## Current Implementation

### Current Approach: Flow Server

The backend currently uses a **Flow Server** (simple HTTP server on port 5000):

```java
// PrefectService.triggerManualRun()
String flowServerUrl = "http://prefect-worker:5000";
flowServerClient.post()
    .uri("/trigger")
    .bodyValue(Map.of("connector_id", connectorId))
    ...
```

**Pros**:
- Simple, direct execution
- No deployment required
- Works even if Prefect Server is down

**Cons**:
- Single-threaded (Python `http.server`)
- Not production-grade
- Bypasses Prefect orchestration
- No visibility in Prefect UI

## Better Approach: Prefect API

### Option 1: Create Flow Run from Deployment (Recommended)

Since connectors have deployments created automatically, you can trigger them via Prefect API:

```java
// PrefectService.triggerManualRun() - Updated version
public String triggerManualRun(Long connectorId) {
    logger.info("Triggering manual run for connector {}", connectorId);
    
    try {
        // Get deployment ID from connector
        CAIConnector connector = connectorRepository.findById(connectorId)
            .orElseThrow(() -> new RuntimeException("Connector not found"));
        
        String deploymentId = connector.getPrefectDeploymentId();
        if (deploymentId == null || deploymentId.isEmpty()) {
            throw new RuntimeException("Connector does not have a Prefect deployment");
        }
        
        // Create flow run via Prefect API
        Map<String, Object> requestBody = Map.of(
            "parameters", Map.of("connector_id", connectorId),
            "tags", List.of("manual-trigger", "connector-" + connectorId)
        );
        
        Map response = webClient.post()
                .uri("/deployments/" + deploymentId + "/create_flow_run")
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(Map.class)
                .block();
        
        String flowRunId = (String) response.get("id");
        logger.info("Created flow run {} for connector {}", flowRunId, connectorId);
        return flowRunId;
        
    } catch (Exception e) {
        logger.error("Failed to trigger manual run: {}", e.getMessage(), e);
        throw new RuntimeException("Failed to trigger flow run: " + e.getMessage(), e);
    }
}
```

**Pros**:
- ✅ Production-grade (Uvicorn ASGI server)
- ✅ Full Prefect orchestration
- ✅ Visible in Prefect UI
- ✅ Proper flow run tracking
- ✅ Better observability
- ✅ No need for Flow Server

**Cons**:
- Requires deployment to exist
- Requires Prefect Server to be available

### Option 2: Create Flow Run from Flow Name

If you want to trigger without a deployment:

```java
// Alternative: Create flow run directly from flow name
Map<String, Object> requestBody = Map.of(
    "name", "run_connector_pipeline",
    "parameters", Map.of("connector_id", connectorId),
    "tags", List.of("manual-trigger")
);

Map response = webClient.post()
        .uri("/flows/run")
        .bodyValue(requestBody)
        .retrieve()
        .bodyToMono(Map.class)
        .block();
```

## Prefect API Endpoints for Manual Triggers

### 1. Create Flow Run from Deployment (Recommended)

```bash
POST /api/deployments/{deployment_id}/create_flow_run
Content-Type: application/json

{
  "parameters": {
    "connector_id": 1
  },
  "tags": ["manual-trigger"],
  "name": "manual-run-connector-1"
}
```

**Response**:
```json
{
  "id": "flow-run-uuid",
  "state": {
    "type": "PENDING"
  },
  "deployment_id": "deployment-uuid",
  ...
}
```

### 2. Create Flow Run from Flow

```bash
POST /api/flows/{flow_id}/run
Content-Type: application/json

{
  "parameters": {
    "connector_id": 1
  }
}
```

### 3. Create Flow Run by Flow Name

```bash
POST /api/flows/run
Content-Type: application/json

{
  "name": "run_connector_pipeline",
  "parameters": {
    "connector_id": 1
  }
}
```

## Migration Path

### Step 1: Update PrefectService.triggerManualRun()

Replace Flow Server call with Prefect API call:

```java
public String triggerManualRun(Long connectorId) {
    // Get connector and deployment ID
    CAIConnector connector = connectorRepository.findById(connectorId)
        .orElseThrow(() -> new RuntimeException("Connector not found"));
    
    String deploymentId = connector.getPrefectDeploymentId();
    if (deploymentId == null || deploymentId.isEmpty()) {
        throw new RuntimeException("Connector does not have a Prefect deployment. " +
            "Please ensure the connector is active and has a deployment.");
    }
    
    // Create flow run via Prefect API
    Map<String, Object> requestBody = new HashMap<>();
    Map<String, Object> parameters = new HashMap<>();
    parameters.put("connector_id", connectorId);
    requestBody.put("parameters", parameters);
    
    List<String> tags = new ArrayList<>();
    tags.add("manual-trigger");
    tags.add("connector-" + connectorId);
    requestBody.put("tags", tags);
    
    Map response = webClient.post()
            .uri("/deployments/" + deploymentId + "/create_flow_run")
            .bodyValue(requestBody)
            .retrieve()
            .bodyToMono(Map.class)
            .doOnSuccess(r -> logger.info("Flow run created: {}", r))
            .doOnError(e -> logger.error("Failed to create flow run: {}", e.getMessage()))
            .block();
    
    if (response == null || !response.containsKey("id")) {
        throw new RuntimeException("Invalid response from Prefect API");
    }
    
    String flowRunId = (String) response.get("id");
    logger.info("Successfully created flow run {} for connector {}", flowRunId, connectorId);
    return flowRunId;
}
```

### Step 2: Remove Flow Server (Optional)

If you migrate to Prefect API only:

1. **Remove `flow_server.py`** from the repository
2. **Update Dockerfile** to remove Flow Server startup:
   ```dockerfile
   # OLD:
   CMD ["/bin/sh", "-c", "nohup python flow_server.py > /tmp/flow_server.log 2>&1 & sleep 2 && exec prefect worker start --pool default --type process"]
   
   # NEW:
   CMD ["prefect", "worker", "start", "--pool", "default", "--type", "process"]
   ```

3. **Update Kubernetes Service** to remove Flow Server port (5000)
4. **Update health checks** to use Prefect API instead

### Step 3: Update Environment Variables

Remove Flow Server URL:
```yaml
# Remove from ConfigMap
# FLOW_SERVER_URL: http://prefect-worker:5000
```

## Comparison

| Feature | Flow Server | Prefect API |
|---------|------------|-------------|
| **Server Type** | Python `http.server` | Uvicorn (ASGI) |
| **Production-Ready** | ❌ No | ✅ Yes |
| **Concurrency** | Single-threaded | Multi-process |
| **Prefect UI Visibility** | ❌ No | ✅ Yes |
| **Flow Run Tracking** | ❌ Limited | ✅ Full |
| **Requires Deployment** | ❌ No | ✅ Yes |
| **Requires Prefect Server** | ❌ No | ✅ Yes |

## Recommendation

**✅ Use Prefect API for Manual Triggers**

**Reasons**:
1. ✅ Production-grade server (Uvicorn)
2. ✅ Full Prefect orchestration and tracking
3. ✅ Visible in Prefect UI
4. ✅ Better observability
5. ✅ Consistent with scheduled flows
6. ✅ No need for separate Flow Server

**When to Keep Flow Server**:
- If you need to trigger flows without deployments
- If Prefect Server might be unavailable
- For development/testing scenarios

## Implementation Example

### Updated PrefectService.java

```java
public String triggerManualRun(Long connectorId) {
    logger.info("Triggering manual run for connector {} via Prefect API", connectorId);
    
    try {
        // Get connector from database
        CAIConnector connector = connectorRepository.findById(connectorId)
                .orElseThrow(() -> new RuntimeException("Connector not found: " + connectorId));
        
        String deploymentId = connector.getPrefectDeploymentId();
        if (deploymentId == null || deploymentId.isEmpty()) {
            throw new RuntimeException(
                "Connector " + connectorId + " does not have a Prefect deployment. " +
                "Please ensure the connector is active and has a deployment created."
            );
        }
        
        // Build request body
        Map<String, Object> parameters = new HashMap<>();
        parameters.put("connector_id", connectorId);
        
        List<String> tags = new ArrayList<>();
        tags.add("manual-trigger");
        tags.add("connector-" + connectorId);
        
        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("parameters", parameters);
        requestBody.put("tags", tags);
        requestBody.put("name", "manual-run-connector-" + connectorId);
        
        // Create flow run via Prefect API
        Map response = webClient.post()
                .uri("/deployments/" + deploymentId + "/create_flow_run")
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(Map.class)
                .doOnSuccess(r -> logger.info("Prefect API response: {}", r))
                .doOnError(e -> logger.error("Prefect API error: {}", e.getMessage()))
                .block();
        
        if (response == null || !response.containsKey("id")) {
            throw new RuntimeException("Invalid response from Prefect API: missing flow run ID");
        }
        
        String flowRunId = (String) response.get("id");
        logger.info("Successfully created flow run {} for connector {}", flowRunId, connectorId);
        return flowRunId;
        
    } catch (WebClientResponseException e) {
        logger.error("Failed to create flow run for connector {}: Status={}, Body={}", 
                connectorId, e.getStatusCode(), e.getResponseBodyAsString());
        throw new RuntimeException("Failed to create flow run: " + e.getResponseBodyAsString(), e);
    } catch (Exception e) {
        logger.error("Unexpected error creating flow run for connector {}: {}", 
                connectorId, e.getMessage(), e);
        throw new RuntimeException("Failed to create flow run: " + e.getMessage(), e);
    }
}
```

## Summary

**Yes, Prefect API can handle manual triggers!** 

The current Flow Server is **not necessary** if you use Prefect API. Migrating to Prefect API provides:
- ✅ Production-grade server
- ✅ Full Prefect orchestration
- ✅ Better observability
- ✅ Consistent with scheduled flows

The Flow Server can be removed once you migrate to Prefect API.

