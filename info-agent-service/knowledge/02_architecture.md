# System Architecture & Technical Design

## Multi-Agent AI Orchestration
Agent M utilizes a decoupled microservices architecture. The "Brain" is powered by **LangGraph** and **LangChain**, orchestrating multiple specialized agents. The execution layer is hosted within a **Scalable EKS Cluster** across multiple Availability Zones to ensure high availability and low-latency trade execution.

## Microservices Breakdown
| Service | Tech Stack | Responsibility |
| :--- | :--- | :--- |
| **User Info** | Go (Gin) | Manages user profiles, preferences, and authentication. |
| **Trading Agent M** | Python (LangGraph) | Core agentic logic and decision-making engine. |
| **RAG Chatbot** | Python (FastAPI) | LLM-driven interaction for portfolio and news queries. |
| **Information Agent** | Python (FastAPI) | Answers user queries about platform features and usage. |
| **News Scrapers** | Python | Specialized scrapers for Yahoo Finance and TradingView. |
| **Sentiment Analysis** | Python (FinBERT) | Processes news through FinBERT for financial sentiment. |
| **Ticker/Event Identification** | Python | Identifies relevant stocks and financial events in text. |
| **Qdrant Retrieval** | Python | Manages vector embeddings for efficient news retrieval. |
| **Trading Service** | Python (Alpaca) | Interface for brokerage API integrations (Alpaca). |
| **Notification Alert** | Python | Dispatches real-time alerts via various channels. |
| **Metrics Tracker** | Python | Monitors portfolio performance and system health. |
| **News Aggregator** | Python | Orchestrates and consolidates scraped news data. |
| **Preprocessing** | Python | Cleans and prepares raw data for analysis. |

## Intelligence & Infrastructure
* **LLMs:** Powered by **Google Gemini**, **Groq**, and **Ollama**.
* **Orchestration:** **LangGraph** and **LangChain** for multi-agent workflows.
* **Databases:** **PostgreSQL** (Transactional), **MongoDB** (Documents), **Redis** (Caching), and **Qdrant** (Vector).
* **Execution:** Hosted within a **Scalable EKS Cluster** across multiple Availability Zones.

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
