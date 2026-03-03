import boto3
import logging
import argparse
from datetime import datetime, timedelta, timezone
import csv


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser()
parser.add_argument("--region", default="us-east-1")
parser.add_argument("--all-regions", action="store_true", help="Check all AWS regions")
parser.add_argument("--output", default="cleanup_report.csv")
args = parser.parse_args()


def get_all_regions(ec2_client):
    response = ec2_client.describe_regions()
    return [region["RegionName"] for region in response["Regions"]]


# ---------------- EC2 ----------------
def find_stopped_instances(ec2_client, days=7):

    logger.info("Checking for stopped EC2 instances...")

    response = ec2_client.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
    )

    stopped_instances = []

    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:

            instance_id = instance["InstanceId"]

            name = "N/A"
            for tag in instance.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]

            state_reason = instance.get("StateTransitionReason", "")
            stop_time = None

            if "(" in state_reason and ")" in state_reason:
                timestamp_str = state_reason.split("(")[1].split(")")[0]

                try:
                    stop_time = datetime.strptime(
                        timestamp_str,
                        "%Y-%m-%d %H:%M:%S GMT"
                    ).replace(tzinfo=timezone.utc)
                except Exception:
                    stop_time = None

            if stop_time:
                age_days = (datetime.now(timezone.utc) - stop_time).days

                if age_days > days:
                    stopped_instances.append({
                        "resource_type": "EC2",
                        "resource_id": instance_id,
                        "name": name,
                        "age_days": age_days,
                        "recommendation": f"Stopped for {age_days} days"
                    })

    return stopped_instances


# ---------------- EBS ----------------
def find_unattached_volumes(ec2_client):

    logger.info("Checking for unattached EBS volumes...")

    response = ec2_client.describe_volumes(
        Filters=[{"Name": "status", "Values": ["available"]}]
    )

    unattached_volumes = []

    for volume in response["Volumes"]:
        volume_id = volume["VolumeId"]
        size_gb = volume["Size"]
        create_time = volume["CreateTime"]

        age_days = (datetime.now(timezone.utc) - create_time).days

        unattached_volumes.append({
            "resource_type": "EBS",
            "resource_id": volume_id,
            "size_gb": size_gb,
            "age_days": age_days,
            "recommendation": f"Volume is unattached; created {age_days} days ago"
        })

    return unattached_volumes


# ---------------- S3 ----------------
def find_old_s3_objects(s3_client, bucket_name, days=90):

    logger.info(f"Checking bucket: {bucket_name}")

    old_objects = []

    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name)

        for page in pages:
            for obj in page.get("Contents", []):

                last_modified = obj["LastModified"]

                age_days = (
                    datetime.now(timezone.utc) - last_modified
                ).days

                if age_days > days:
                    old_objects.append({
                        "resource_type": "S3",
                        "resource_id": f"{bucket_name}/{obj['Key']}",
                        "size_mb": obj["Size"] / 1024 / 1024,
                        "age_days": age_days,
                        "recommendation": f"Object is {age_days} days old"
                    })

    except Exception as e:
        logger.error(f"Error checking bucket {bucket_name}: {e}")

    return old_objects


# ---------------- IAM ----------------
def find_users_without_mfa(iam_client):

    logger.info("Checking IAM Users for MFA...")

    users_without_mfa = []

    try:
        response = iam_client.list_users()

        for user in response["Users"]:
            username = user["UserName"]
            mfa_response = iam_client.list_mfa_devices(UserName=username)

            if len(mfa_response["MFADevices"]) == 0:
                users_without_mfa.append({
                    "resource_type": "IAM User",
                    "resource_id": username,
                    "issue": "MFA not configured",
                    "recommendation": "Please configure MFA"
                })

    except Exception as e:
        logger.error(f"Error while checking for MFA: {e}")

    return users_without_mfa


# ---------------- Cost ----------------
COSTS = {
    "EBS_per_gb": 0.10,
    "S3_per_gb": 0.023,
    "EC2_stopped_estimate": 0.5
}


def estimate_monthly_cost(resource):

    if resource["resource_type"] == "EBS":
        return resource.get("size_gb", 0) * COSTS["EBS_per_gb"]

    elif resource["resource_type"] == "S3":
        size_mb = resource.get("size_mb", 0)
        return (size_mb / 1024) * COSTS["S3_per_gb"]

    elif resource["resource_type"] == "EC2":
        return COSTS["EC2_stopped_estimate"]

    return 0


# ---------------- CSV ----------------
def export_to_csv(results, filename):

    logger.info(f"Exporting results to {filename}")

    if not results:
        logger.info("No issues found")
        return

    all_fields = set()
    for item in results:
        all_fields.update(item.keys())

    fieldnames = list(all_fields)

    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    logger.info(f"Exported {len(results)} findings")


# ---------------- Main ----------------
if __name__ == "__main__":

    if args.all_regions:
        ec2_base = boto3.client("ec2", region_name="us-east-1")
        regions = get_all_regions(ec2_base)
    else:
        regions = [args.region]

    s3 = boto3.client("s3", region_name=args.region)
    iam = boto3.client("iam")

    results = []

    for region in regions:
        logger.info(f"Checking region: {region}")

        ec2 = boto3.client("ec2", region_name=region)
        results.extend(find_stopped_instances(ec2))
        results.extend(find_unattached_volumes(ec2))

    results.extend(find_old_s3_objects(s3, "maniksinghal.com"))
    results.extend(find_users_without_mfa(iam))

    for resource in results:
        resource["estimated_monthly_cost"] = estimate_monthly_cost(resource)

    export_to_csv(results, args.output)

    logger.info("Cleanup report complete")
