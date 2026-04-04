# Frequently Asked Questions (FAQ)

## General Information
### What is Agent M and who is it for?
Agent M is a fully autonomous investment companion for retail investors. it translates financial news and internet sentiment into personalized buy/sell decisions executed via the **Alpaca Brokerage API**.

## Practical Usage
### How does the system help retail investors?
It solves information overload. By automatically scraping news and analyzing sentiment, it either answers user queries via a RAG chatbot or executes trades within pre-set risk limits.

## Decision Making
### How does the Trading Agent decide when to buy or sell?
The agent uses a pipeline: Scraped posts are checked for credibility, analyzed via FinBERT for sentiment, and then checked against user-set risk guardrails. Orders are only executed if the weighted sentiment score meets the threshold.

## Interactive Features
### Do I need an order ID to ask why a trade was made?
No. You can ask naturally, like "Why did you sell GOOGL last week?" Agent M will automatically search your last 30 days for matching trades and ask for clarification if multiple matches are found. You can even refer to items in a list, like "the first one."

## Reliability
### How do you ensure the accuracy of trade decisions?
We utilize multiple validation rounds, modular scrapers to prevent anti-bot blocking, and RAG-based validation to cross-reference news claims before they reach the execution engine.
