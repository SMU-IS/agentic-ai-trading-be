<p align="center">
  <img src="https://img.shields.io/github/issues/SMU-IS/agentic-ai-trading-be" alt="Issue">
  <img src="https://img.shields.io/github/issues-pr/SMU-IS/agentic-ai-trading-be" alt="Pull Request">
  <img src="https://img.shields.io/github/v/release/SMU-IS/agentic-ai-trading-be" alt="Release Badge">
</p>

<p align="center">
  <img width="220" height="204" alt="agent" src="https://github.com/user-attachments/assets/82d27a27-f71c-42ac-bf51-5b1a83893e6a" />
</p>

## 🤖 Agentic AI Trading Portfolio Backend X

A dynamic, fully autonomous trading portfolio companion designed to navigate the complex digital financial landscape. Leveraging a multi-agent AI architecture, the platform transforms real-time market data, traditional news, and internet sentiment into personalised, actionable investment decisions.

The system operates on behalf of users to mitigate information overload and circumvent human emotional bias, executing optimised buy or sell orders via external brokerage APIs within user-defined risk guardrails

## 👨‍💻 Tech Stack

- [🐹 Gin (Golang)](https://gin-gonic.com/en/)
- [🐘 PostgreSQL ](https://postgresql.org)
- [☁️ Amazon Web Services](https://aws.amazon.com)

## 🚀 Getting Started

To get the microservices backend up and running locally, follow these steps:

- Ensure Docker is running.
- Setup Environment Variables: Create a `.env` file in the individual directory and configure keys.
- Launch Containers: Run the following command to build and start the services in detached mode `docker compose up -d`
- Access the Server: Once the containers are healthy, the server is available at `http://localhost:8000`
- Refer to Swagger API documentation for the API routes.

## 📁 API Documentation

- http://localhost:8000/api/v1/user/docs/index.html
