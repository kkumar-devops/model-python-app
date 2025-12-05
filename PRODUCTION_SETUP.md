# Production Setup Guide: AWS S3 and HashiCorp Vault

This guide provides specific instructions for configuring the Clinical AI Prefect service for production deployment with AWS S3 and HashiCorp Vault.

## Overview

In production, the service uses:
- **AWS S3** for object storage (not MinIO)
- **HashiCorp Vault** for secure credential management
- **S3 bucket names** configured in the database (not in Kubernetes files)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              HashiCorp Vault                             │
│  ┌──────────────────────────────────────────────────┐   │
│  │ secret/data/clinical-ai/aws                     │   │
│  │   - aws_access_key_id                            │   │
│  │   - aws_secret_access_key                        │   │
│  └──────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────┘
                        │
                        │ External Secrets Operator
                        │ (syncs secrets to Kubernetes)
                        ▼
┌─────────────────────────────────────────────────────────┐
│              Kubernetes Cluster                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Secret: clinical-ai-aws-credentials            │   │
│  │   - aws-access-key-id                            │   │
│  │   - aws-secret-access-key                        │   │
│  └──────────────────────────────────────────────────┘   │
│                        │                                 │
│                        ▼                                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Prefect Worker Pod                               │   │
│  │   - AWS_ACCESS_KEY_ID (from secret)              │   │
│  │   - AWS_SECRET_ACCESS_KEY (from secret)          │   │
│  │   - AWS_REGION (from ConfigMap)                  │   │
│  │   - STORAGE_ENVIRONMENT=production               │   │
│  └──────────────────────────────────────────────────┘   │
│                        │                                 │
│                        ▼                                 │
│              AWS S3 Buckets                              │
│  (bucket names configured in database)                   │
└─────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **HashiCorp Vault** installed and accessible
2. **External Secrets Operator** installed in Kubernetes cluster
3. **AWS S3** buckets created and accessible
4. **Vault authentication** configured (Kubernetes auth method recommended)
5. **AWS IAM credentials** stored in Vault

## Step-by-Step Setup

### 1. Store AWS Credentials in HashiCorp Vault

```bash
# Using Vault CLI
vault kv put secret/clinical-ai/aws \
  aws_access_key_id="AKIAIOSFODNN7EXAMPLE" \
  aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

# Or using Vault API
curl \
  --header "X-Vault-Token: $VAULT_TOKEN" \
  --request POST \
  --data @payload.json \
  https://vault.example.com/v1/secret/data/clinical-ai/aws
```

**Payload JSON** (`payload.json`):
```json
{
  "data": {
    "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
  }
}
```

### 2. Configure Vault Kubernetes Authentication

```bash
# Enable Kubernetes auth method (if not already enabled)
vault auth enable kubernetes

# Configure Kubernetes auth
vault write auth/kubernetes/config \
  token_reviewer_jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
  kubernetes_host="https://$KUBERNETES_PORT_443_TCP_ADDR:443" \
  kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt

# Create role for Clinical AI Prefect service
vault write auth/kubernetes/role/clinical-ai-prefect \
  bound_service_account_names=clinical-ai-prefect-worker \
  bound_service_account_namespaces=clinical-ai \
  policies=clinical-ai-aws-read \
  ttl=1h

# Create policy for reading AWS credentials
vault policy write clinical-ai-aws-read - <<EOF
path "secret/data/clinical-ai/aws" {
  capabilities = ["read"]
}
EOF
```

### 3. Install External Secrets Operator

```bash
# Install External Secrets Operator
kubectl apply -f https://github.com/external-secrets/external-secrets/releases/latest/download/external-secrets.yaml

# Verify installation
kubectl get pods -n external-secrets-system
```

### 4. Configure External Secrets

1. **Update `k8s/external-secret.yaml.template`** with your Vault configuration:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-backend
  namespace: clinical-ai
spec:
  provider:
    vault:
      server: "https://vault.example.com:8200"  # Your Vault server URL
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "clinical-ai-prefect"
          serviceAccountRef:
            name: clinical-ai-prefect-worker
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: clinical-ai-aws-credentials
  namespace: clinical-ai
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
  target:
    name: clinical-ai-aws-credentials
    creationPolicy: Owner
  data:
  - secretKey: aws-access-key-id
    remoteRef:
      key: secret/data/clinical-ai/aws
      property: aws_access_key_id
  - secretKey: aws-secret-access-key
    remoteRef:
      key: secret/data/clinical-ai/aws
      property: aws_secret_access_key
```

2. **Apply the configuration**:

```bash
kubectl apply -f k8s/external-secret.yaml.template
```

3. **Verify secret sync**:

```bash
# Check ExternalSecret status
kubectl get externalsecret clinical-ai-aws-credentials -n clinical-ai

# Check if secret was created
kubectl get secret clinical-ai-aws-credentials -n clinical-ai

# View secret (base64 encoded)
kubectl get secret clinical-ai-aws-credentials -n clinical-ai -o yaml
```

### 5. Configure ConfigMap for Production

Update `k8s/configmap.yaml`:

```yaml
data:
  storage-environment: "production"  # Set to production
  aws-region: "us-east-1"            # Your AWS region
  prefect-api-url: "http://clinical-ai-prefect-server.clinical-ai.svc.cluster.local:4200/api"
