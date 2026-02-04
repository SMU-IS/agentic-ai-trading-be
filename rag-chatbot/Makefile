IMAGE_NAME = rag-chatbot
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
	@kubectl create secret generic rag-chatbot-secrets --from-env-file=.env.prod --dry-run=client -o yaml | kubectl apply -f - --insecure-skip-tls-verify --validate=false
	@echo ""

	@echo "===================================================="
	@echo "🚀 2. APPLYING KUBERNETES MANIFESTS"
	@echo "===================================================="
	@kubectl apply -f ../k8s/rag-chatbot --insecure-skip-tls-verify --validate=false
	@echo ""

	@echo "===================================================="
	@echo "♻️  3. RESTARTING & WAITING FOR ROLLOUT"
	@echo "===================================================="
	@kubectl rollout restart deployment rag-chatbot-deployment
	@kubectl rollout status deployment rag-chatbot-deployment
	@echo ""

	@echo "===================================================="
	@echo "📊 4. FINAL SYSTEM STATUS"
	@echo "===================================================="
	@kubectl get pods,svc,ingress -l app=rag-chatbot
	@echo ""
	@echo "✅ RAG Chatbot Deployment Complete!"

logs:
	kubectl logs -l app=rag-chatbot -f --tail=50
