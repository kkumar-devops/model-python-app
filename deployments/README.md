# Prefect Deployments Directory

This directory is intended for storing **Prefect deployment configuration files** (YAML files) that define how flows should be deployed to Prefect Server.

## Production Workflow

**Important**: In production, deployments are **NOT** created from static YAML files in this directory. Instead:

1. **Initial Setup**: Helm chart deploys Prefect infrastructure (Server + Worker)
2. **Runtime**: When business users create connectors via the frontend:
   - Backend saves connector to database
   - Backend calls Prefect API to create deployment programmatically
   - Deployment is scheduled automatically based on connector's schedule

See [`PRODUCTION_WORKFLOW.md`](./PRODUCTION_WORKFLOW.md) for the complete production workflow.

## What are Prefect Deployments?

In Prefect, a **deployment** is a configuration that:
- Registers a flow with Prefect Server
- Defines scheduling (cron schedules, intervals, etc.)
- Specifies work pools and queues
- Sets default parameters
- Configures infrastructure requirements

## Current Usage

Currently, this directory is **empty** because:

1. **Programmatic Deployment Creation**: Deployments are created via Prefect API from the Spring Boot backend when connectors are created
2. **Database-Driven**: Connector configurations (including schedules) are stored in PostgreSQL
3. **Dynamic Scheduling**: When a user creates a connector with a schedule, the backend automatically creates the Prefect deployment

## When to Use This Directory

You would populate this directory if you want to:

### 1. Initial/Seed Deployments (Optional)

Create initial deployment files for testing or seeding:

```yaml
# deployments/example-connector-deployment.yaml
name: example-connector-pipeline
description: Example scheduled pipeline
flow_name: run_connector_pipeline
entrypoint: flows/dlt_pipeline_flow.py:run_connector_pipeline
work_pool_name: default
work_queue_name: default
parameters:
  connector_id: 1
schedule:
  cron: "0 */6 * * *"  # Every 6 hours
  timezone: "UTC"
tags:
  - connector-1
  - scheduled
```

Then deploy via Helm init container or Kubernetes Job (see [`KUBERNETES_DEPLOYMENT.md`](./KUBERNETES_DEPLOYMENT.md)).

### 2. Local Development

For local testing:

```bash
# For local development only
prefect deploy deployments/example-connector-deployment.yaml
```

**⚠️ Important**: The CLI method above is for **local development only**. 

For **production Kubernetes deployments**, see [`KUBERNETES_DEPLOYMENT.md`](./KUBERNETES_DEPLOYMENT.md) for proper methods.

### 3. Backup/Version Control

Store deployment configurations for:
- Version control
- Disaster recovery
- Documentation
- Migration between environments

## Production Deployment Flow

```
User Creates Connector (Frontend)
    ↓
Backend: ConnectorService.create()
    ↓
Backend: PrefectService.createDeployment()
    ↓
Prefect API: POST /api/deployments/
    ↓
Prefect Server: Registers Deployment
    ↓
Prefect Scheduler: Runs on Schedule
```

**No static YAML files needed** - everything is created programmatically!

## Alternative: Database-Driven Deployments

The current implementation uses **database-driven deployments** where:
- Connector configurations are stored in PostgreSQL (`cai_connectors` table)
- Schedules are stored in `cai_connectors.schedule` (cron format)
- Deployments are created/updated/deleted via Prefect API when connectors change
- No static deployment files are needed

This approach is more flexible for:
- Adding/removing connectors without redeploying
- Changing schedules via database updates
- Managing deployments through the UI/API
- Business users managing their own connectors

## Recommendation

**Keep the directory empty** for production - deployments are created programmatically.

**Use this directory** for:
- Local development/testing
- Initial seed deployments (optional)
- Documentation/examples
- Backup configurations

## References

- [Prefect Deployments Documentation](https://docs.prefect.io/latest/concepts/deployments/)
- [Prefect Deployment YAML Reference](https://docs.prefect.io/latest/api-ref/prefect/deployments/#prefect.deployments.Deployment)
- [Production Workflow Guide](./PRODUCTION_WORKFLOW.md) - **Read this for production deployments**
- [Kubernetes Deployment Guide](./KUBERNETES_DEPLOYMENT.md) - For static deployment files
