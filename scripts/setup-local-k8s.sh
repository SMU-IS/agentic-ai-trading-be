#!/bin/bash
set -e

echo "🚀 Starting Local Kubernetes Setup (Minikube)..."

# 1. Force Minikube context
if ! minikube status >/dev/null 2>&1; then
    minikube start --driver=docker
fi
kubectl config use-context minikube

# 2. Install Kong Gateway via Helm
echo "📦 Installing Kong Gateway..."
helm repo add kong https://charts.konghq.com
helm repo update
helm upgrade --install kong kong/kong \
  --namespace kong \
  --create-namespace \
  --set ingressController.enabled=true \
  --set env.database=off \
  --set controller.ingressClass=kong \
  --set wait=true

# 3. Apply Global Kong Configurations (CORS, JWT, etc.)
echo "🛠️ Applying Global Kong Configurations..."
kubectl apply -f deploy/kong-global-config.yaml

# 3.5 Create the RDS Certs ConfigMap 
echo "📜 Creating RDS Certs ConfigMap..." 
kubectl create configmap rds-certs --from-file=global-bundle.pem=certs/global-bundle.pem --dry-run=client -o yaml | kubectl apply -f - 

# 4. Create the JWT Secret (Mirroring Terraform)
echo "🔐 Creating JWT Secret..."
kubectl create secret generic agentic-ai-jwt-secret \
  --namespace default \
  --from-literal=kongCredType=jwt \
  --from-literal=key=agentic-ai-user-service \
  --from-literal=algorithm=HS256 \
  --from-literal=secret=L5TjuuTAlM8MMcZ9nyhB9QkLXxgyW8tGlPQc40rJcMt \
  --dry-run=client -o yaml | kubectl apply -f -

# 5. Provide instructions
echo "✅ Local Environment Ready!"
echo "--------------------------------------------------"
echo "To deploy a service (e.g., News Scraper):"
echo "  helm upgrade --install news-scraper ./infra -f deploy/values-news-scraper.yaml"
echo ""
echo "To access the gateway:"
echo "  minikube service kong-kong-proxy -n kong"
echo "--------------------------------------------------"
