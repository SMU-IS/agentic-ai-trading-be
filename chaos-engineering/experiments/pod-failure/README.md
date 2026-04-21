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
*   **MTTR**: ~9 seconds for infrastructure recovery.
*   **Zero-Downtime**: 100% service availability via 2-replica HA.
*   **Anti-Affinity**: Proved that replicas are distributed across different nodes.
