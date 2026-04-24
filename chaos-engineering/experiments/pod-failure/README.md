# Pod Failure Experiment (Resilience & HA)

This experiment simulates a catastrophic pod crash to verify the system's **Self-Healing** and **High Availability** capabilities.

## Goal
Verify that the `trading-service` maintains 100% availability during a pod failure and recovers the infrastructure in < 10 seconds.

## How to Run
1.  **Register the Fault**:
    ```bash
    kubectl apply -f https://raw.githubusercontent.com/litmuschaos/chaos-charts/master/faults/kubernetes/pod-delete/fault.yaml -n default
    ```
2.  **Launch the Experiment**:
    ```bash
    kubectl apply -f experiment.yaml
    ```

## Monitoring & Results
*   **Watch Recovery**: `kubectl get pods -n default -l app.kubernetes.io/instance=trading-service -w`
*   **View Verdict**: `kubectl describe chaosresult trading-service-chaos-pod-delete -n default`

## Key Presentation Points
*   **Verified RTO**: ~8 seconds for full infrastructure recovery (from creation to Ready status).
*   **Zero-Downtime**: 100% service availability via 2-replica HA.
*   **Multi-AZ Resilience**: Replicas are strictly distributed across different Availability Zones (us-east-1a/b) via Hard Anti-Affinity.
*   **Optimized Probes**: Readiness probes tuned to 2s intervals to minimize recovery latency.
