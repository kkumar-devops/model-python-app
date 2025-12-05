#!/usr/bin/env python3
"""
Script to deploy the Prefect flow for manual execution.
This allows the flow to be triggered via Prefect API.
"""
import os
import sys

# Add flows directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'flows'))

from prefect import serve
from flows.dlt_pipeline_flow import run_connector_pipeline

if __name__ == "__main__":
    # Deploy the flow so it can be triggered via API
    # This creates a deployment that can be run manually
    run_connector_pipeline.serve(
        name="run_connector_pipeline",
        parameters={"connector_id": 0},  # Placeholder, will be overridden
    )

