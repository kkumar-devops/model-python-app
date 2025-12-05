# Flow Server Backup

This directory contains backup files for the Flow Server implementation that was removed in favor of using Prefect API for manual flow triggers.

## Files

- `flow_server.py` - Original Flow Server implementation (Python http.server)

## Why It Was Removed

The Flow Server was replaced with Prefect API for manual flow triggers because:

1. **Production-Grade**: Prefect API uses Uvicorn (ASGI server) vs. Python's basic http.server
2. **Full Orchestration**: Flows are properly tracked and visible in Prefect UI
3. **Better Observability**: Flow runs are tracked with full context
4. **Consistency**: All flows (scheduled and manual) go through Prefect
5. **No Additional Service**: One less service to maintain

## When to Restore

You might want to restore the Flow Server if:

- You need to trigger flows without Prefect deployments
- Prefect Server is unavailable and you need a fallback
- You're in a development/testing scenario where Prefect Server isn't running

## How to Restore

1. Copy `flow_server.py` back to the root directory
2. Update `Dockerfile` to start the Flow Server:
   ```dockerfile
   CMD ["/bin/sh", "-c", "nohup python flow_server.py > /tmp/flow_server.log 2>&1 & sleep 2 && exec prefect worker start --pool default --type process"]
   ```
3. Update Kubernetes deployments to expose port 5000
4. Update health checks to use port 5000
5. Update backend `PrefectService.triggerManualRun()` to use Flow Server URL

## Current Implementation

Manual triggers now use Prefect API:
- Endpoint: `POST /api/deployments/{deployment_id}/create_flow_run`
- Requires: Deployment ID from connector
- Returns: Flow run ID for tracking

See `MANUAL_TRIGGER_OPTIONS.md` for details.

