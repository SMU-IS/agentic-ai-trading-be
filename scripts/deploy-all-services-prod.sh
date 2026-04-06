#!/bin/bash
set -e

# =============================================================================================
# ⚠️ DISCLAIMER: MANUAL TESTING ONLY
# This script is intended for MANUAL use only if the deployment or terraform folder has changes
# configurations and infrastructure changes in a controlled environment.
#
# THE PRIMARY PRODUCTION DEPLOYMENT IS HANDLED AUTOMATICALLY VIA THE CI/CD PIPELINE.
# Do not use this script for routine deployments.
# =============================================================================================


ENV_DIR=$(dirname "$(readlink -f "$0")")
if [ -f "$ENV_DIR/../.env" ]; then
    set -a
    source "$ENV_DIR/../.env"
    set +a
    echo "Loaded .env from $ENV_DIR/../.env"
else
    echo "Error: .env file not found at $ENV_DIR/../.env"
    exit 1
fi

# Configuration - Pulling from Environment Variables
REGION="${AWS_REGION}"
CLUSTER_NAME="${EKS_CLUSTER_NAME}"
ACCOUNT_ID="${AWS_ACCOUNT_ID}"

# Safety Check: If Account ID is empty, stop the script
if [ -z "$ACCOUNT_ID" ]; then
  echo "❌ Error: AWS_ACCOUNT_ID environment variable is not set."
  echo "Run: export AWS_ACCOUNT_ID='123456789012'"
  exit 1
fi

REGISTRY="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

echo "🚀 Starting Production Deployment for $CLUSTER_NAME..."

# 1. Switch to Production Context
kubectl config use-context "arn:aws:eks:$REGION:$ACCOUNT_ID:cluster/$CLUSTER_NAME"

# 2. List of Services to deploy (using the values-*.yaml filename)
# Format: values-<SERVICE>.yaml
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

# Function to get ECR repo name AND Helm release name from the Service name
# $1 = service (the part after 'values-' in filename)
# Returns: "HelmReleaseName ECRRepoName"
get_mapping() {
  case "$1" in
    "chatbot")               echo "rag-chatbot rag-chatbot" ;;
    "event-identification")  echo "event-identification-service event-identification-service" ;;
    "info-agent")            echo "info-agent-service info-agent-service" ;;
    "metrics-tracker")       echo "metrics-tracker-service metrics-tracker-service" ;;
    "news-aggregator")       echo "news-aggregator-service news-aggregator-service" ;;
    "news-scraper")          echo "news-scraper news-scraper" ;;
    "notification-alert")    echo "notification-alert notification-alert" ;;
    "pre-processing")        echo "preprocessing-service preprocessing-service" ;;
    "qdrant-retrieval")      echo "qdrant-retrieval qdrant-retrieval" ;;
    "sentiment-analysis")    echo "sentiment-analysis-service sentiment-analysis-service" ;;
    "ticker-identification") echo "ticker-identification-service ticker-identification-service" ;;
    "trading-agent-m")       echo "trading-agent-m trading-agent-m" ;;
    "trading-service")       echo "trading-service trading-service" ;;
    "trading-view")          echo "news-scraper-tradingview news-scraper-tradingview" ;;
    "user-info")             echo "user-info user-info" ;;
    *)                       echo "" ;;
  esac
}

# 3. Deploy each service
for SERVICE in "${SERVICES[@]}"; do
  MAPPING=$(get_mapping "$SERVICE")
  if [ -z "$MAPPING" ]; then
    echo "⚠️ Error: No mapping found for $SERVICE. Skipping..."
    continue
  fi

  # Split mapping (Bash 3.2 friendly)
  HELM_RELEASE=$(echo $MAPPING | awk '{print $1}')
  REPO_NAME=$(echo $MAPPING | awk '{print $2}')

  echo "--------------------------------------------------"
  echo "📦 Processing: $SERVICE"
  echo "   Helm Release: $HELM_RELEASE"
  echo "   ECR Repo:     $REPO_NAME"

  # A. Fetch the LATEST image tag from ECR (Sorted by push date)
  echo "🔍 Searching for latest image tag in ECR..."
  LATEST_TAG=$(aws ecr describe-images \
    --repository-name "$REPO_NAME" \
    --query 'sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]' \
    --output text)

  if [ "$LATEST_TAG" == "None" ] || [ -z "$LATEST_TAG" ]; then
    echo "⚠️ Error: No image tags found for $REPO_NAME. Skipping..."
    continue
  fi

  echo "🚀 Found latest tag: $LATEST_TAG"

  # B. Deploy using Helm
  VALUES_FILE="deploy/values-$SERVICE.yaml"

  if [ -f "$VALUES_FILE" ]; then
    echo "🏗️  Upgrading $HELM_RELEASE with tag $LATEST_TAG..."

    # ⚠️ RECREATION LOGIC: We delete the deployment first because selector labels are immutable.
    # This ensures our new 'api' and 'worker' labels are correctly applied.
    # Since we have minReplicas: 2 for core services, we do this one by one.
    echo "🗑️  Deleting old deployment to update immutable selectors..."
    kubectl delete deployment "$HELM_RELEASE-infra" --ignore-not-found=true
    if [ "$SERVICE" == "event-identification" ] || [ "$SERVICE" == "pre-processing" ] || [ "$SERVICE" == "qdrant-retrieval" ] || [ "$SERVICE" == "sentiment-analysis" ] || [ "$SERVICE" == "ticker-identification" ]; then
       kubectl delete deployment "$HELM_RELEASE-infra-worker" --ignore-not-found=true
    fi

    helm upgrade --install "$HELM_RELEASE" ./infra \
      --namespace default \
      --values "$VALUES_FILE" \
      --set image.tag="$LATEST_TAG" \
      --wait \
      --timeout 600s \
      --rollback-on-failure
    echo "✅ $HELM_RELEASE deployed successfully!"
  else
    echo "⚠️ Warning: $VALUES_FILE not found, skipping..."
  fi
done

echo "--------------------------------------------------"
echo "🎉 Production Deployment Complete!"
echo "Check status with: kubectl get pods"
echo "--------------------------------------------------"
