#!/bin/bash
# Quick deployment status checker

echo "⏰ Deployment Status Check - $(date +%H:%M:%S)"
echo "=========================================="
echo ""

# Check deployment log
if [ -f /tmp/azure-deploy.log ]; then
  echo "📋 Latest deployment log (last 10 lines):"
  echo "----------------------------------------"
  tail -10 /tmp/azure-deploy.log
  echo ""
fi

# Check if image is built
echo "🐳 Docker Image Status:"
IMAGE_COUNT=$(az acr repository list --name presidiopii --query "length(@)" -o tsv 2>/dev/null || echo "0")
if [ "$IMAGE_COUNT" -gt 0 ]; then
  echo "✅ Image(s) exist in registry:"
  az acr repository list --name presidiopii -o table
else
  echo "⏳ No images in registry yet (still building...)"
fi
echo ""

# Check ACR build status
echo "🔨 Build History:"
az acr task list-runs --registry presidiopii --top 3 -o table 2>/dev/null || echo "No builds yet"
echo ""

# Check Container App
echo "📱 Container App Status:"
APP_EXISTS=$(az containerapp show --name presidio-pii-backend --resource-group presidio-pii-rg --query "name" -o tsv 2>/dev/null || echo "")
if [ -n "$APP_EXISTS" ]; then
  echo "✅ Container App exists"
  APP_URL=$(az containerapp show --name presidio-pii-backend --resource-group presidio-pii-rg --query properties.configuration.ingress.fqdn -o tsv)
  APP_STATUS=$(az containerapp show --name presidio-pii-backend --resource-group presidio-pii-rg --query properties.runningStatus -o tsv)
  echo "   URL: https://$APP_URL"
  echo "   Status: $APP_STATUS"
  
  # Try health check
  echo ""
  echo "🏥 Health Check:"
  curl -s -f "https://$APP_URL/health" && echo "" || echo "   ❌ Health check failed or app not ready"
else
  echo "⏳ Container App not created yet"
fi
