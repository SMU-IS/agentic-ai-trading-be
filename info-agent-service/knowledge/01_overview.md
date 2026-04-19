# Agent M - Agentic AI Trading Portfolio

## Project Mission
Agent M is a dynamic, fully autonomous trading companion designed to navigate the complex digital financial landscape. Developed by **Team Mvidia (SMU IS484)** in collaboration with **UBS**, it transforms real-time market sentiment into actionable trade decisions. Our mission is to empower retail investors with the speed, logic, and discipline of institutional trading desks.

## The Core Philosophy: "Trade the Reaction, Not the Story"
Agent M operates on a fundamental principle: news itself is just noise until the market reacts. The system doesn't just read a headline; it analyzes how the price structure (candlesticks, RSI, volume) responds to that catalyst. This allows the agent to distinguish between a high-conviction breakout and a speculative overreaction.

## Core Value Proposition
*   **Mitigate Bias:** Circumbents human emotional triggers like FOMO (Fear of Missing Out) and panic-selling by executing based on deterministic rules and LLM-driven logic.
*   **Information Synthesis:** Processes vast amounts of unstructured data (Yahoo Finance, Reddit, TradingView, X) that are impossible for a human to track in real-time.
*   **Advanced NLP Analysis:** Utilizes specialized models like **FinBERT** for financial sentiment and **spaCy** for precise entity extraction.
*   **Autonomous Execution:** Moves from "Signal" to "Order" in milliseconds, leveraging **Alpaca's low-latency infrastructure** to capture moves before they fade.

## The "No Black Box" Promise
Transparency is our core pillar. Unlike traditional "Black Box" AI trading systems, Agent M provides:
*   **Visible Reasoning:** Every trade includes a detailed "Thesis" explaining the technical and fundamental alignment.
*   **Deterministic Routing:** Signals must pass through a multi-stage risk adjustment layer (Conservative/Aggressive) before reaching the broker.
*   **Audit Trail:** A clear link between the source news article (the "sauce"), the sentiment score, and the final trade execution.
