<p align="center">
  <img src="https://img.shields.io/github/issues/SMU-IS/agentic-ai-trading-be" alt="Issue">
  <img src="https://img.shields.io/github/issues-pr/SMU-IS/agentic-ai-trading-be" alt="Pull Request">
  <img src="https://img.shields.io/github/v/release/SMU-IS/agentic-ai-trading-be" alt="Release Badge">
</p>

:)

<p align="center">
  <img width="220" height="204" alt="agent" src="https://github.com/user-attachments/assets/82d27a27-f71c-42ac-bf51-5b1a83893e6a" />
</p>

## 🤖 Agentic AI Trading Portfolio Backen

Agent M - A dynamic, fully autonomous trading portfolio companion designed to navigate the complex digital financial landscape. Leveraging a multi-agent AI architecture, the platform transforms real-time market data, traditional news, and internet sentiment into personalised, actionable investment decisions.

The system operates on behalf of users to mitigate information overload and circumvent human emotional bias, executing optimised buy or sell orders via external brokerage APIs within user-defined risk guardrails.

## ⚙️ System Architecture

<img width="1442" height="691" alt="Agent M" src="https://github.com/user-attachments/assets/b3e892eb-8d90-4acf-a1cd-13b767843ad1" />

## 👨‍💻 Tech Stack

- [🐍 FastAPI (Python)](https://fastapi.tiangolo.com)
- [🐹 Gin (Golang)](https://gin-gonic.com/en/)
- [🔴 Redis](https://redis.io)
- [🦍 Kong Gateway](https://konghq.com/products/kong-gateway)
- [🧠 FinBERT](https://huggingface.co/yiyanghkust/finbert-tone)
- [🔗 LangChain](https://langchain.com)
- [🦜 LangGraph](https://langchain.com/langgraph)
- [✨ Google Gemini](https://ai.google.dev)
- [🦙 Ollama](https://ollama.com)
- [📂 Qdrant](https://qdrant.tech)
- [🐘 PostgreSQL ](https://postgresql.org)
- [☁️ Amazon Web Services](https://aws.amazon.com)

## ⚙️ Key Features

- **🤖 Multi-Agent AI Architecture**: Utilises a sophisticated multi-agent system to transform market data and sentiment into autonomous investment decisions.
- **📥 Real-Time Data Ingestion**: Automatically scrapes and aggregates daily financial news and high-volume internet sentiment from sources like Yahoo Finance, Reddit, and X.
- **🧠 NLP-Powered News Analysis**: Uses advanced Natural Language Processing (via spaCy, NLTK, and FinBERT) to extract investment-relevant events and perform sentiment analysis.
- **🛡️ Credibility & Fact-Checking**: Evaluates source reliability and uses AI to validate the accuracy of claims, assigning a credibility score to weighted sentiment.
- **💬 RAG Chatbot**: A natural language interface that allows users to query a news database and their portfolio context using Retrieval-Augmented Generation (RAG).
- **🎩 Autonomous Trading Agent**: Synthesises market data with user-specific portfolio context to execute buy/sell orders via external brokerage APIs (e.g., Alpaca/IBKR).
- **📊 Interactive Visualisation Dashboard**: Provides real-time sentiment indicators per ticker, profit and loss (P&L) trends, and current portfolio holdings.
- **🔔 Notification System**: Delivers critical alerts when breaking news directly impacts a user’s specific holdings and confirms autonomous trade executions.

## 🚀 Getting Started

To get the microservices backend up and running locally, follow these steps:

- Ensure Docker is running
- Setup Environment Variables: Create a `.env` file in the individual directory and configure keys.
- Launch Containers: Run the following command to build and start the services in detached mode `docker compose up -d`
- Access the Server: Once the containers are healthy, the server is available at `http://localhost:8000`
- Refer to Swagger API documentation for the API routes

## 🤝 Acknowledgement

Developed by Mvidia (Team 2), IS484 Project Experience <br />
In Collaboration With UBS.

<a href="https://www.linkedin.com/in/joshydavid/">
  <img src="https://github.com/user-attachments/assets/4dfe0c89-8ced-4e08-bcf3-6261bdbb956d" width="80">
</a> &nbsp;

<a href="https://www.linkedin.com/in/bryancjh/">
  <img src="https://github.com/user-attachments/assets/cc1782b1-e71f-410a-97a4-cfec08bccead" width="80">
</a> &nbsp;

<a href="https://www.linkedin.com/in/derricklkh/">
  <img src="https://github.com/user-attachments/assets/2db4b711-b7d0-4368-8d12-6449c3fa2aa2" width="80">
</a> &nbsp;

<a href="https://www.linkedin.com/in/shawn-ng-yh/">
  <img src="https://github.com/user-attachments/assets/6bd4f3a7-6784-402a-b891-03d91e15d705" width="80">
</a> &nbsp;

<a href="https://www.linkedin.com/in/jiayenbeh/">
  <img src="[https://github.com/user-attachments/assets/6bd4f3a7-6784-402a-b891-03d91e15d705](https://media.licdn.com/dms/image/v2/D5603AQEqWsXbDOKWyw/profile-displayphoto-scale_400_400/B56ZmbOb1OHAAg-/0/1759245877416?e=1770249600&v=beta&t=w4zr9NdTnsOEKuO3Woe02NOv6NVU2hH8FadXhy51Y0s)" width="80">
</a> &nbsp;

<a href="https://www.linkedin.com/in/shawn-ng-yh/">
  <img src="https://github.com/user-attachments/assets/6bd4f3a7-6784-402a-b891-03d91e15d705" width="80">
</a> &nbsp;
