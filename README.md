<p align="center">
  <img src="https://img.shields.io/github/issues/SMU-IS/agentic-ai-trading-fe" alt="Issue">
  <img src="https://img.shields.io/github/issues-pr/SMU-IS/agentic-ai-trading-fe" alt="Pull Request">
  <img src="https://img.shields.io/github/v/release/SMU-IS/agentic-ai-trading-fe" alt="Release Badge">
</p>

<p align="center">
  <img width="250" height="250" alt="Agent-M" src="https://github.com/user-attachments/assets/e5a2b7ac-b397-4db6-88b1-4b61101ab62b" />
</p>

<h1 align="center">🤖 Agent M - Agentic AI Trading Portfolio Backend</h1>

<p align="center">
  <strong>A dynamic, fully autonomous trading portfolio companion designed to navigate the complex digital financial landscape.</strong>
</p>

<p align="center">
  <a href="https://agentic-m.com"><strong>🚀 Check out the Live App</strong></a>
</p>

---

## 📖 Overview

Agent M leverages a multi-agent AI architecture to transform real-time market data, traditional news, and internet sentiment into personalized, actionable investment decisions. The platform operates on behalf of users to mitigate information overload and circumvent human emotional bias, executing optimized buy or sell orders via external brokerage APIs within user-defined risk guardrails.

## ⚙️ Key Features

- **Multi-Agent AI Architecture**: Sophisticated multi-agent system coordinating tasks from data ingestion to trade execution.
- **Real-Time Data Ingestion**: Automated scraping and aggregation of financial news and internet sentiment (Yahoo Finance, Reddit, X, TradingView).
- **NLP-Powered Analysis**: Advanced NLP (spaCy, NLTK, FinBERT) for event extraction and sentiment scoring.
- **Credibility & Fact-Checking**: AI-driven validation of news claims and source reliability scoring.
- **RAG-Powered Chatbot**: Natural language interface for querying news history and portfolio context using Retrieval-Augmented Generation.
- **Application Knowledge Base**: Dedicated information agent to assist users with platform features and technical documentation.
- **Autonomous Trading**: Synthesis of market signals with portfolio context to execute trades via APIs (e.g., Alpaca, IBKR).
- **Interactive Dashboard**: Real-time sentiment indicators, P&L trends, and portfolio visualization.
- **Proactive Notifications**: Critical alerts for breaking news affecting holdings and trade execution confirmations.

## ☁️ AWS Architecture

<p align="center">
  <img width="3033" height="2526" alt="aws_infrastructure" src="https://github.com/user-attachments/assets/2e0f6edc-3cff-404e-a401-6a1bf19b1d60" />
</p>

## 🚀 Features

<p align="center">
    <img width="927" height="519" alt="agent-m-features" src="https://github.com/user-attachments/assets/6ed543c4-178e-404d-97c6-62c68b283881" />
</p>

## ⚙️ System Architecture

<p align="center">
  <img width="1442" alt="Agent M Architecture" src="https://github.com/user-attachments/assets/d4e42a75-0ea0-4020-9746-6925d36defa1" />
</p>

## 🧩 Microservices Overview

The backend is built using a highly decoupled microservices architecture:

| Service                         | Responsibility                                           | Language/Framework |
| :------------------------------ | :------------------------------------------------------- | :----------------- |
| **User Info**                   | Manages user profiles, preferences, and authentication.  | Go (Gin)           |
| **Trading Agent M**             | Core agentic logic and decision-making engine.           | Python (LangGraph) |
| **RAG Chatbot**                 | LLM-driven interaction for portfolio and news queries.   | Python (FastAPI)   |
| **Information Agent**           | Answers user queries about platform features and usage.  | Python (FastAPI)   |
| **News Scrapers**               | Specialized scrapers for Yahoo Finance and TradingView.  | Python             |
| **Sentiment Analysis**          | Processes news through FinBERT for financial sentiment.  | Python             |
| **Ticker/Event Identification** | Identifies relevant stocks and financial events in text. | Python             |
| **Qdrant Retrieval**            | Manages vector embeddings for efficient news retrieval.  | Python             |
| **Trading Service**             | Interface for brokerage API integrations (Alpaca/IBKR).  | Python             |
| **Notification Alert**          | Dispatches real-time alerts via various channels.        | Python             |
| **Metrics Tracker**             | Monitors portfolio performance and system health.        | Python             |

