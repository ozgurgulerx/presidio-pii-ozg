# Azure Container Apps Deployment Guide

This guide explains how to deploy the Presidio PII Backend to Azure Container Apps.

## Prerequisites

- Azure CLI installed (`brew install azure-cli`)
- Azure subscription
- GitHub repository with the code
- Docker installed locally (for testing)

## Architecture

- **Azure Container Registry (ACR)**: Stores Docker images
- **Azure Container Apps**: Serverless container hosting
- **GitHub Actions**: CI/CD pipeline

## Initial Setup

### 1. Login to Azure

```bash
az login
az account set --subscription <your-subscription-id>
```

### 2. Run the Setup Script

```bash
chmod +x scripts/deploy-azure-setup.sh
./scripts/deploy-azure-setup.sh
```

This script will:
- Create a resource group
- Set up Azure Container Registry
- Create Container Apps environment
- Build and deploy the initial image
- Create the Container App with proper resources (2 CPU, 4GB RAM for Ollama)

### 3. Set Up GitHub Secrets for CI/CD

Create an Azure Service Principal for GitHub Actions:

```bash
# Get your subscription ID
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

# Create service principal
az ad sp create-for-rbac \
  --name "presidio-pii-github-actions" \
  --role contributor \
  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/presidio-pii-rg \
  --sdk-auth
```

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

- `AZURE_CLIENT_ID`: Client ID from the output
- `AZURE_TENANT_ID`: Tenant ID from the output  
- `AZURE_SUBSCRIPTION_ID`: Your subscription ID
- `PII_ALLOWED_ORIGINS`: Your frontend URL (e.g., `https://your-frontend.azurestaticapps.net`)

### 4. Grant ACR Access to the Service Principal

```bash
# Get the service principal ID
SP_ID=$(az ad sp list --display-name "presidio-pii-github-actions" --query [0].id -o tsv)

# Get the ACR resource ID
ACR_ID=$(az acr show --name presidiopii --query id -o tsv)

# Assign AcrPush role
az role assignment create \
  --assignee $SP_ID \
  --role AcrPush \
  --scope $ACR_ID
```

## Configuration

### Environment Variables

The following environment variables are configured in the Container App:

| Variable | Default | Description |
|----------|---------|-------------|
| `PII_ALLOWED_ORIGINS` | `*` | CORS allowed origins (set to frontend URL in production) |
| `PII_MAX_TEXT_LENGTH` | `5000` | Maximum text length to analyze |
| `PII_DETERMINISTIC_THRESHOLD` | `0.85` | Confidence threshold for deterministic detection |
| `PII_LLM_TRIGGER_THRESHOLD` | `0.6` | Threshold to trigger LLM fallback |
| `PII_LLM_TIMEOUT_SECONDS` | `15` | Timeout for LLM calls |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `qwen2.5:1.5b-instruct-q4_0` | Ollama model to use |

### Resource Allocation

The Container App is configured with:
- **CPU**: 2.0 cores (needed for Ollama inference)
- **Memory**: 4.0 GB (needed for the LLM model)
- **Replicas**: 1-3 (auto-scaling based on load)

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/azure-container-apps.yml`) automatically:

1. Builds Docker image on push to `main` branch
2. Pushes image to Azure Container Registry
3. Updates Container App with new image
4. Performs health check

### Manual Deployment

To manually trigger deployment:

```bash
# Go to GitHub Actions tab
# Select "Deploy Backend to Azure Container Apps"
# Click "Run workflow"
```

## Testing

### Health Check

```bash
curl https://presidio-pii-backend.{random-suffix}.eastus.azurecontainerapps.io/health
```

Expected response:
```json
{"status": "ok"}
```

### PII Analysis

```bash
curl -X POST https://presidio-pii-backend.{random-suffix}.eastus.azurecontainerapps.io/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "My email is john.doe@example.com and my phone is 555-1234"}'
```

## Monitoring

### View Logs

```bash
az containerapp logs show \
  --name presidio-pii-backend \
  --resource-group presidio-pii-rg \
  --follow
```

### View Metrics

```bash
az monitor metrics list \
  --resource $(az containerapp show --name presidio-pii-backend --resource-group presidio-pii-rg --query id -o tsv) \
  --metric Requests
```

## Updating Configuration

### Update Environment Variables

```bash
az containerapp update \
  --name presidio-pii-backend \
  --resource-group presidio-pii-rg \
  --set-env-vars \
    PII_ALLOWED_ORIGINS="https://your-frontend-url.azurestaticapps.net"
```

### Scale Resources

```bash
az containerapp update \
  --name presidio-pii-backend \
  --resource-group presidio-pii-rg \
  --cpu 4.0 \
  --memory 8.0Gi
```

## Cost Optimization

- Container Apps charges based on vCPU-seconds and memory GB-seconds
- With 1 replica at 2 CPU / 4GB, expect ~$100-150/month
- Consider scaling to 0 replicas during off-hours for cost savings:

```bash
az containerapp update \
  --name presidio-pii-backend \
  --resource-group presidio-pii-rg \
  --min-replicas 0
```

## Troubleshooting

### Container App Not Starting

Check logs:
```bash
az containerapp logs show --name presidio-pii-backend --resource-group presidio-pii-rg --tail 100
```

### LLM Not Working

The Ollama model is downloaded during image build. If issues occur:
1. Check if the model exists in the container
2. Verify Ollama service is running
3. Check OLLAMA_BASE_URL is correct

### High Response Times

- Increase CPU/memory allocation
- Check if LLM is timing out (increase `PII_LLM_TIMEOUT_SECONDS`)
- Consider using a smaller Ollama model

## Cleanup

To delete all resources:

```bash
az group delete --name presidio-pii-rg --yes --no-wait
```

## Next Steps

1. Update frontend to use the deployed backend URL
2. Set up custom domain (optional)
3. Configure Azure Application Insights for monitoring
4. Set up alerts for errors and performance issues
