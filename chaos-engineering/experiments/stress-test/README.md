# CPU Stress Test (HPA & Karpenter Scaling)

This experiment simulates a high-load scenario to verify the cluster's **Elasticity** and **Automated Scaling**.

## Goal
Trigger the Horizontal Pod Autoscaler (HPA) and Karpenter Node Provisioner to verify that the cluster can "scale-out" automatically under load.

## How to Run
1.  **Register the Fault**:
    ```bash
    kubectl apply -f https://raw.githubusercontent.com/litmuschaos/chaos-charts/master/faults/kubernetes/pod-cpu-hog/fault.yaml -n default
    ```
2.  **Launch the Stress Test**:
    ```bash
    kubectl apply -f experiment.yaml
    ```

## Monitoring the "Scaling Chain"
While the test runs (5 mins):
*   **HPA Status**: `kubectl get hpa -w` (Watch CPU utilization pass 70%).
*   **Pod Expansion**: `kubectl get pods -l app.kubernetes.io/instance=trading-service` (Watch replicas scale from 2 to 5).
*   **Node Scaling**: `kubectl get nodes -w` (Watch Karpenter provision a new EC2 instance to handle the load).

## Key Presentation Points
*   **Elasticity**: Cluster dynamically grows based on real-time demand.
*   **Karpenter**: Just-in-time node provisioning reduces cost and increases agility.
*   **Infrastructure-as-Code**: Scaling policies are defined in Terraform and verified by Chaos.
