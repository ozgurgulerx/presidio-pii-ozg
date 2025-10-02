# Quick Start - Deploy Backend to Azure

Follow these steps to deploy the Presidio PII backend to Azure Container Apps.

## Step 1: Login to Azure

```bash
az login
```

## Step 2: Run the Setup Script

```bash
cd /Users/ozgurguler/Developer/Projects/presidio-pii-ozg
chmod +x scripts/deploy-azure-setup.sh
./scripts/deploy-azure-setup.sh
```

This will create all Azure resources and deploy the backend. **Note**: The first deployment takes ~10-15 minutes because it needs to download and set up the Ollama model.

## Step 3: Set Up GitHub Actions

### 3.1 Create Service Principal

```bash
# Get your subscription ID
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
echo "Subscription ID: $SUBSCRIPTION_ID"

# Create service principal for GitHub Actions
az ad sp create-for-rbac \
  --name "presidio-pii-github-actions" \
  --role contributor \
  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/presidio-pii-rg \
  --json-auth
```

**Save the output** - you'll need these values for GitHub secrets.

### 3.2 Grant ACR Access

```bash
# Get service principal object ID
SP_OBJECT_ID=$(az ad sp list --display-name "presidio-pii-github-actions" --query "[0].id" -o tsv)

# Get ACR resource ID
ACR_ID=$(az acr show --name presidiopii --query id -o tsv)

# Assign AcrPush role
az role assignment create \
  --assignee $SP_OBJECT_ID \
  --role AcrPush \
  --scope $ACR_ID
```

### 3.3 Add GitHub Secrets

Go to your GitHub repository: `Settings → Secrets and variables → Actions → New repository secret`

Add these secrets from the service principal output:

- **AZURE_CLIENT_ID**: `clientId` from the JSON output
- **AZURE_TENANT_ID**: `tenantId` from the JSON output
- **AZURE_SUBSCRIPTION_ID**: `subscriptionId` from the JSON output

Also add:
- **PII_ALLOWED_ORIGINS**: `*` (or your frontend URL once deployed)

## Step 4: Get Backend URL

```bash
az containerapp show \
  --name presidio-pii-backend \
  --resource-group presidio-pii-rg \
  --query properties.configuration.ingress.fqdn \
  -o tsv
```

Save this URL - you'll need it for the frontend configuration.

## Step 5: Test the Backend

```bash
# Get the backend URL
BACKEND_URL=$(az containerapp show \
  --name presidio-pii-backend \
  --resource-group presidio-pii-rg \
  --query properties.configuration.ingress.fqdn \
  -o tsv)

# Health check
curl https://$BACKEND_URL/health

# Test PII detection
curl -X POST https://$BACKEND_URL/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "My email is john.doe@example.com and my phone is 555-1234"}'
```

## Step 6: Update Frontend

Update the frontend environment variable in Azure Static Web Apps:

```bash
# In the frontend repository settings, update:
NEXT_PUBLIC_ANALYZE_URL=https://<your-backend-url>/analyze
```

Or update the GitHub Actions workflow in the frontend repo to include this environment variable.

## Verification Checklist

- [ ] Backend deployed successfully
- [ ] Health endpoint returns `{"status": "ok"}`
- [ ] Analyze endpoint returns PII entities
- [ ] GitHub Actions workflow runs successfully
- [ ] Frontend connects to backend

## Common Issues

### Issue: Container App not starting
**Solution**: Check logs with:
```bash
az containerapp logs show \
  --name presidio-pii-backend \
  --resource-group presidio-pii-rg \
  --tail 100
```

### Issue: GitHub Actions fails to push image
**Solution**: Verify ACR permissions:
```bash
az role assignment list --assignee <service-principal-id> --all
```

### Issue: CORS errors in frontend
**Solution**: Update CORS origins:
```bash
az containerapp update \
  --name presidio-pii-backend \
  --resource-group presidio-pii-rg \
  --set-env-vars PII_ALLOWED_ORIGINS="https://your-frontend-url.azurestaticapps.net"
```

## Next Steps

1. ✅ Backend deployed
2. ⏳ Update frontend to use backend URL
3. ⏳ Test end-to-end flow
4. ⏳ Set up monitoring and alerts (optional)

---

**Need help?** Check the full [DEPLOYMENT.md](./DEPLOYMENT.md) guide.
