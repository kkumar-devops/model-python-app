# Clinical AI Prefect Helm Chart

This Helm chart deploys the Clinical AI Prefect service (Server and Worker) to a Kubernetes cluster.

## Prerequisites

- Kubernetes 1.24+
- Helm 3.0+
- PostgreSQL database accessible from the cluster
- **Production**: AWS S3 access and HashiCorp Vault for credentials
- **Development**: MinIO storage (optional)

## Installation

### Quick Start

```bash
# Install with default values
helm install clinical-ai-prefect ./helm/clinical-ai-prefect

# Install with production values
helm install clinical-ai-prefect ./helm/clinical-ai-prefect -f ./helm/clinical-ai-prefect/values-production.yaml

# Install with development values
helm install clinical-ai-prefect ./helm/clinical-ai-prefect -f ./helm/clinical-ai-prefect/values-development.yaml
```

### Custom Installation

```bash
# Install with custom values file
helm install clinical-ai-prefect ./helm/clinical-ai-prefect -f my-values.yaml

# Install with inline values
helm install clinical-ai-prefect ./helm/clinical-ai-prefect \
  --set config.storageEnvironment=production \
  --set worker.replicaCount=3 \
  --set worker.image.tag=v1.0.0
```

## Configuration

### Required Secrets

Before installing, create the required secrets:

#### Database Secrets

```bash
kubectl create secret generic clinical-ai-prefect-secrets \
  --from-literal=database-url='postgresql://user:password@host:5432/database' \
  --from-literal=prefect-database-url='postgresql+asyncpg://user:password@host:5432/database' \
  --namespace=clinical-ai
```

#### AWS Credentials (Production)

For production, AWS credentials should come from HashiCorp Vault via External Secrets Operator. See `PRODUCTION_SETUP.md` for details.

Alternatively, create the secret manually:

```bash
kubectl create secret generic clinical-ai-aws-credentials \
  --from-literal=aws-access-key-id='YOUR_ACCESS_KEY' \
  --from-literal=aws-secret-access-key='YOUR_SECRET_KEY' \
  --namespace=clinical-ai
```

#### MinIO Credentials (Development)

```bash
kubectl create secret generic clinical-ai-prefect-secrets \
  --from-literal=minio-access-key='minioadmin' \
  --from-literal=minio-secret-key='minioadmin' \
  --namespace=clinical-ai
```

## Values

### Key Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `config.storageEnvironment` | Storage environment: "production" or "development" | `"production"` |
| `config.aws.region` | AWS region for S3 | `"us-east-1"` |
| `worker.enabled` | Enable Prefect Worker | `true` |
| `worker.replicaCount` | Number of worker replicas | `2` |
| `worker.image.repository` | Worker image repository | `"clinical-ai-prefect"` |
| `worker.image.tag` | Worker image tag | `"latest"` |
| `server.enabled` | Enable Prefect Server | `true` |
| `server.replicaCount` | Number of server replicas | `1` |
| `server.image.tag` | Server image tag | `"2.14-python3.11"` |

### Complete Values Reference

See `values.yaml` for all available configuration options.

## Upgrading

```bash
# Upgrade with new values
helm upgrade clinical-ai-prefect ./helm/clinical-ai-prefect -f values-production.yaml

# Upgrade with inline values
helm upgrade clinical-ai-prefect ./helm/clinical-ai-prefect \
  --set worker.replicaCount=5
```

## Rollback

```bash
# List releases
helm list

# Rollback to previous version
helm rollback clinical-ai-prefect

# Rollback to specific revision
helm rollback clinical-ai-prefect 2
```

## Uninstallation

```bash
helm uninstall clinical-ai-prefect
```

**Note**: This does not delete secrets or persistent volumes. Delete them manually if needed.

## Verification

```bash
# Check release status
helm status clinical-ai-prefect

# Check pods
kubectl get pods -n clinical-ai -l app.kubernetes.io/instance=clinical-ai-prefect

# Check services
kubectl get svc -n clinical-ai -l app.kubernetes.io/instance=clinical-ai-prefect

# View logs
kubectl logs -n clinical-ai -l app.kubernetes.io/component=worker
kubectl logs -n clinical-ai -l app.kubernetes.io/component=server
```

## Production Deployment

For production deployments, see `PRODUCTION_SETUP.md` for:
- HashiCorp Vault integration
- External Secrets Operator setup
- AWS S3 configuration
- Security best practices

## Troubleshooting

### Pods Not Starting

```bash
# Check pod events
kubectl describe pod <pod-name> -n clinical-ai

# Check pod logs
kubectl logs <pod-name> -n clinical-ai

# Verify secrets exist
kubectl get secrets -n clinical-ai
```

### Configuration Issues

```bash
# View rendered templates
helm template clinical-ai-prefect ./helm/clinical-ai-prefect

# Dry-run installation
helm install clinical-ai-prefect ./helm/clinical-ai-prefect --dry-run --debug
```

### External Secrets Not Syncing

```bash
# Check ExternalSecret status
kubectl get externalsecret -n clinical-ai

# Check External Secrets Operator logs
kubectl logs -n external-secrets-system -l app.kubernetes.io/name=external-secrets
```

## Support

For issues and questions:
- Check `DEPLOYMENT.md` for deployment instructions
- Check `PRODUCTION_SETUP.md` for production-specific setup
- Contact DevOps Team: [contact information]

