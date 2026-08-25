#!/usr/bin/env python3
"""
get_solution_metrics.py

Pulls Personalize's own offline evaluation metrics (precision-at-k, mean
reciprocal rank, coverage, normalized discounted cumulative gain) for an
already-trained solution version. These are computed automatically during
training and held-out evaluation -- this script only reads them, it doesn't
trigger any new training or incur any new cost.

Usage:
    python3 get_solution_metrics.py <solution-version-arn>

The ARN was printed at the end of provision_and_validate_personalize.py's
output ("Solution version ARN (save this): ...").
"""

import sys
import boto3

REGION = "us-east-1"
personalize = boto3.client("personalize", region_name=REGION)


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 get_solution_metrics.py <solution-version-arn>")
        sys.exit(1)

    solution_version_arn = sys.argv[1]
    response = personalize.get_solution_metrics(solutionVersionArn=solution_version_arn)
    metrics = response["metrics"]

    print(f"Metrics for solution version:\n  {solution_version_arn}\n")
    for name, value in sorted(metrics.items()):
        print(f"  {name}: {value:.4f}")

    print("""
How to read these:
  - coverage: fraction of the item catalog that ever appears across all
    recommendations. Low coverage (close to 0) can mean the model is
    defaulting to a small set of popular items for everyone -- consistent
    with what we observed manually in the batch inference output.
  - precision_at_k / mean_reciprocal_rank / normalized_discounted_cumulative_gain_at_k:
    measure ranking quality against held-out interactions Personalize set
    aside during training. Near-zero or very low values suggest the model
    isn't confidently distinguishing relevant items from irrelevant ones
    for individual users -- again consistent with a popularity-collapse
    read of the batch inference results.
There's no official "good" threshold published by AWS for these -- they're
comparative (better/worse across solution versions or recipes), not
absolute pass/fail. Still useful as corroborating evidence alongside the
manual batch inference check we already did.
""")


if __name__ == "__main__":
    main()
