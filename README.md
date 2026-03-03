# AWS Multi-Region Cost Audit & Governance Tool

AWS automation tool for auditing unused infrastructure and estimating potential cloud waste.

Provides a lightweight governance utility to identify cost leakage and basic security gaps in AWS environments.

---

## What It Does

Scans AWS accounts across EC2, EBS, S3, and IAM to identify:
- EC2 instances stopped beyond configurable threshold (default: 7 days)
- Unattached EBS volumes
- S3 objects older than configurable threshold (default: 90 days)
- IAM users without MFA

Outputs structured CSV with cost estimates.

---

## Usage

**Single region:**
```bash
python aws_cleanup_report.py --region us-east-1 --output report.csv
```

**All regions:**
```bash
python aws_cleanup_report.py --all-regions --output full_report.csv
```

Requires AWS credentials via `aws configure` or environment variables.

---

## Output Format

CSV with dynamic schema (columns depend on resource type):
```
resource_type,resource_id,age_days,size_gb,estimated_monthly_cost,recommendation
EC2,i-abc123,45,,,0.50,"Stopped for 45 days"
EBS,vol-xyz789,120,100,10.00,"Delete - 120 days old"
S3,bucket/file.txt,180,,0.0056,"Object is 180 days old"
IAM User,john.doe,,,,0,"MFA not configured"
```

---

## Technical Implementation

**EC2:** Parses `StateTransitionReason` to extract stop time and calculate days stopped

**EBS:** Queries volumes with status "available" and calculates age from `CreateTime`

**S3:** Uses boto3 paginator for `list_objects_v2` to handle large buckets (1000+ objects)

**IAM:** Loops through users and checks for attached MFA devices

**Multi-region:** Iterates across AWS regions and instantiates region-specific EC2 clients; S3/IAM are global

**Cost estimation:** Hardcoded rates for demonstration (EBS: $0.10/GB, S3: $0.023/GB, EC2: $0.50)

**Error handling:** Implements fail-soft pattern — logs API errors and continues execution to prevent partial service failure from breaking the entire audit

**Schema aggregation:** Dynamic CSV fieldnames using set operations to handle heterogeneous data

---

## Limitations & Scope

**Current scope:**
- S3 bucket name hardcoded (line 208) - can be converted to CLI flag
- Cost rates are approximations, not real-time AWS Pricing API
- No pagination for EC2/EBS (assumes <1000 resources per region)
- EC2 stop time parsing depends on AWS StateTransitionReason format
- No retry/backoff for API throttling
- Age thresholds parameterized within functions (default: EC2 7 days, S3 90 days)

**Not included:**
- RDS, Lambda, or other services
- EBS snapshots
- Reserved instances or savings plans
- Slack/email notifications

For production cost management, use AWS Cost Explorer, Trusted Advisor, or Cloud Custodian.

---

## Engineering Focus

This project demonstrates:
- Multi-service AWS automation using boto3
- Cross-region orchestration
- Pagination handling for large datasets
- Time-based filtering with timezone-safe logic
- Dynamic schema aggregation for heterogeneous resources
- Cost estimation modeling
- Fail-soft error handling patterns

---

## Technical Highlights

- **Pagination:** Handles S3 buckets with 1000+ objects using `get_paginator`
- **Timezone-safe datetime handling:** Uses datetime.now(timezone.utc) to avoid naive/aware datetime issues
- **Dynamic schemas:** Aggregates different resource types with varying fields into single CSV
- **Multi-region:** Iterates across regions with region-specific clients
- **Defensive coding:** Safe key access with `.get()`, empty list defaults, try/except wrappers
- **Configurable thresholds:** Age filters parameterized via function arguments

---

## Possible Extensions

- Add `--bucket` and `--days` CLI flags for runtime configuration
- Integrate AWS Pricing API for real-time cost calculation
- Add exponential backoff for API throttling
- Deploy as Lambda with EventBridge schedule
- Push results to Slack/SNS
- Add tagging compliance checks
- Support for additional services (RDS, Lambda, ELB)

---

## Repository Structure
```
aws-multi-region-cost-audit/
│
├── aws_cleanup_report.py
├── README.md
├── requirements.txt
└── sample_output/
    └── sample_cleanup_report.csv
```

---

## Requirements
```bash
pip install boto3
```

Python 3.8+

**IAM permissions needed:**
- ec2:DescribeInstances, ec2:DescribeVolumes, ec2:DescribeRegions
- s3:ListBucket, s3:ListObjects
- iam:ListUsers, iam:ListMFADevices