```

Apply:

```bash
kubectl apply -f k8s/configmap.yaml
```

### 6. Configure S3 Bucket Names in Database

S3 bucket names are **not** stored in Kubernetes files. They are configured in the database:

1. **Source buckets** are configured in `cai_defined_sources` table:
   ```sql
   UPDATE cai_defined_sources
   SET config = jsonb_set(config, '{bucket}', '"production-source-bucket"')
   WHERE name = 'Your Source Name';
   ```

2. **Destination buckets** are configured in `cai_defined_destinations` table:
   ```sql
   UPDATE cai_defined_destinations
   SET config = jsonb_set(config, '{bucket}', '"production-dest-bucket"')
   WHERE name = 'Your Destination Name';
   ```

3. **Connector-specific overrides** can be set in `cai_connectors` table:
   ```sql
   UPDATE cai_connectors
   SET source_config_override = jsonb_set(
     source_config_override, 
     '{bucket}', 
     '"connector-specific-bucket"'
   )
   WHERE id = <connector_id>;
   ```

### 7. Deploy the Service

```bash
# Apply all Kubernetes resources
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/serviceaccount.yaml
```

### 8. Verify Deployment

```bash
# Check pods are running
kubectl get pods -n clinical-ai

# Check environment variables in worker pod
kubectl exec -n clinical-ai <worker-pod-name> -- env | grep -E "AWS_|STORAGE"

# Verify AWS credentials are available (should not show values)
kubectl exec -n clinical-ai <worker-pod-name> -- env | grep AWS_ACCESS_KEY_ID
kubectl exec -n clinical-ai <worker-pod-name> -- env | grep AWS_SECRET_ACCESS_KEY

# Test S3 access from pod
kubectl exec -it -n clinical-ai <worker-pod-name> -- \
  python -c "import boto3; s3 = boto3.client('s3'); print(s3.list_buckets())"
```

## Configuration Summary

| Component | Location | Value |
|-----------|----------|-------|
| **Storage Environment** | ConfigMap | `production` |
| **AWS Region** | ConfigMap | `us-east-1` (or your region) |
| **AWS Access Key ID** | Vault → External Secrets → K8s Secret | From Vault |
| **AWS Secret Key** | Vault → External Secrets → K8s Secret | From Vault |
| **S3 Bucket Names** | Database (`cai_defined_sources`, `cai_defined_destinations`) | Configured per connector |

## Troubleshooting

### External Secret Not Syncing

```bash
# Check ExternalSecret status
kubectl describe externalsecret clinical-ai-aws-credentials -n clinical-ai

# Check External Secrets Operator logs
kubectl logs -n external-secrets-system -l app.kubernetes.io/name=external-secrets

# Common issues:
# - Vault authentication failure
# - Incorrect Vault path
# - Missing Vault policy permissions
```

### AWS Credentials Not Available in Pod

```bash
# Verify secret exists
kubectl get secret clinical-ai-aws-credentials -n clinical-ai

# Check deployment environment variables
kubectl describe deployment clinical-ai-prefect-worker -n clinical-ai

# Verify secret keys match deployment expectations
kubectl get secret clinical-ai-aws-credentials -n clinical-ai -o jsonpath='{.data}' | jq
```

### S3 Access Denied

```bash
# Test AWS credentials
kubectl exec -it -n clinical-ai <worker-pod-name> -- \
  aws s3 ls

# Check IAM permissions
# Ensure the AWS credentials have:
# - s3:ListBucket
# - s3:GetObject
# - s3:PutObject
# - s3:DeleteObject
```

### Vault Authentication Issues

```bash
# Test Vault authentication from pod
kubectl exec -it -n clinical-ai <worker-pod-name> -- \
  sh -c 'cat /var/run/secrets/kubernetes.io/serviceaccount/token | vault write -field=token auth/kubernetes/login role=clinical-ai-prefect jwt=-'

# Check Vault role configuration
vault read auth/kubernetes/role/clinical-ai-prefect
```

## Security Best Practices

1. **Rotate Credentials Regularly**: Update AWS credentials in Vault periodically
2. **Use IAM Roles When Possible**: Consider using IAM roles for pods instead of static credentials
3. **Limit Vault Policy Scope**: Only grant read access to specific paths
4. **Monitor Secret Access**: Enable Vault audit logging
5. **Use Vault Namespaces**: Isolate secrets by environment/namespace
6. **Enable Secret Rotation**: Use Vault's dynamic secrets if possible

## Alternative: IAM Roles for Service Accounts (IRSA)

If running on AWS EKS, consider using IAM Roles for Service Accounts instead of static credentials:

1. Create IAM role with S3 permissions
2. Annotate service account with IAM role ARN
3. Remove AWS credential environment variables from deployment
4. boto3 will automatically use the IAM role

This eliminates the need for Vault-stored AWS credentials.

## Support

For production deployment issues, contact:
- DevOps Team: [contact information]
- Security Team: [contact information]

