#!/usr/bin/env python3
"""
Example demonstrating the complete connector lifecycle:
1. Create connector (with schedule) - automatically creates Prefect deployment
2. Update connector schedule - updates Prefect deployment schedule
3. Trigger manual run - executes flow immediately
4. Deactivate connector - deletes Prefect deployment
5. Delete connector - removes connector and deployment

Prerequisites:
- Backend API running and accessible
- Valid authentication token (if required)
- Prefect Server running and accessible from backend
- requests library: pip install requests
"""

import requests
import json
import time
from typing import Optional, Dict, Any

# Configuration
BASE_URL = "http://localhost:8080/api/v1"
AUTH_TOKEN = "your-jwt-token-here"  # Optional if auth is disabled
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {AUTH_TOKEN}"  # Optional
}


def create_connector() -> Optional[int]:
    """
    Step 1: Create a new connector with a schedule.
    This automatically creates a Prefect deployment via the backend.
    
    Returns:
        Connector ID if successful, None otherwise
    """
    print("Step 1: Creating connector with schedule...")
    
    payload = {
        "name": "Example Customer Data Pipeline",
        "description": "Example connector for demonstration",
        "projectId": 1,  # Update with your project ID
        "definedSourceId": 1,  # Update with your source ID
        "definedDestinationId": 1,  # Update with your destination ID
        "schedule": "0 */4 * * *",  # Every 4 hours
        "isActive": True,
        "sourceConfigOverride": {},
        "destinationConfigOverride": {}
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/connectors",
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            data = response.json()
            connector_id = data.get("id")
            deployment_id = data.get("prefectDeploymentId", "pending")
            
            print("✅ Connector created successfully!")
            print(f"   Connector ID: {connector_id}")
            print(f"   Prefect Deployment ID: {deployment_id}")
            print("   Schedule: 0 */4 * * * (every 4 hours)")
            print("   Note: Prefect deployment is created automatically by the backend\n")
            
            return connector_id
        else:
            print(f"❌ Failed to create connector: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error creating connector: {e}")
        return None


def update_connector_schedule(connector_id: int, new_schedule: str) -> bool:
    """
    Step 2: Update the connector's schedule.
    This automatically updates the Prefect deployment schedule via the backend.
    
    Args:
        connector_id: Connector ID
        new_schedule: New cron schedule (e.g., "0 */6 * * *")
    
    Returns:
        True if successful, False otherwise
    """
    print("Step 2: Updating connector schedule...")
    
    payload = {
        "schedule": new_schedule
    }
    
    try:
        response = requests.patch(
            f"{BASE_URL}/connectors/{connector_id}",
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            print("✅ Connector schedule updated successfully!")
            print(f"   New Schedule: {new_schedule} (every 6 hours)")
            print("   Note: Prefect deployment schedule updated automatically by the backend\n")
            return True
        else:
            print(f"❌ Failed to update schedule: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating schedule: {e}")
        return False


def trigger_manual_run(connector_id: int) -> bool:
    """
    Step 3: Trigger a manual run of the connector.
    This executes the flow immediately without waiting for the schedule.
    
    Args:
        connector_id: Connector ID
    
    Returns:
        True if successful, False otherwise
    """
    print("Step 3: Triggering manual run...")
    
    try:
        response = requests.post(
            f"{BASE_URL}/connectors/{connector_id}/trigger",
            headers=HEADERS,
            timeout=60  # Longer timeout for flow execution
        )
        
        if response.status_code == 200:
            print("✅ Manual run triggered successfully!")
            print(f"   Response: {response.text}")
            print("   Note: Flow is executing in Prefect Worker\n")
            return True
        else:
            print(f"❌ Failed to trigger manual run: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error triggering manual run: {e}")
        return False


def deactivate_connector(connector_id: int) -> bool:
    """
    Step 4: Deactivate the connector.
    This automatically deletes the Prefect deployment via the backend.
    
    Args:
        connector_id: Connector ID
    
    Returns:
        True if successful, False otherwise
    """
    print("Step 4: Deactivating connector...")
    
    payload = {
        "isActive": False
    }
    
    try:
        response = requests.patch(
            f"{BASE_URL}/connectors/{connector_id}",
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            print("✅ Connector deactivated successfully!")
            print("   Note: Prefect deployment deleted automatically by the backend")
            print("   Note: Scheduled runs will no longer execute\n")
            return True
        else:
            print(f"❌ Failed to deactivate connector: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error deactivating connector: {e}")
        return False


def delete_connector(connector_id: int) -> bool:
    """
    Step 5: Delete the connector.
    This automatically deletes the Prefect deployment (if it still exists) via the backend.
    
    Args:
        connector_id: Connector ID
    
    Returns:
        True if successful, False otherwise
    """
    print("Step 5: Deleting connector...")
    
    try:
        response = requests.delete(
            f"{BASE_URL}/connectors/{connector_id}",
            headers=HEADERS,
            timeout=30
        )
        
        if response.status_code in [200, 204]:
            print("✅ Connector deleted successfully!")
            print("   Note: Prefect deployment deleted automatically by the backend\n")
            return True
        else:
            print(f"❌ Failed to delete connector: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error deleting connector: {e}")
        return False


def get_connector(connector_id: int) -> Optional[Dict[str, Any]]:
    """
    Helper function to retrieve connector details.
    
    Args:
        connector_id: Connector ID
    
    Returns:
        Connector data if successful, None otherwise
    """
    try:
        response = requests.get(
            f"{BASE_URL}/connectors/{connector_id}",
            headers=HEADERS,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to get connector: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Error getting connector: {e}")
        return None


def main():
    """Main function demonstrating the complete lifecycle."""
    print("=== Connector Lifecycle Example ===\n")
    
    # Step 1: Create Connector (with schedule)
    connector_id = create_connector()
    
    if connector_id is None:
        print("Failed to create connector. Exiting.")
        return
    
    # Wait a moment for deployment to be created
    time.sleep(2)
    
    # Step 2: Update Connector Schedule
    update_connector_schedule(connector_id, "0 */6 * * *")  # Change to every 6 hours
    
    # Step 3: Trigger Manual Run
    trigger_manual_run(connector_id)
    
    # Step 4: Deactivate Connector (deletes deployment)
    deactivate_connector(connector_id)
    
    # Step 5: Delete Connector
    delete_connector(connector_id)
    
    print("\n=== Lifecycle Example Complete ===")


if __name__ == "__main__":
    main()

