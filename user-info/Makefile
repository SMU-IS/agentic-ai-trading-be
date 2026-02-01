IMAGE_NAME = user-info-go
TAG = v1
REGISTRY = joshdavidang

.PHONY: deploy logs clean build

build:
	@echo "===================================================="
	@echo "📦 BUILDING DOCKER IMAGE"
	@echo "===================================================="
	docker build -t $(REGISTRY)/$(IMAGE_NAME):$(TAG) .
	@echo "📤 Pushing image to registry..."
	docker push $(REGISTRY)/$(IMAGE_NAME):$(TAG)
	@echo ""

deploy:
	@echo ""
	@echo "===================================================="
	@echo "🔐 1. SYNCING SECRETS"
	@echo "===================================================="
	@kubectl create secret generic user-info-secrets --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
	@echo ""

	@echo "===================================================="
	@echo "🚀 2. APPLYING KUBERNETES MANIFESTS"
	@echo "===================================================="
	@kubectl apply -f ../k8s/user-info
	@echo ""

	@echo "===================================================="
	@echo "♻️  3. RESTARTING & WAITING FOR ROLLOUT"
	@echo "===================================================="
	@kubectl rollout restart deployment user-info-deployment
	@kubectl rollout status deployment user-info-deployment
	@echo ""

	@echo "===================================================="
	@echo "📊 4. FINAL SYSTEM STATUS"
	@echo "===================================================="
	@kubectl get pods,svc,ingress -l app=user-info
	@echo ""
	@echo "✅ Deployment Complete!"

logs:
	kubectl logs -l app=user-info -f --tail=50
