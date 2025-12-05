# Java Examples

This directory contains Java examples demonstrating the complete connector lifecycle.

## Prerequisites

- Java 11 or higher
- Maven or Gradle for dependency management
- Backend API running and accessible
- Jackson library for JSON processing

## Dependencies

Add to your `pom.xml` (Maven):

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.15.2</version>
    </dependency>
</dependencies>
```

Or to your `build.gradle` (Gradle):

```gradle
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.15.2'
}
```

## Configuration

Before running the examples, update the following in `ConnectorLifecycleExample.java`:

```java
private static final String BASE_URL = "http://localhost:8080/api/v1";
private static final String AUTH_TOKEN = "your-jwt-token-here"; // Optional if auth is disabled
```

Also update the connector creation parameters:
- `projectId` - Your project ID
- `definedSourceId` - Your source ID
- `definedDestinationId` - Your destination ID

## Running the Example

### Compile

```bash
javac -cp ".:jackson-databind-2.15.2.jar" ConnectorLifecycleExample.java
```

### Run

```bash
java -cp ".:jackson-databind-2.15.2.jar" ConnectorLifecycleExample
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

4. **Deactivate Connector** - Sets `isActive = false`
   - Backend automatically deletes Prefect deployment
   - Scheduled runs stop

5. **Delete Connector** - Removes connector from database
   - Backend automatically deletes Prefect deployment (if still exists)

## API Endpoints Used

- `POST /api/v1/connectors` - Create connector
- `PATCH /api/v1/connectors/{id}` - Update connector
- `POST /api/v1/connectors/{id}/trigger` - Trigger manual run
- `DELETE /api/v1/connectors/{id}` - Delete connector

## Error Handling

The example includes basic error handling. In production, you should:
- Implement retry logic for transient failures
- Handle authentication errors
- Validate responses
- Log errors appropriately

