#!/bin/bash
set -e

echo "🚀 Deploying All Microservices to Local Kubernetes..."

# 1. Force Minikube context
kubectl config use-context minikube

# List of services to deploy (based on your values files in /deploy)
# Exclude the kong-global-config as it's a raw K8s manifest, not a Helm values file.
SERVICES=(
  "chatbot"
  "event-identification"
  "info-agent"
  "metrics-tracker"
  "news-aggregator"
  "news-scraper"
  "notification-alert"
  "pre-processing"
  "qdrant-retrieval"
  "sentiment-analysis"
  "ticker-identification"
  "trading-agent-m"
  "trading-service"
  "trading-view"
  "user-info"
)

for SERVICE in "${SERVICES[@]}"; do
  echo "--------------------------------------------------"
  echo "📦 Deploying Service: $SERVICE..."

  VALUES_FILE="deploy/values-$SERVICE.yaml"

  if [ -f "$VALUES_FILE" ]; then
    helm upgrade --install "$SERVICE" ./infra \
      --namespace default \
      --values "$VALUES_FILE" \
      --wait \
      --timeout 300s
    echo "✅ $SERVICE deployed successfully!"
  else
    echo "⚠️ Warning: $VALUES_FILE not found, skipping..."
  fi
done

echo "--------------------------------------------------"
echo "🎉 All services have been deployed!"
echo "Check status with: kubectl get pods"
echo "Access the gateway: minikube service kong-kong-proxy -n kong --url"
echo "--------------------------------------------------"
