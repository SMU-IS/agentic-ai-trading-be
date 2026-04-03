# Frequently Asked Questions (FAQ)

## General Information
### What is Agent M and who is it for?
Agent M is a fully autonomous investment companion for retail investors. it translates financial news and internet sentiment into personalized buy/sell decisions executed via brokerage APIs.

## Practical Usage
### How does the system help retail investors?
It solves information overload. By automatically scraping news and analyzing sentiment, it either answers user queries via a RAG chatbot or executes trades within pre-set risk limits.

## Decision Making
### How does the Trading Agent decide when to buy or sell?
The agent uses a pipeline: Scraped posts are checked for credibility, analyzed via FinBERT for sentiment, and then checked against user-set risk guardrails. Orders are only executed if the weighted sentiment score meets the threshold.

## Reliability
### How do you ensure the accuracy of trade decisions?
We utilize multiple validation rounds, modular scrapers to prevent anti-bot blocking, and RAG-based validation to cross-reference news claims before they reach the execution engine.
