# Helm Chart Quick Start Guide

## Installation

### Production

```bash
# 1. Create namespace
kubectl create namespace clinical-ai

# 2. Create database secrets
kubectl create secret generic clinical-ai-prefect-secrets \
  --from-literal=database-url='postgresql://user:pass@host:5432/db' \
  --from-literal=prefect-database-url='postgresql+asyncpg://user:pass@host:5432/db' \
  --namespace=clinical-ai

# 3. Configure External Secrets Operator for AWS credentials (see PRODUCTION_SETUP.md)

# 4. Install with production values
helm install clinical-ai-prefect ./helm/clinical-ai-prefect \
  -f ./helm/clinical-ai-prefect/values-production.yaml \
  --namespace clinical-ai
```

### Development

```bash
# 1. Create namespace
kubectl create namespace clinical-ai

# 2. Create secrets (including MinIO)
kubectl create secret generic clinical-ai-prefect-secrets \
  --from-literal=database-url='postgresql://user:pass@host:5432/db' \
  --from-literal=prefect-database-url='postgresql+asyncpg://user:pass@host:5432/db' \
  --from-literal=minio-access-key='minioadmin' \
  --from-literal=minio-secret-key='minioadmin' \
  --namespace=clinical-ai

# 3. Install with development values
helm install clinical-ai-prefect ./helm/clinical-ai-prefect \
  -f ./helm/clinical-ai-prefect/values-development.yaml \
  --namespace clinical-ai
```

## Common Operations

### Upgrade

```bash
# Upgrade with new values
helm upgrade clinical-ai-prefect ./helm/clinical-ai-prefect \
  -f ./helm/clinical-ai-prefect/values-production.yaml \
  --namespace clinical-ai

# Upgrade with inline values
helm upgrade clinical-ai-prefect ./helm/clinical-ai-prefect \
  --set worker.replicaCount=5 \
  --namespace clinical-ai
```

### Rollback

```bash
# Rollback to previous version
helm rollback clinical-ai-prefect --namespace clinical-ai

# Rollback to specific revision
helm rollback clinical-ai-prefect 2 --namespace clinical-ai
```

### Uninstall

```bash
helm uninstall clinical-ai-prefect --namespace clinical-ai
```

### Status and Verification

```bash
# Check release status
helm status clinical-ai-prefect --namespace clinical-ai

# List all releases
helm list --namespace clinical-ai

# View rendered templates (dry-run)
helm template clinical-ai-prefect ./helm/clinical-ai-prefect \
  -f ./helm/clinical-ai-prefect/values-production.yaml

# Test installation (dry-run)
helm install clinical-ai-prefect ./helm/clinical-ai-prefect \
  -f ./helm/clinical-ai-prefect/values-production.yaml \
  --dry-run --debug \
  --namespace clinical-ai
```

## Customization Examples

### Scale Workers

```bash
helm upgrade clinical-ai-prefect ./helm/clinical-ai-prefect \
  --set worker.replicaCount=5 \
  --namespace clinical-ai
```

### Change Image Tag

```bash
helm upgrade clinical-ai-prefect ./helm/clinical-ai-prefect \
  --set worker.image.tag=v1.0.0 \
  --namespace clinical-ai
```

### Change AWS Region

```bash
helm upgrade clinical-ai-prefect ./helm/clinical-ai-prefect \
  --set config.aws.region=us-west-2 \
  --namespace clinical-ai
```

### Use IAM Role (IRSA on EKS)

```bash
helm upgrade clinical-ai-prefect ./helm/clinical-ai-prefect \
  --set secrets.aws.useIamRole=true \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=arn:aws:iam::ACCOUNT:role/ROLE_NAME \
  --namespace clinical-ai
```

## Troubleshooting

### View Values

```bash
# Get current values
helm get values clinical-ai-prefect --namespace clinical-ai

# Get all values (including defaults)
helm get values clinical-ai-prefect --all --namespace clinical-ai
```

### Check Pods

```bash
# List pods
kubectl get pods -n clinical-ai -l app.kubernetes.io/instance=clinical-ai-prefect

# View logs
kubectl logs -n clinical-ai -l app.kubernetes.io/component=worker
kubectl logs -n clinical-ai -l app.kubernetes.io/component=server
```

### Validate Chart

```bash
# Lint chart
helm lint ./helm/clinical-ai-prefect

# Validate templates
helm template clinical-ai-prefect ./helm/clinical-ai-prefect \
  -f ./helm/clinical-ai-prefect/values-production.yaml | kubectl apply --dry-run=client -f -
```

