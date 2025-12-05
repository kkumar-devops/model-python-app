# Technical Specifications: Clinical AI Prefect Workflows

## Document Information

- **Version**: 1.0.0
- **Last Updated**: 2024
- **Author**: Clinical AI Development Team

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Flow Design](#flow-design)
4. [Task Specifications](#task-specifications)
5. [Data Sources](#data-sources)
6. [Data Destinations](#data-destinations)
7. [Error Handling](#error-handling)
8. [Performance Considerations](#performance-considerations)
9. [Security](#security)
10. [Configuration](#configuration)

## 1. Overview

The Clinical AI Prefect service is a workflow orchestration system built on Prefect 2.14+ that executes data ingestion and transformation pipelines. It integrates with the Clinical AI Data Ingestion Platform to process data from various sources and deliver it to multiple destinations.

### Key Features

- **Multi-source Support**: PostgreSQL databases, S3/MinIO, filesystem
- **Multi-destination Support**: PostgreSQL, S3, SFTP (TrueNAS), NFS, REST API
- **Data Transformation**: CSV processing, file transfers, schema management
- **Orchestration**: Prefect-based workflow management
- **Monitoring**: Integration with Prefect UI and database logging
- **Scalability**: Process-based worker pool for parallel execution

## 2. Architecture

### 2.1 System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Clinical AI Platform                      │
│                                                              │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │ Spring Boot  │──────│  PostgreSQL  │                    │
│  │   Backend    │      │   Database   │                    │
│  └──────┬───────┘      └──────────────┘                    │
│         │                                                     │
│         │ HTTP/API                                            │
│         ▼                                                     │
│  ┌──────────────────────────────────────┐                    │
│  │      Prefect Server (Orchestrator)   │                    │
│  │  - Flow scheduling                   │                    │
│  │  - Run management                    │                    │
│  │  - UI dashboard                     │                    │
│  └──────────────┬───────────────────────┘                    │
│                 │                                             │
│                 │ API                                          │
│                 ▼                                             │
│  ┌──────────────────────────────────────┐                    │
│  │    Prefect Worker (Flow Executor)   │                    │
│  │  - Flow execution                   │                    │
│  │  - Task scheduling                  │                    │
│  │  - Logging                          │                    │
│  └──────────────┬───────────────────────┘                    │
│                 │                                             │
│                 │ Python Execution                            │
│                 ▼                                             │
│  ┌──────────────────────────────────────┐                    │
│  │      dlt Pipeline (Data Loader)     │                    │
│  │  - Data extraction                   │                    │
│  │  - Transformation                    │                    │
│  │  - Loading                           │                    │
│  └──────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Communication Flow

1. **Backend → Prefect Server**: Spring Boot backend triggers flows via Prefect API
2. **Prefect Server → Worker**: Server schedules flows to available workers
3. **Worker → Database**: Worker reads connector configuration from PostgreSQL
4. **Worker → Source**: Worker connects to data source (PostgreSQL, S3, etc.)
5. **Worker → Destination**: Worker transfers data to destination
6. **Worker → Database**: Worker updates run status in PostgreSQL

### 2.3 Deployment Architecture

- **Prefect Server**: Single instance, stateless, can be scaled horizontally
- **Prefect Worker**: Multiple instances, process-based execution
- **Manual Triggers**: Via Prefect API (deployment flow runs)
- **Database**: Shared PostgreSQL instance for configuration and logging

## 3. Flow Design

### 3.1 Main Flow: `run_connector_pipeline`

**Flow Signature**:
```python
@flow(name="run_connector_pipeline")
def run_connector_pipeline(
    connector_id: int,
    prefect_flow_run_id: str = None
) -> Dict[str, Any]
```

**Flow Steps**:

1. **Initialize Flow Run**
   - Generate or retrieve Prefect flow run ID
   - Create logger context

2. **Create Run Record**
   - Insert record into `cai_connector_runs` table
   - Status: `started`
   - Store Prefect flow run ID for correlation

3. **Read Connector Configuration**
   - Query `cai_connectors` table
   - Join with `cai_defined_sources` and `cai_defined_destinations`
   - Merge base configs with connector-specific overrides
   - Return source and destination configurations

4. **Execute Data Pipeline**
   - Route to appropriate handler based on source type:
     - Database source → `handle_database_source()`
     - Filesystem/S3 source → `run_dlt_pipeline()` or `transfer_files_function()`

5. **Update Run Record**
   - Update status: `success` or `failed`
   - Store rows ingested count
   - Store log summary
   - Set `finished_at` timestamp

### 3.2 Flow Execution Modes

#### Scheduled Execution
- Flows are scheduled via Prefect deployments
- Cron-based scheduling supported
- Managed by Prefect Server

#### Manual Execution
- Triggered via Prefect API (creates flow run from deployment)
- Triggered via Spring Boot backend (uses Prefect API)

#### Direct Execution
- Can be called directly as Python function
- Useful for testing and debugging
- Bypasses Prefect orchestration

## 4. Task Specifications

### 4.1 Task: `read_connector_config`

**Purpose**: Retrieve connector configuration from database

**Input**:
- `connector_id: int` - Connector identifier

**Output**:
```python
{
    "connector_id": int,
    "connector_name": str,
    "source_type": str,  # "sql_database", "filesystem", etc.
    "source_config": Dict[str, Any],
    "destination_type": str,  # "postgres", "s3", "sftp", etc.
    "destination_config": Dict[str, Any]
}
```

**Database Query**:
```sql
SELECT 
    c.id, c.name, 
    c.source_config_override, c.destination_config_override,
    ds.config as source_base_config, 
    dd.config as dest_base_config,
    alc_s.lookup_code as source_type,
    alc_d.lookup_code as dest_type
FROM cai_connectors c
LEFT JOIN cai_defined_sources ds ON c.defined_source_id = ds.id
LEFT JOIN cai_defined_destinations dd ON c.defined_destination_id = dd.id
LEFT JOIN ad_lookup_codes alc_s ON ds.source_type_lookup_code_id = alc_s.id
LEFT JOIN ad_lookup_codes alc_d ON dd.destination_type_lookup_code_id = alc_d.id
WHERE c.id = %s
```

**Error Handling**:
- Raises `ValueError` if connector not found
- Logs error and re-raises for Prefect to handle

### 4.2 Task: `create_run_record`

**Purpose**: Create a run record in the database

**Input**:
- `connector_id: int`
- `prefect_flow_run_id: str`

**Output**:
- `run_id: int` - Database record ID

**Database Operation**:
```sql
INSERT INTO cai_connector_runs 
    (connector_id, status, prefect_flow_run_id, started_at)
VALUES (%s, 'started', %s, NOW())
RETURNING id
```

**Error Handling**:
- Database errors are logged and re-raised
- Flow continues even if record creation fails (with warning)

### 4.3 Task: `run_dlt_pipeline`

**Purpose**: Execute the data pipeline based on source/destination types

**Input**:
- `config: Dict[str, Any]` - Full connector configuration

**Output**:
```python
{
    "status": str,  # "success" or "failed"
    "rows_ingested": int,
    "log_summary": str
}
```

**Processing Logic**:

1. **Database Source** (`sql_database`, `postgres`, `database`):
   - Execute SQL query
   - Export to CSV
   - Upload to destination (S3, SFTP, filesystem)

2. **Filesystem/S3 Source**:
   - **File Transfer Mode**: Direct file transfer (S3→S3, S3→SFTP, S3→NFS, S3→REST API)
   - **Data Extraction Mode**: Use dlt to process CSV files and load to PostgreSQL

**Error Handling**:
- Returns error status in result dict
- Logs detailed error information
- Does not raise exceptions (returns error status instead)

### 4.4 Task: `update_run_record`

**Purpose**: Update run record with completion status

**Input**:
- `run_id: int`
- `status: str`
- `rows_ingested: int` (optional)
- `log_summary: str` (optional)

**Database Operation**:
```sql
UPDATE cai_connector_runs
SET status = %s,
    finished_at = NOW(),
    rows_ingested = COALESCE(%s, rows_ingested),
    log_summary = COALESCE(%s, log_summary)
WHERE id = %s
```

## 5. Data Sources

### 5.1 PostgreSQL Database

**Configuration**:
```json
{
    "host": "postgres.example.com",
    "port": 5432,
    "database": "source_db",
    "username": "user",
    "password": "password",
    "query": "SELECT * FROM table WHERE condition",
    "csv_filename": "export_20240101.csv",
    "batch_size": 10000,
    "use_server_side_cursor": true,
    "chunk_size_mb": 5
}
```

**Processing**:
- Uses server-side cursors for large datasets
- Streams results to avoid memory issues
- Exports to CSV format
- Supports configurable batch sizes

**Limitations**:
- Only SELECT queries supported
- Large result sets require sufficient disk space for CSV export

### 5.2 S3/MinIO Storage

**Configuration**:
```json
{
    "bucket": "customer-data",
    "path": "incoming",
    "file_pattern": "*.csv",
    "aws_access_key_id": "minioadmin",
    "aws_secret_access_key": "minioadmin",
    "endpoint_url": "http://minio:9000"
}
```

**Processing**:
- Lists objects matching file pattern
- Supports glob patterns (`*.csv`, `data_*.txt`)
- Downloads files for processing or transfer

**File Transfer Modes**:
- S3 → S3: Copy and delete
- S3 → SFTP: Download and upload
- S3 → NFS: Download and write
- S3 → REST API: Download and POST/PUT

### 5.3 Local Filesystem

**Configuration**:
```json
{
    "path": "/mnt/data/incoming",
    "file_pattern": "*.csv"
}
```

**Processing**:
- Reads files from local or NFS-mounted path
- Processes with dlt or transfers to destination

## 6. Data Destinations

### 6.1 PostgreSQL

**Configuration**:
```json
{
    "host": "postgres.example.com",
    "port": 5432,
    "database": "target_db",
    "username": "user",
    "password": "password",
    "schema": "public",
    "connection_string": "postgresql://user:pass@host:port/db"
}
```

**Processing**:
- Uses dlt PostgreSQL destination
- Automatically creates tables based on source schema
- Supports schema management

### 6.2 S3/MinIO

**Configuration**:
```json
{
    "bucket": "output",
    "prefix": "processed/",
    "aws_access_key_id": "minioadmin",
    "aws_secret_access_key": "minioadmin",
    "endpoint_url": "http://minio:9000"
}
```

**Processing**:
- Uploads files or data to S3 bucket
- Supports multipart upload for large files (>25MB)
- Configurable chunk sizes

### 6.3 SFTP (TrueNAS Scale)

**Configuration**:
```json
{
    "host": "truenas.example.com",
    "port": 22,
    "username": "user",
    "password": "password",
    "pkey_path": "/path/to/private/key",
    "path": "/mnt/pool/dataset/incoming"
}
```

**Processing**:
- Connects via Paramiko SFTP client
- Supports password or key-based authentication
- Creates destination directories if needed
- Transfers files directly

### 6.4 NFS/Local Filesystem

**Configuration**:
```json
{
    "path": "/mnt/nfs/destination"
}
```

**Processing**:
- Writes files directly to mounted path
- Creates directories as needed
- Supports local and NFS-mounted paths

### 6.5 REST API

**Configuration**:
```json
{
    "url": "https://api.example.com/upload",
    "method": "POST",
    "auth_type": "bearer_token",
    "token": "bearer-token-here",
    "file_field_name": "file",
    "additional_fields": {
        "projectName": "PROJ1",
        "subdirectory": "incoming"
    },
    "use_multipart": true,
    "content_type": "application/octet-stream",
    "headers": {
        "X-Custom-Header": "value"
    }
}
```

**Authentication Types**:
- `bearer_token`: Bearer token in Authorization header
- `api_key`: API key in custom header
- `basic`: Basic authentication

**Processing**:
- Downloads file from source
- Uploads via HTTP POST/PUT/PATCH
- Supports multipart/form-data or raw binary
- Retries on failure (3 attempts with exponential backoff)
- Does not delete source file if upload fails

## 7. Error Handling

### 7.1 Error Categories

1. **Configuration Errors**:
   - Missing required fields
   - Invalid connector ID
   - Malformed configuration JSON

2. **Connection Errors**:
   - Database connection failures
   - S3/MinIO connection failures
   - SFTP connection failures
   - Network timeouts

3. **Processing Errors**:
   - SQL query execution failures
   - File transfer failures
   - Data transformation errors
   - dlt pipeline failures

4. **Resource Errors**:
   - Insufficient disk space
   - Memory limitations
   - File permission errors

### 7.2 Error Handling Strategy

- **Task Level**: Tasks catch exceptions and return error status in result dict
- **Flow Level**: Flow catches exceptions, updates run record, and re-raises
- **Database Errors**: Logged with full context, run record updated with error message
- **Retry Logic**: REST API transfers include retry logic (3 attempts)
- **Partial Failures**: File transfers continue even if individual files fail

### 7.3 Logging

- All errors are logged with full stack traces
- Prefect context provides structured logging
- Database run records store error summaries
- Flow execution logs via Prefect API and UI

## 8. Performance Considerations

### 8.1 Large Dataset Handling

**Database Sources**:
- Server-side cursors for streaming results
- Configurable batch sizes (default: 10,000 rows)
- Temporary file usage for large CSV exports
- Memory-efficient CSV writing

**File Transfers**:
- Multipart uploads for large S3 files (>25MB)
- Configurable chunk sizes
- Parallel processing via Prefect worker pool

### 8.2 Scalability

- **Horizontal Scaling**: Multiple Prefect workers can run in parallel
- **Process-based Execution**: Each flow run in separate process
- **Resource Limits**: Configurable via Kubernetes resource requests/limits

### 8.3 Optimization Tips

1. Use server-side cursors for large database queries
2. Configure appropriate batch sizes based on available memory
3. Use multipart uploads for large S3 files
4. Monitor worker pool utilization
5. Adjust Prefect worker concurrency limits

## 9. Security

### 9.1 Credential Management

- **Database Credentials**: Stored in database configuration JSON
- **S3 Credentials**: Environment variables or configuration JSON
- **SFTP Credentials**: Configuration JSON (password or key path)
- **API Tokens**: Configuration JSON

**Best Practices**:
- Use Kubernetes Secrets for sensitive credentials
- Rotate credentials regularly
- Use key-based authentication for SFTP when possible
- Encrypt configuration at rest

### 9.2 Network Security

- All connections should use TLS/SSL when available
- SFTP connections use SSH encryption
- REST API connections should use HTTPS
- Network policies restrict worker access

### 9.3 Access Control

- Prefect Server API authentication
- Database access via connection string with credentials
- S3 access via IAM or access keys
- SFTP access via username/password or keys

## 10. Configuration

### 10.1 Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `PREFECT_API_URL` | Yes | Prefect Server API URL | `http://prefect-server:4200/api` |
| `DATABASE_URL` | Yes | PostgreSQL connection string | `postgresql://user:pass@host:5432/db` |
| `MINIO_ACCESS_KEY` | No* | MinIO access key | `minioadmin` |
| `MINIO_SECRET_KEY` | No* | MinIO secret key | `minioadmin` |
| `MINIO_ENDPOINT` | No* | MinIO endpoint | `http://minio:9000` |
| Flow Server | Removed | Manual triggers now use Prefect API | N/A |

*Required if using S3/MinIO sources or destinations

### 10.2 Database Configuration

Connector configurations are stored in PostgreSQL:
- `cai_connectors`: Connector definitions with overrides
- `cai_defined_sources`: Base source configurations
- `cai_defined_destinations`: Base destination configurations

### 10.3 Prefect Configuration

- Work pool: `default`
- Work queue: `default`
- Worker type: `process`
- Concurrency: Configurable per worker

## Appendix A: Database Schema

### `cai_connector_runs`
```sql
CREATE TABLE cai_connector_runs (
    id SERIAL PRIMARY KEY,
    connector_id INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL,
    prefect_flow_run_id VARCHAR(255),
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    rows_ingested INTEGER,
    log_summary TEXT
);
```

### `cai_connectors`
```sql
CREATE TABLE cai_connectors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    defined_source_id INTEGER,
    defined_destination_id INTEGER,
    source_config_override JSONB,
    destination_config_override JSONB
);
```

## Appendix B: Example Configurations

See the main platform documentation for detailed connector configuration examples.

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2024 | Development Team | Initial specification |

