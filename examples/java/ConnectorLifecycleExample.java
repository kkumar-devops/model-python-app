package com.nphase.redcapcloud.examples;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Example demonstrating the complete connector lifecycle:
 * 1. Create connector (with schedule) - automatically creates Prefect deployment
 * 2. Update connector schedule - updates Prefect deployment schedule
 * 3. Trigger manual run - executes flow immediately
 * 4. Deactivate connector - deletes Prefect deployment
 * 5. Delete connector - removes connector and deployment
 * 
 * Prerequisites:
 * - Backend API running and accessible
 * - Valid authentication token (if required)
 * - Prefect Server running and accessible from backend
 */
public class ConnectorLifecycleExample {
    
    private static final String BASE_URL = "http://localhost:8080/api/v1";
    private static final String AUTH_TOKEN = "your-jwt-token-here"; // Optional if auth is disabled
    private static final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();
    private static final ObjectMapper objectMapper = new ObjectMapper();
    
    public static void main(String[] args) {
        try {
            System.out.println("=== Connector Lifecycle Example ===\n");
            
            // Step 1: Create Connector (with schedule)
            Long connectorId = createConnector();
            
            if (connectorId == null) {
                System.err.println("Failed to create connector. Exiting.");
                return;
            }
            
            // Wait a moment for deployment to be created
            Thread.sleep(2000);
            
            // Step 2: Update Connector Schedule
            updateConnectorSchedule(connectorId, "0 */6 * * *"); // Change to every 6 hours
            
            // Step 3: Trigger Manual Run
            triggerManualRun(connectorId);
            
            // Step 4: Deactivate Connector (deletes deployment)
            deactivateConnector(connectorId);
            
            // Step 5: Delete Connector
            deleteConnector(connectorId);
            
            System.out.println("\n=== Lifecycle Example Complete ===");
            
        } catch (Exception e) {
            System.err.println("Error: " + e.getMessage());
            e.printStackTrace();
        }
    }
    
    /**
     * Step 1: Create a new connector with a schedule.
     * This automatically creates a Prefect deployment via the backend.
     */
    private static Long createConnector() throws Exception {
        System.out.println("Step 1: Creating connector with schedule...");
        
        ObjectNode requestBody = objectMapper.createObjectNode();
        requestBody.put("name", "Example Customer Data Pipeline");
        requestBody.put("description", "Example connector for demonstration");
        requestBody.put("projectId", 1L); // Update with your project ID
        requestBody.put("definedSourceId", 1L); // Update with your source ID
        requestBody.put("definedDestinationId", 1L); // Update with your destination ID
        requestBody.put("schedule", "0 */4 * * *"); // Every 4 hours
        requestBody.put("isActive", true);
        requestBody.set("sourceConfigOverride", objectMapper.createObjectNode());
        requestBody.set("destinationConfigOverride", objectMapper.createObjectNode());
        
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/connectors"))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + AUTH_TOKEN) // Optional
                .POST(HttpRequest.BodyPublishers.ofString(requestBody.toString()))
                .build();
        
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        
        if (response.statusCode() == 200 || response.statusCode() == 201) {
            ObjectNode responseBody = (ObjectNode) objectMapper.readTree(response.body());
            Long connectorId = responseBody.get("id").asLong();
            String deploymentId = responseBody.has("prefectDeploymentId") 
                    ? responseBody.get("prefectDeploymentId").asText() 
                    : "pending";
            
            System.out.println("✅ Connector created successfully!");
            System.out.println("   Connector ID: " + connectorId);
            System.out.println("   Prefect Deployment ID: " + deploymentId);
            System.out.println("   Schedule: 0 */4 * * * (every 4 hours)");
            System.out.println("   Note: Prefect deployment is created automatically by the backend\n");
            
            return connectorId;
        } else {
            System.err.println("❌ Failed to create connector: " + response.statusCode());
            System.err.println("Response: " + response.body());
            return null;
        }
    }
    
    /**
     * Step 2: Update the connector's schedule.
     * This automatically updates the Prefect deployment schedule via the backend.
     */
    private static void updateConnectorSchedule(Long connectorId, String newSchedule) throws Exception {
        System.out.println("Step 2: Updating connector schedule...");
        
        ObjectNode requestBody = objectMapper.createObjectNode();
        requestBody.put("schedule", newSchedule);
        
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/connectors/" + connectorId))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + AUTH_TOKEN) // Optional
                .method("PATCH", HttpRequest.BodyPublishers.ofString(requestBody.toString()))
                .build();
        
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        
        if (response.statusCode() == 200) {
            System.out.println("✅ Connector schedule updated successfully!");
            System.out.println("   New Schedule: " + newSchedule + " (every 6 hours)");
            System.out.println("   Note: Prefect deployment schedule updated automatically by the backend\n");
        } else {
            System.err.println("❌ Failed to update schedule: " + response.statusCode());
            System.err.println("Response: " + response.body());
        }
    }
    
    /**
     * Step 3: Trigger a manual run of the connector.
     * This executes the flow immediately without waiting for the schedule.
     */
    private static void triggerManualRun(Long connectorId) throws Exception {
        System.out.println("Step 3: Triggering manual run...");
        
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/connectors/" + connectorId + "/trigger"))
                .header("Authorization", "Bearer " + AUTH_TOKEN) // Optional
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
        
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        
        if (response.statusCode() == 200) {
            System.out.println("✅ Manual run triggered successfully!");
            System.out.println("   Response: " + response.body());
            System.out.println("   Note: Flow is executing in Prefect Worker\n");
        } else {
            System.err.println("❌ Failed to trigger manual run: " + response.statusCode());
            System.err.println("Response: " + response.body());
        }
    }
    
    /**
     * Step 4: Deactivate the connector.
     * This automatically deletes the Prefect deployment via the backend.
     */
    private static void deactivateConnector(Long connectorId) throws Exception {
        System.out.println("Step 4: Deactivating connector...");
        
        ObjectNode requestBody = objectMapper.createObjectNode();
        requestBody.put("isActive", false);
        
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/connectors/" + connectorId))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + AUTH_TOKEN) // Optional
                .method("PATCH", HttpRequest.BodyPublishers.ofString(requestBody.toString()))
                .build();
        
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        
        if (response.statusCode() == 200) {
            System.out.println("✅ Connector deactivated successfully!");
            System.out.println("   Note: Prefect deployment deleted automatically by the backend");
            System.out.println("   Note: Scheduled runs will no longer execute\n");
        } else {
            System.err.println("❌ Failed to deactivate connector: " + response.statusCode());
            System.err.println("Response: " + response.body());
        }
    }
    
    /**
     * Step 5: Delete the connector.
     * This automatically deletes the Prefect deployment (if it still exists) via the backend.
     */
    private static void deleteConnector(Long connectorId) throws Exception {
        System.out.println("Step 5: Deleting connector...");
        
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/connectors/" + connectorId))
                .header("Authorization", "Bearer " + AUTH_TOKEN) // Optional
                .DELETE()
                .build();
        
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        
        if (response.statusCode() == 200 || response.statusCode() == 204) {
            System.out.println("✅ Connector deleted successfully!");
            System.out.println("   Note: Prefect deployment deleted automatically by the backend\n");
        } else {
            System.err.println("❌ Failed to delete connector: " + response.statusCode());
            System.err.println("Response: " + response.body());
        }
    }
}

