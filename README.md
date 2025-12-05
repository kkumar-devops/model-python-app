# Clinical AI Prefect Workflows

This repository contains Prefect workflows for the Clinical AI Data Ingestion Platform. It handles data extraction, transformation, and loading (ETL) operations for various data sources and destinations.

## 🎯 Overview

The Clinical AI Prefect service orchestrates data pipeline execution for connectors defined in the main platform. It supports:

- **Data Sources**: PostgreSQL databases, S3/MinIO storage, filesystem
- **Data Destinations**: PostgreSQL, S3/MinIO, TrueNAS Scale (SFTP), NFS/Local filesystem, REST API endpoints
- **Data Processing**: CSV extraction, file transfers, data transformation using dlt (data load tool)

## 🏗️ Architecture

```
┌─────────────────┐
│  Spring Boot    │
│   Backend API   │
└────────┬────────┘
         │ HTTP/API
         ▼
┌─────────────────┐
│  Prefect Server │
│   (Orchestrator)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Prefect Worker  │
│  (Flow Runner)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  dlt Pipeline   │
│  (Data Loader)  │
└─────────────────┘
```

## 🔧 Components

### 1. Main Flow (`flows/dlt_pipeline_flow.py`)
- **Flow**: `run_connector_pipeline`
- **Tasks**:
  - `read_connector_config` - Reads connector configuration from database
  - `create_run_record` - Creates a run record in `cai_connector_runs` table
  - `run_dlt_pipeline` - Executes the data pipeline
  - `update_run_record` - Updates run status and results

### 2. Supported Operations

#### Database Source → CSV → Destination
- Extracts data from PostgreSQL using SQL queries
- Exports to CSV format
- Uploads to S3, SFTP, or filesystem

#### S3/Filesystem Source → Destination
- File transfers between S3 buckets
- S3 to SFTP (TrueNAS Scale)
- S3 to NFS/Local filesystem
- S3 to REST API endpoints

#### Data Extraction with dlt
- CSV file processing
- PostgreSQL data loading
- Schema management

## 📋 Prerequisites

- Python 3.11+
- Prefect 2.14+
- PostgreSQL client libraries
- Access to:
  - PostgreSQL database (for connector configuration)
  - MinIO/S3 storage
  - Prefect Server API

## 📦 Installation

### 💻 Local Development

```bash
# Clone the repository
git clone https://github.com/nphaseinc/clinical-ai-prefect.git
cd clinical-ai-prefect

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export PREFECT_API_URL=http://localhost:4200/api
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cai_data
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin
export MINIO_ENDPOINT=http://localhost:9000
```

### 🐳 Docker

```bash
# Build the image
docker build -t clinical-ai-prefect:latest .

# Run with environment variables
docker run -d \
  -e PREFECT_API_URL=http://prefect-server:4200/api \
  -e DATABASE_URL=postgresql://postgres:postgres@postgres:5432/cai_data \
  -e MINIO_ACCESS_KEY=minioadmin \
  -e MINIO_SECRET_KEY=minioadmin \
  -e MINIO_ENDPOINT=http://minio:9000 \
  clinical-ai-prefect:latest
```

## ⚙️ Configuration

### 🔐 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PREFECT_API_URL` | Prefect Server API URL | `http://localhost:4200/api` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@postgres:5432/cai_data` |
| `MINIO_ACCESS_KEY` | MinIO access key | `minioadmin` |
| `MINIO_SECRET_KEY` | MinIO secret key | `minioadmin` |
| `MINIO_ENDPOINT` | MinIO endpoint URL | `http://minio:9000` |

### 🗄️ Database Schema

The service expects the following database tables:
- `cai_connectors` - Connector definitions
- `cai_defined_sources` - Source configurations
- `cai_defined_destinations` - Destination configurations
- `cai_connector_runs` - Run history and status
- `ad_lookup_codes` - Lookup codes for source/destination types

## 🚀 Usage

### ▶️ Starting the Worker

```bash
# Start Prefect worker
prefect worker start --pool default --type process

# Or use the Docker container which starts the Prefect worker
docker run clinical-ai-prefect:latest
```

### 🎯 Triggering Flows

#### Via Prefect API

```bash
# Create a flow run
curl -X POST http://localhost:4200/api/flows/run \
  -H "Content-Type: application/json" \
  -d '{
    "flow_id": "<flow-id>",
    "parameters": {"connector_id": 1}
  }'
```

#### Via Spring Boot Backend

The Spring Boot backend service (`PrefectService`) triggers flows via the Prefect API, creating flow runs from deployments.

## 💻 Development

### 📁 Project Structure

```
clinical-ai-prefect/
├── flows/
│   ├── __init__.py
│   └── dlt_pipeline_flow.py    # Main flow definition
├── deployments/                 # Deployment configurations (optional)
├── deploy_flow.py              # Script to deploy flows to Prefect
├── flow_server_backup/         # Backup of Flow Server (no longer used)
├── Dockerfile                  # Container image definition
├── requirements.txt            # Python dependencies
├── project.toml                # Prefect project configuration
└── README.md                   # This file
```

### 🧪 Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

### ✨ Code Formatting

```bash
# Format code
black flows/ *.py

# Lint code
ruff check flows/ *.py
```

## 🚢 Deployment

See [DEPLOYMENT.md](./DEPLOYMENT.md) for Kubernetes deployment instructions.

## 📊 Monitoring

### 🖥️ Prefect UI

Access the Prefect UI at `http://localhost:4200` to:
- View flow runs
- Monitor execution status
- View logs
- Manage deployments

### ❤️ Health Checks

```bash
# Prefect API health check
curl http://localhost:4200/api/health

# Note: Flow Server removed - manual triggers now use Prefect API
```

## 🔍 Troubleshooting

### ⚠️ Common Issues

1. **Database Connection Errors**
   - Verify `DATABASE_URL` is correct
   - Check PostgreSQL is accessible
   - Ensure database schema is initialized

2. **Prefect API Connection Errors**
   - Verify `PREFECT_API_URL` is correct
   - Check Prefect Server is running
   - Verify network connectivity

3. **S3/MinIO Connection Errors**
   - Verify `MINIO_ENDPOINT` is accessible
   - Check credentials are correct
   - Ensure bucket exists

4. **Flow Execution Failures**
   - Check Prefect UI for detailed error logs
   - Verify connector configuration in database
   - Check source/destination accessibility

## 📝 License

This software is proprietary and confidential. All rights are reserved. This code may not be used, copied, reproduced, modified, or distributed without the express prior written permission of nPhase, Inc.

© 2025 nPhase, Inc. All Rights Reserved.

## 💬 Support

For issues and questions, please contact the development team or create an issue in the repository.

