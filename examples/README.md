# Connector Lifecycle Examples

This directory contains example programs demonstrating the complete connector lifecycle in both Java and Python.

## Overview

These examples show how to interact with the Clinical AI backend API to manage connectors and their associated Prefect deployments. The backend automatically handles Prefect deployment creation, updates, and deletion.

## Complete Lifecycle

The examples demonstrate the following operations:

1. **Create Connector** (with schedule)
   - Creates connector in database
   - Backend automatically creates Prefect deployment
   - Deployment is scheduled to run on the specified cron schedule

2. **Update Connector Schedule**
   - Updates connector schedule in database
   - Backend automatically updates Prefect deployment schedule
   - Future runs will use the new schedule

3. **Trigger Manual Run**
   - Executes the flow immediately
   - Bypasses the schedule
   - Useful for testing or on-demand execution

4. **Deactivate Connector**
   - Sets `isActive = false`
   - Backend automatically deletes Prefect deployment
   - Scheduled runs stop immediately

5. **Delete Connector**
   - Removes connector from database
   - Backend automatically deletes Prefect deployment (if still exists)
   - All associated data is cleaned up

## Directory Structure

```
examples/
├── README.md                    # This file
├── java/
│   ├── README.md               # Java-specific instructions
│   └── ConnectorLifecycleExample.java
└── python/
    ├── README.md               # Python-specific instructions
    └── connector_lifecycle_example.py
```

## Quick Start

### Java

```bash
cd java
# Update BASE_URL and AUTH_TOKEN in ConnectorLifecycleExample.java
javac -cp ".:jackson-databind-2.15.2.jar" ConnectorLifecycleExample.java
java -cp ".:jackson-databind-2.15.2.jar" ConnectorLifecycleExample
```

### Python

```bash
cd python
pip install requests
# Update BASE_URL and AUTH_TOKEN in connector_lifecycle_example.py
python3 connector_lifecycle_example.py
```

## API Endpoints

All examples use the following backend API endpoints:

| Operation | Method | Endpoint | Description |
|-----------|--------|----------|-------------|
| Create | POST | `/api/v1/connectors` | Create new connector |
| Update | PATCH | `/api/v1/connectors/{id}` | Update connector |
| Get | GET | `/api/v1/connectors/{id}` | Get connector details |
| Trigger | POST | `/api/v1/connectors/{id}/trigger` | Trigger manual run |
| Delete | DELETE | `/api/v1/connectors/{id}` | Delete connector |

## Request/Response Examples

### Create Connector

**Request:**
```json
POST /api/v1/connectors
{
  "name": "Customer Data Pipeline",
  "description": "Pipeline description",
  "projectId": 1,
  "definedSourceId": 1,
  "definedDestinationId": 1,
  "schedule": "0 */4 * * *",
  "isActive": true,
  "sourceConfigOverride": {},
  "destinationConfigOverride": {}
}
```

**Response:**
```json
{
  "id": 123,
  "name": "Customer Data Pipeline",
  "prefectDeploymentId": "deployment-uuid-here",
  "schedule": "0 */4 * * *",
  "isActive": true,
  ...
}
```

### Update Schedule

**Request:**
```json
PATCH /api/v1/connectors/123
{
  "schedule": "0 */6 * * *"
}
```

**Response:**
```json
{
  "id": 123,
  "schedule": "0 */6 * * *",
  ...
}
```

### Trigger Manual Run

**Request:**
```json
POST /api/v1/connectors/123/trigger
```

**Response:**
```json
{
  "status": "success",
  "result": "Flow execution started"
}
```

## Authentication

If authentication is enabled, include the JWT token in the `Authorization` header:

```
Authorization: Bearer <your-jwt-token>
```

If authentication is disabled (public endpoints), you can omit the token.

## Error Handling

Both examples include basic error handling. In production, you should:

- Implement retry logic for transient failures (network issues, 503 errors)
- Handle authentication errors (401) by refreshing tokens
- Validate request/response data
- Log errors appropriately
- Handle timeouts gracefully

## Production Considerations

1. **Base URL**: Update to production API URL
2. **Authentication**: Use proper token management
3. **Error Handling**: Implement comprehensive error handling
4. **Logging**: Use proper logging framework
5. **Configuration**: Use environment variables or config files
6. **Retry Logic**: Implement exponential backoff for retries
7. **Validation**: Validate all inputs before sending requests

## Testing

Before running in production:

1. Test against a development/staging environment
2. Verify Prefect Server is accessible from backend
3. Verify database connectivity
4. Test with sample connectors
5. Monitor Prefect UI for deployment creation

## Support

For issues or questions:
- Check backend API logs
- Check Prefect Server logs
- Verify network connectivity
- Review `PRODUCTION_WORKFLOW.md` for deployment details

