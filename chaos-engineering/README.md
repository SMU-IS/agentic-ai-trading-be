# Chaos Engineering Suite

This directory contains our Cloud-Native resilience and elasticity validation experiments.

## Prerequisites: Litmus Operator

Before running any experiment, ensure the lightweight Chaos Operator is installed:

```bash
kubectl apply -f https://litmuschaos.github.io/litmus/litmus-operator-v3.0.0.yaml
```

## Available Experiments

### 1. [Pod Failure (Resilience)](./experiments/pod-failure/README.md)

- **Focus**: High Availability & Self-Healing.
- **Metric**: MTTR < 10 seconds.
- **Use Case**: Simulating random server/process crashes.

### 2. [Stress Test (Scaling)](./experiments/stress-test/README.md)

- **Focus**: Elasticity (HPA + Karpenter).
- **Metric**: Automated cluster expansion.
- **Use Case**: Simulating high-traffic market events.

---
