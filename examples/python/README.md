# Python Examples

This directory contains Python examples demonstrating the complete connector lifecycle.

## Prerequisites

- Python 3.8 or higher
- `requests` library
- Backend API running and accessible
- Prefect Server running and accessible from backend

## Installation

Install required dependencies:

```bash
pip install requests
```

Or add to `requirements.txt`:

```
requests>=2.31.0
```

## Configuration

Before running the examples, update the following in `connector_lifecycle_example.py`:

```python
BASE_URL = "http://localhost:8080/api/v1"
AUTH_TOKEN = "your-jwt-token-here"  # Optional if auth is disabled
```

Also update the connector creation parameters:
- `projectId` - Your project ID
- `definedSourceId` - Your source ID
- `definedDestinationId` - Your destination ID

## Running the Example

### Make executable

```bash
chmod +x connector_lifecycle_example.py
```

### Run

```bash
python3 connector_lifecycle_example.py
```

Or:

```bash
./connector_lifecycle_example.py
```

## Example Flow

The example demonstrates:

1. **Create Connector** - Creates a connector with schedule "0 */4 * * *" (every 4 hours)
   - Backend automatically creates Prefect deployment
   - Returns connector ID and deployment ID

2. **Update Schedule** - Changes schedule to "0 */6 * * *" (every 6 hours)
   - Backend automatically updates Prefect deployment schedule

3. **Trigger Manual Run** - Executes the flow immediately
   - Bypasses schedule, runs flow right away

4. **Deactivate Connector** - Sets `isActive = False`
   - Backend automatically deletes Prefect deployment
   - Scheduled runs stop

5. **Delete Connector** - Removes connector from database
   - Backend automatically deletes Prefect deployment (if still exists)

## API Endpoints Used

- `POST /api/v1/connectors` - Create connector
- `PATCH /api/v1/connectors/{id}` - Update connector
- `POST /api/v1/connectors/{id}/trigger` - Trigger manual run
- `DELETE /api/v1/connectors/{id}` - Delete connector
- `GET /api/v1/connectors/{id}` - Get connector details (helper function)

## Error Handling

The example includes basic error handling. In production, you should:
- Implement retry logic for transient failures
- Handle authentication errors
- Validate responses
- Log errors appropriately
- Use proper exception handling

## Additional Examples

You can extend this example to:
- List all connectors
- Get connector run history
- Monitor flow run status
- Handle batch operations

