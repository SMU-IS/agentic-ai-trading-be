# System Architecture & Technical Design

## Multi-Agent AI Orchestration
Agent M utilizes a decoupled microservices architecture. The "Brain" is powered by **LangGraph** and **LangChain**, orchestrating multiple specialized agents. The execution layer is hosted within a **Scalable EKS Cluster** across multiple Availability Zones to ensure high availability and low-latency trade execution.

## Microservices Breakdown
| Service | Tech Stack | Responsibility |
| :--- | :--- | :--- |
| **User Info** | Go (Gin) | Profiles, Auth, and Preferences. |
| **Trading Agent** | Python (LangGraph) | Core decision-making logic and trade signals. |
| **RAG Chatbot** | Python (FastAPI) | News and portfolio context retrieval. |
| **News Scrapers** | Python | Real-time ingestion from Yahoo Finance, Reddit, and X. |
| **Sentiment Analysis** | Python (FinBERT) | Financial-specific NLP scoring. |
| **Qdrant Retrieval** | Python | High-performance vector memory for RAG. |

## Infrastructure Layer

### Networking & Security
* **Edge Defense:** Traffic is routed via **Route 53** through **AWS WAF** (Edge Security) and **CloudFront** for API acceleration.
* **Ingress Control:** An **Internet-Facing NLB** (Network Load Balancer) directs traffic to a **Kong Ingress Controller** in a High-Availability (HA) configuration within the EKS cluster.
* **Compute:** **EKS Control Plane** manages an auto-scaling node fleet powered by **Karpenter** for elastic, right-sized scaling of App Pods (HPA).

### Persistence & Storage
* **Primary Database:** **RDS PostgreSQL** (Multi-AZ Master) in private subnets for transactional metadata.
* **Disaster Recovery:** Cross-region replication to a **Replica VPC (us-west-2)** containing a standby EKS cluster and RDS Read Replica.
* **Object Storage:** **S3 Buckets** act as a replicated store for logs and artifacts.
* **Vector Memory:** **Qdrant Vector DB** for high-performance semantic retrieval.

### Observability & Monitoring
* **Metrics:** **AWS Managed Prometheus** scrapes metrics from the EKS cluster.
* **Logging:** **CloudWatch** handles centralized logs and system alarms.
* **Visualization:** **AWS Grafana** provides the unified dashboard for real-time monitoring of system health and portfolio performance.

### DevOps
* **Containerization:** **Docker** images are stored in **AWS ECR** (Image Registry).
* **IaC:** **Terraform** manages the entire AWS lifecycle.
* **Frontend:** Hosted via **AWS Amplify** for seamless CI/CD and global distribution.