## 👨‍💻 Tech Stack

### API & Gateway Layer

- [Kong Gateway](https://konghq.com/products/kong-gateway)
- [Gin, Golang](https://gin-gonic.com/en/)
- [FastAPI, Python](https://fastapi.tiangolo.com)

### Intelligence & Agentic Logic

- [LangChain](https://langchain.com)
- [LangGraph](https://langchain.com/langgraph)
- [Google Gemini](https://ai.google.dev)
- [Groq](https://groq.com)
- [Ollama](https://ollama.com)
- [FinBERT](https://huggingface.co/yiyanghkust/finbert-tone)

### Persistence & Memory

- [Qdrant Vector DB](https://qdrant.tech)
- [PostgreSQL](https://postgresql.org)
- [MongoDB](https://www.mongodb.com)
- [Redis](https://redis.io)

### Infrastructure & DevOps

- [Terraform](https://developer.hashicorp.com/terraform)
- [Amazon Web Services](https://aws.amazon.com)
- [Docker](https://www.docker.com)
- [Kubernetes (EKS)](https://aws.amazon.com/eks/)

## 🚀 Getting Started

### Prerequisites

- [Docker](https://www.docker.com/products/docker-desktop/)
- [Docker Compose](https://docs.docker.com/compose/)
- [Python 3.10+](https://www.python.org/downloads/)
- [Go 1.21+](https://go.dev/dl/)

### Quick Start

1. **Clone the repository**:

   ```bash
   git clone https://github.com/SMU-IS/agentic-ai-trading-be.git
   cd agentic-ai-trading-be
   ```

2. **Setup Environment**:
   - Create `.env` files for each microservice based on their respective `.env.sample` files.
   - Configure a root `.env` for global settings (Kong, DB credentials).

3. **Launch Services**:

   ```bash
   docker compose up -d
   ```

4. **Verify Deployment**:
   - Live App: [https://agentic-m.com](https://agentic-m.com)
   - API Endpoint: [http://api.agentic-m.com/api/v1/rag/healthcheck](http://api.agentic-m.com/api/v1/rag/healthcheck)

## 🗳️ Acknowledgement

Developed by **Mvidia (Team 2)**, IS484 Project Experience in collaboration with **UBS**, 2026

<a href="https://www.linkedin.com/in/joshydavid/"><img src="https://github.com/user-attachments/assets/f9dd5867-724a-4dff-a2ad-61c81ea6e3b5" width="80" title="Joshua David"></a>&nbsp;
<a href="https://www.linkedin.com/in/bryancjh/"><img src="https://github.com/user-attachments/assets/cc1782b1-e71f-410a-97a4-cfec08bccead" width="80" title="Bryan Chia"></a>&nbsp;
<a href="https://www.linkedin.com/in/derricklkh/"><img src="https://github.com/user-attachments/assets/2db4b711-b7d0-4368-8d12-6449c3fa2aa2" width="80" title="Derrick Lau"></a>&nbsp;
<a href="https://www.linkedin.com/in/shawn-ng-yh/"><img src="https://github.com/user-attachments/assets/6bd4f3a7-6784-402a-b891-03d91e15d705" width="80" title="Shawn Ng"></a>&nbsp;
<a href="https://www.linkedin.com/in/jiayenbeh/"><img src="https://github.com/user-attachments/assets/23ca9394-c7ed-4cdc-a1fc-5c67a37df9ee" width="80" title="Beh Jia Yen"></a>&nbsp;
<a href="https://www.linkedin.com/in/zi-you-foo"><img src="https://github.com/user-attachments/assets/506dbced-5709-4477-978a-c0fb12ce7aec" width="80" title="Foo Zi You"></a>
