# Kubernetes Deployment Guide: Clinical AI Prefect Workflows

This document provides step-by-step instructions for deploying the Clinical AI Prefect workflows to a Kubernetes cluster.

## Prerequisites

- Kubernetes cluster (v1.24+)
- `kubectl` configured to access the cluster
- Docker registry access (for pushing the container image)
- Access to create namespaces, deployments, services, configmaps, and secrets
- PostgreSQL database accessible from the cluster
- **Production**: AWS S3 access and HashiCorp Vault for credential management
- **Development**: MinIO storage accessible from the cluster (optional)

## Table of Contents

1. [Overview](#overview)
2. [Pre-deployment Steps](#pre-deployment-steps)
3. [Building and Pushing Container Image](#building-and-pushing-container-image)
4. [Creating Kubernetes Resources](#creating-kubernetes-resources)
5. [Verification](#verification)
6. [Post-deployment Configuration](#post-deployment-configuration)
7. [Troubleshooting](#troubleshooting)
8. [Scaling and Maintenance](#scaling-and-maintenance)

## Overview

The deployment consists of two main components:

1. **Prefect Server**: Orchestrates and schedules workflow execution
2. **Prefect Worker**: Executes workflows and processes data

Both components are deployed as Kubernetes Deployments with associated Services.

## Pre-deployment Steps

### 1. Create Namespace

```bash
kubectl create namespace clinical-ai
```

### 2. Verify Database Access

Ensure your PostgreSQL database is accessible from the Kubernetes cluster:

```bash
# Test database connectivity (from a pod in the cluster)
kubectl run -it --rm db-test --image=postgres:17 --restart=Never -- \
  psql -h <postgres-host> -U <username> -d cai_data -c "SELECT 1;"
```

### 3. Verify Storage Access

#### Production (AWS S3)

Ensure AWS S3 is accessible and credentials are available in HashiCorp Vault:

```bash
# Test AWS S3 connectivity (from a pod in the cluster)
kubectl run -it --rm s3-test --image=amazon/aws-cli --restart=Never -- \
  aws s3 ls

# Verify Vault access (if using External Secrets Operator)
kubectl get externalsecret clinical-ai-aws-credentials -n clinical-ai
```

#### Development (MinIO)

Ensure MinIO storage is accessible:

```bash
# Test MinIO connectivity (from a pod in the cluster)
kubectl run -it --rm s3-test --image=amazon/aws-cli --restart=Never -- \
  aws --endpoint-url=http://<minio-host>:9000 s3 ls
```

## Building and Pushing Container Image

### 1. Build the Container Image

```bash
cd clinical-ai-prefect
docker build -t clinical-ai-prefect:latest .
```

### 2. Tag for Your Registry

```bash
# Replace with your registry URL
docker tag clinical-ai-prefect:latest \
  <your-registry>/clinical-ai-prefect:latest
docker tag clinical-ai-prefect:latest \
  <your-registry>/clinical-ai-prefect:v1.0.0
```

### 3. Push to Registry

```bash
docker push <your-registry>/clinical-ai-prefect:latest
docker push <your-registry>/clinical-ai-prefect:v1.0.0
```

### 4. Update Deployment YAML

Update `k8s/deployment.yaml` to use your registry image:

```yaml
image: <your-registry>/clinical-ai-prefect:latest
imagePullPolicy: Always  # or IfNotPresent
```

## Creating Kubernetes Resources

### 1. Create ConfigMap

First, update `k8s/configmap.yaml` with your environment-specific values:

**Production Configuration:**
```yaml
storage-environment: "production"
aws-region: "us-east-1"  # Update with your AWS region
prefect-api-url: "http://clinical-ai-prefect-server.clinical-ai.svc.cluster.local:4200/api"
```

**Development Configuration:**
```yaml
storage-environment: "development"
minio-endpoint: "http://minio.clinical-ai.svc.cluster.local:9000"
prefect-api-url: "http://clinical-ai-prefect-server.clinical-ai.svc.cluster.local:4200/api"
```

Then apply:

```bash
kubectl apply -f k8s/configmap.yaml
```

### 2. Configure HashiCorp Vault Integration (Production)

**IMPORTANT**: In production, AWS credentials must come from HashiCorp Vault.

#### Option A: External Secrets Operator (Recommended)

1. **Install External Secrets Operator** (if not already installed):
   ```bash
   kubectl apply -f https://github.com/external-secrets/external-secrets/releases/latest/download/external-secrets.yaml
   ```

2. **Update `k8s/external-secret.yaml.template`** with your Vault configuration:
   - Update Vault server URL
   - Update Vault path for AWS credentials
   - Update authentication method (Kubernetes auth recommended)

3. **Create SecretStore**:
   ```bash
   kubectl apply -f k8s/external-secret.yaml.template
   ```

4. **Verify ExternalSecret sync**:
   ```bash
   kubectl get externalsecret clinical-ai-aws-credentials -n clinical-ai
   kubectl get secret clinical-ai-aws-credentials -n clinical-ai
   ```

#### Option B: Vault Agent Sidecar

See `k8s/vault-agent-sidecar.yaml.example` for configuration details.

### 3. Create Database Secrets

**IMPORTANT**: Never commit actual secrets to version control.

Create the database secret using `kubectl`:

```bash
kubectl create secret generic clinical-ai-prefect-secrets \
  --from-literal=database-url='postgresql://user:password@postgres-service:5432/cai_data' \
  --from-literal=prefect-database-url='postgresql+asyncpg://user:password@postgres-service:5432/cai_data' \
  --namespace=clinical-ai
```

**For Development Only** (MinIO credentials):
```bash
kubectl create secret generic clinical-ai-prefect-secrets \
  --from-literal=database-url='postgresql://user:password@postgres-service:5432/cai_data' \
  --from-literal=prefect-database-url='postgresql+asyncpg://user:password@postgres-service:5432/cai_data' \
  --from-literal=minio-access-key='minioadmin' \
  --from-literal=minio-secret-key='minioadmin' \
  --namespace=clinical-ai
```

Or use a secrets management tool (e.g., Sealed Secrets, External Secrets Operator).

### 3. Create ServiceAccount

```bash
kubectl apply -f k8s/serviceaccount.yaml
```

### 4. Deploy Prefect Server

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

The deployment will create both Prefect Server and Worker deployments.

**Production Notes**:
- AWS credentials are automatically injected from HashiCorp Vault via External Secrets Operator
- S3 bucket names are configured in the database (`cai_defined_sources` and `cai_defined_destinations` tables)
- The `STORAGE_ENVIRONMENT` environment variable determines whether to use AWS S3 (production) or MinIO (development)

**See `PRODUCTION_SETUP.md` for detailed production configuration instructions.**

### 5. Verify Deployment

```bash
# Check deployments
kubectl get deployments -n clinical-ai

# Check pods
kubectl get pods -n clinical-ai -l app=clinical-ai-prefect-server
kubectl get pods -n clinical-ai -l app=clinical-ai-prefect-worker

# Check services
kubectl get services -n clinical-ai
```

## Verification

### 1. Check Pod Status

```bash
# All pods should be in Running state
kubectl get pods -n clinical-ai

# Check pod logs
kubectl logs -n clinical-ai -l app=clinical-ai-prefect-server
kubectl logs -n clinical-ai -l app=clinical-ai-prefect-worker
```

### 2. Test Prefect Server API

```bash
# Port-forward to access Prefect Server
kubectl port-forward -n clinical-ai svc/clinical-ai-prefect-server 4200:4200

# In another terminal, test the API
curl http://localhost:4200/api/health
```

### 3. Access Prefect UI

**Yes, Prefect UI is fully accessible for deployment verification!**

#### Option 1: Port-Forward (Development/Testing)

```bash
# Port-forward to Prefect Server
kubectl port-forward -n clinical-ai svc/clinical-ai-prefect-server 4200:4200

# Then open in your browser:
# http://localhost:4200
```

**What you can verify:**
- ✅ View all deployments created by backend
- ✅ See deployment schedules
- ✅ Monitor flow runs
- ✅ View execution logs
- ✅ Check deployment status

#### Option 2: Ingress (Production)

Enable Ingress in Helm values:

```yaml
server:
  ingress:
    enabled: true
    className: "nginx"
    hosts:
      - host: prefect.yourdomain.com
        path: /
```

Then access at: `https://prefect.yourdomain.com`

**See `examples/PREFECT_UI_ACCESS.md` for detailed UI access instructions.**

## Post-deployment Configuration

### 1. Configure Work Pools

Access Prefect UI and create work pools:

1. Navigate to Work Pools
2. Create a new work pool named `default`
3. Set worker type to `process`
4. Configure concurrency limits as needed

### 2. Register Flows

Flows can be registered via:

- Prefect CLI (from a development machine)
- Prefect API
- Prefect UI

Example:

```bash
# From development machine with Prefect CLI
prefect deploy flows/dlt_pipeline_flow.py:run_connector_pipeline \
  --name run_connector_pipeline \
  --pool default \
  --work-queue-name default
```

### 3. Configure Backend Integration

Update the Spring Boot backend to use the Prefect Server service:

```yaml
app:
  prefect:
    api-url: http://clinical-ai-prefect-server.clinical-ai.svc.cluster.local:4200/api
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod events
kubectl describe pod <pod-name> -n clinical-ai

# Check pod logs
kubectl logs <pod-name> -n clinical-ai

# Common issues:
# - Image pull errors: Check registry credentials
# - Database connection errors: Verify DATABASE_URL secret
# - ConfigMap errors: Verify configmap exists and has correct keys
```

### Database Connection Issues

```bash
# Test database connectivity from a pod
kubectl run -it --rm db-test --image=postgres:17 --restart=Never -- \
  psql "$(kubectl get secret clinical-ai-prefect-secrets -n clinical-ai -o jsonpath='{.data.database-url}' | base64 -d)"
```

### Prefect Server Not Accessible

```bash
# Check service endpoints
kubectl get endpoints -n clinical-ai clinical-ai-prefect-server

# Check service selector matches pod labels
kubectl get pods -n clinical-ai -l app=clinical-ai-prefect-server
kubectl get svc -n clinical-ai clinical-ai-prefect-server -o yaml
```

### Worker Not Connecting to Server

```bash
# Check worker logs
kubectl logs -n clinical-ai -l app=clinical-ai-prefect-worker

# Verify PREFECT_API_URL environment variable
kubectl exec -n clinical-ai <worker-pod> -- env | grep PREFECT_API_URL
```

### High Memory Usage

```bash
# Check resource usage
kubectl top pods -n clinical-ai

# Adjust resource limits in deployment.yaml if needed
```

## Scaling and Maintenance

### Scaling Workers

```bash
# Scale workers horizontally
kubectl scale deployment clinical-ai-prefect-worker --replicas=4 -n clinical-ai

# Or update deployment.yaml and reapply
```

### Updating Deployment

```bash
# Update image
kubectl set image deployment/clinical-ai-prefect-worker \
  prefect-worker=<new-image> \
  -n clinical-ai

# Or update deployment.yaml and reapply
kubectl apply -f k8s/deployment.yaml
```

### Rolling Restart

```bash
# Restart all pods
kubectl rollout restart deployment/clinical-ai-prefect-server -n clinical-ai
kubectl rollout restart deployment/clinical-ai-prefect-worker -n clinical-ai
```

### Backup and Recovery

1. **Database Backup**: Ensure PostgreSQL database is backed up regularly
2. **Prefect State**: Prefect Server stores state in PostgreSQL (in `prefect` schema)
3. **Configuration**: Backup ConfigMaps and Secrets (securely)

## Monitoring

### Recommended Monitoring

1. **Pod Health**: Kubernetes liveness and readiness probes
2. **Resource Usage**: CPU and memory metrics
3. **Flow Execution**: Prefect UI and API
4. **Database Connections**: Monitor connection pool usage
5. **Error Rates**: Monitor failed flow runs

### Log Aggregation

Consider integrating with:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Loki + Grafana
- Cloud logging services (CloudWatch, Stackdriver, etc.)

## Security Considerations

1. **Secrets Management**: Use Kubernetes Secrets or external secrets management
2. **Network Policies**: Restrict pod-to-pod communication
3. **RBAC**: Configure appropriate service account permissions
4. **Image Security**: Scan container images for vulnerabilities
5. **Credential Rotation**: Regularly rotate database and S3 credentials

## Additional Resources

- [Prefect Documentation](https://docs.prefect.io/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Clinical AI Platform Documentation](../README.md)

## Support

For deployment issues, contact:
- DevOps Team: [contact information]
- Development Team: [contact information]

