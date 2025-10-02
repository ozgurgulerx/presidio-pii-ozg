#!/bin/bash
# Setup script for Azure Container Apps deployment
# This script creates all necessary Azure resources for the backend

set -e

# Configuration
RESOURCE_GROUP="presidio-pii-rg"
LOCATION="eastus"
ACR_NAME="presidiopii"
CONTAINER_APP_ENV="presidio-pii-env"
CONTAINER_APP_NAME="presidio-pii-backend"
IMAGE_NAME="presidio-pii-backend"

echo "🚀 Setting up Azure resources for Presidio PII Backend..."

# 1. Create Resource Group
echo "📦 Creating resource group..."
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION

# 2. Create Azure Container Registry
echo "🐳 Creating Azure Container Registry..."
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true

# 3. Create Container Apps Environment
echo "🌍 Creating Container Apps Environment..."
az containerapp env create \
  --name $CONTAINER_APP_ENV \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# 4. Get ACR credentials
echo "🔑 Getting ACR credentials..."
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv)

# 5. Build and push initial image
echo "🔨 Building and pushing Docker image..."
az acr build \
  --registry $ACR_NAME \
  --image ${IMAGE_NAME}:latest \
  --file Dockerfile/Dockerfile \
  .

# 6. Create Container App
echo "📱 Creating Container App..."
az containerapp create \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $CONTAINER_APP_ENV \
  --image ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:latest \
  --registry-server ${ACR_NAME}.azurecr.io \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --target-port 8000 \
  --ingress external \
  --cpu 2.0 \
  --memory 4.0Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --env-vars \
    PII_ALLOWED_ORIGINS="*" \
    PII_MAX_TEXT_LENGTH="5000" \
    PII_DETERMINISTIC_THRESHOLD="0.85" \
    PII_LLM_TRIGGER_THRESHOLD="0.6" \
    PII_LLM_TIMEOUT_SECONDS="15" \
    OLLAMA_BASE_URL="http://127.0.0.1:11434" \
    OLLAMA_MODEL="qwen2.5:1.5b-instruct-q4_0"

# 7. Get the app URL
APP_URL=$(az containerapp show \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn \
  -o tsv)

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Resource Details:"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Container Registry: $ACR_NAME"
echo "  Container App: $CONTAINER_APP_NAME"
echo "  Backend URL: https://$APP_URL"
echo ""
echo "🔗 Health Check: https://$APP_URL/health"
echo "🔗 API Endpoint: https://$APP_URL/analyze"
echo ""
echo "📝 Next steps:"
echo "  1. Set up GitHub secrets for CI/CD:"
echo "     - AZURE_CLIENT_ID"
echo "     - AZURE_TENANT_ID"
echo "     - AZURE_SUBSCRIPTION_ID"
echo "     - PII_ALLOWED_ORIGINS (your frontend URL)"
echo ""
echo "  2. Update frontend environment variable:"
echo "     NEXT_PUBLIC_ANALYZE_URL=https://$APP_URL/analyze"
echo ""
