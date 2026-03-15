# Infrastructure Cost Estimation & Optimization Report

## 1. Executive Summary
This report provides a granular cost breakdown for the `agentic-ai-trading-be` project infrastructure. The environment is configured for maximum cost-efficiency while maintaining functional parity for development and testing using professional AWS service architectures.

---

## 2. Infrastructure Cost Breakdown (USD)

| AWS Service | Monthly Est. | Daily Est. | Hourly Est. | Technical Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Amazon EKS Control Plane** | $73.00 | $2.43 | $0.10 | Fixed cluster management fee; non-scalable. |
| **Amazon EC2 Spot Instances** | ~$12.00 | ~$0.40 | ~$0.016 | 1x `t4g.small` (system) + scaling `t4g.micro/small` (apps) via Karpenter. |
| **Amazon RDS (PostgreSQL)** | ~$13.90 | ~$0.46 | ~$0.02 | `db.t4g.micro` + 20GB gp3; Graviton-based instance. |
| **AWS Amplify + CloudFront** | < $2.00 | < $0.06 | < $0.002 | Frontend hosting + manual CDN; includes data transfer. |
| **Amazon Application Load Balancer** | ~$18.00 | ~$0.60 | ~$0.025 | Single ALB for all 11 microservices using path-based routing. |
| **Amazon S3 & Amazon ECR** | < $0.50 | < $0.02 | < $0.01 | Combined storage costs after lifecycle pruning. |
| **TOTAL** | **~$119.40** | **~$3.98** | **~$0.17** | |

---

## 3. Deployment Notes & Constraints

### 3.1 Availability & Reliability
- **Amazon EC2 Spot Risk:** Compute nodes use Spot capacity. While cost-effective, these instances can be terminated with a 2-minute notice if AWS requires the capacity.
- **Public Subnet Architecture:** To eliminate NAT Gateway costs ($32/mo) and NAT Instance management, nodes are deployed in public subnets. Security is maintained via strict Security Group rules.
- **Multi-AZ Configuration:** EKS and RDS are configured for Multi-AZ (`us-east-1a` and `us-east-1b`) as required by AWS, though the workload is minimized for cost.

### 3.2 Performance
- **Architecture:** Compute nodes utilize Graviton (`t4g` class) for optimal cost/performance. Ensure Docker images are built for `linux/arm64`.
- **Memory Overhead:** The app NodePool includes `t4g.small` (2GiB RAM) to accommodate Python-based microservices that exceed the memory limits of `t4g.micro`.
- **Amazon EBS gp3 Storage:** The database uses the latest generation storage, providing a baseline of 3,000 IOPS regardless of volume size.

### 3.3 Scalability
- **Karpenter:** The cluster is configured to automatically scale Amazon EC2 instances based on pod requirements. Both `t4g.micro` and `t4g.small` are available to ensure pods find a fit regardless of size.
- **Traffic Spikes:** Heavy data transfer through Amazon CloudFront or the Amazon Network Load Balancer beyond the free tier thresholds will result in incremental charges.

---

## 4. Operational Recommendations
- **Off-Hours Shutdown:** For further savings, scale EKS deployments to 0 replicas during non-development hours to trigger Karpenter to terminate the Amazon EC2 instances.
- **AWS Budgets:** Configure AWS Budgets to send SNS or Email notifications when actual costs exceed 80% ($100.00) of the $125.00 monthly threshold.

---
*Report updated: March 15, 2026*
