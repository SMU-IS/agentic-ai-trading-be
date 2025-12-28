![Issue](https://img.shields.io/github/issues/SMU-IS/agentic-ai-trading-be)
![Pull Request](https://img.shields.io/github/issues-pr/SMU-IS/agentic-ai-trading-be)
![Release Badge](https://img.shields.io/github/v/release/SMU-IS/agentic-ai-trading-be)

## 🤖 User Module

Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged. It was popularised in the 1960s with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desktop publishing software like Aldus PageMaker including versions of Lorem Ipsum.

## ⚙️ System Architecture

- Lorem Ipsum is simply dummy text of the printing and typesetting industry.
- Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book.
- It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged.
- It was popularised in the 1960s with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desktop publishing software like Aldus PageMaker including versions of Lorem Ipsum.

## 🚀 Features

- Lorem Ipsum is simply dummy text of the printing and typesetting industry.
- Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book.
- It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged.
- It was popularised in the 1960s with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desktop publishing software like Aldus PageMaker including versions of Lorem Ipsum.

## 👨‍💻 Tech Stack

- [Gin, Golang](https://gin-gonic.com)
- [PostgreSQL](https://www.postgresql.org)
- [Amazon Web Services](https://aws.amazon.com)

## 💨 Getting Started

To get the Agentic AI Trading backend up and running locally, follow these steps:
- Ensure Docker is running
- Setup Environment Variables: Create a .env file in the root directory and configure your keys (Gemini API, Qdrant host, etc.). Ensure QDRANT_HOST is set to qdrant for container networking.
- Launch Containers: Run the following command to build and start the services in detached mode:

  ```
  docker compose up -d
  ```
- Access the Server: Once the containers are healthy, the server is available at `http://localhost:8000`
- Verify Development Mode: The backend is configured with fastapi dev, so any changes you save to your local code will automatically trigger a hot-reload inside the container.

## 📁 API Documentation

- http://localhost:8000/api/v1/user/docs/index.html
