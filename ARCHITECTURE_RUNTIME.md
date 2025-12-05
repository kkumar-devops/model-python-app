# Runtime Architecture: How Python Code is Executed

## Overview

The Clinical AI Prefect service uses **two different runtime mechanisms**:

1. **Flow Server** - Simple HTTP server for direct flow triggering
2. **Prefect Worker** - Process-based worker that executes scheduled flows

## Current Implementation

### 1. Flow Server (`flow_server.py`)

**What it uses**: Python's built-in `http.server.HTTPServer`

```python
from http.server import HTTPServer, BaseHTTPRequestHandler

server = HTTPServer(('0.0.0.0', port), FlowHandler)
server.serve_forever()
```

**Characteristics**:
- ✅ Simple, lightweight
- ✅ No external dependencies
- ❌ **Single-threaded** (handles one request at a time)
- ❌ **Not production-grade** (not suitable for high concurrency)
- ❌ No process management (no worker processes)

**Purpose**: 
- Provides `/trigger` endpoint for manual flow execution
- Provides `/health` endpoint for health checks
- Used by Spring Boot backend for on-demand flow triggering

**Port**: 5000 (configurable via `FLOW_SERVER_PORT`)

### 2. Prefect Worker

**What it uses**: Prefect's process-based worker

```bash
prefect worker start --pool default --type process
```

**Characteristics**:
- ✅ Multi-process execution (can run multiple flows in parallel)
- ✅ Managed by Prefect Server
- ✅ Handles scheduled flows automatically
- ✅ Production-ready for flow execution

**Purpose**:
- Executes flows scheduled via Prefect deployments
- Processes flows from work queues
- Managed by Prefect Server orchestration

### 3. Prefect Server

**What it uses**: **Uvicorn** (ASGI server) internally

```bash
prefect server start --host 0.0.0.0
```

**Characteristics**:
- ✅ Production-grade ASGI server (Uvicorn)
- ✅ Handles API requests
- ✅ Manages deployments and scheduling
- ✅ Provides Prefect UI

**Port**: 4200

## Current Architecture

```
┌─────────────────────────────────────────┐
│         Spring Boot Backend             │
└──────────────┬──────────────────────────┘
               │
               ├─── HTTP ────► Flow Server (port 5000)
               │              [Python http.server]
               │              - Single-threaded
               │              - Direct flow execution
               │
               └─── HTTP ────► Prefect Server (port 4200)
                              [Uvicorn ASGI Server]
                              - Production-grade
                              - API + UI
                              │
                              └─── Manages ────► Prefect Worker
                                                 [Process-based]
                                                 - Multi-process
                                                 - Scheduled flows
```

## Production Considerations

### Current Flow Server Limitations

The `flow_server.py` uses Python's basic `http.server`, which has limitations:

1. **Single-threaded**: Only handles one request at a time
2. **No process management**: No worker processes
3. **No load balancing**: Can't scale horizontally
4. **Not production-grade**: Suitable for low-traffic scenarios only

### Options for Production

#### Option 1: Keep Current Setup (Recommended for Low Traffic)

**Pros**:
- Simple, no additional dependencies
- Works for manual triggers (low frequency)
- Scheduled flows use Prefect Worker (production-ready)

**Cons**:
- Flow Server is single-threaded
- May block if multiple manual triggers occur simultaneously

**When to use**: 
- Low frequency of manual triggers
- Most flows are scheduled (use Prefect Worker)

#### Option 2: Replace with Gunicorn + Flask/FastAPI

**Implementation**:

```python
# flow_server_gunicorn.py (Flask example)
from flask import Flask, request, jsonify
from flows.dlt_pipeline_flow import run_connector_pipeline

app = Flask(__name__)

@app.route('/trigger', methods=['POST'])
def trigger():
    data = request.json
    connector_id = data.get('connector_id')
    result = run_connector_pipeline(connector_id)
    return jsonify({'status': 'success', 'result': result})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

**Dockerfile update**:
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "300", "flow_server_gunicorn:app"]
```

**Pros**:
- ✅ Multi-worker processes
- ✅ Production-grade
- ✅ Handles concurrent requests
- ✅ Configurable worker count

**Cons**:
- Additional dependency (gunicorn)
- More complex setup

#### Option 3: Use Prefect API Only (Remove Flow Server)

**Implementation**:
- Remove `flow_server.py`
- All triggers go through Prefect API
- Backend calls Prefect API to create flow runs

**Pros**:
- ✅ Single entry point
- ✅ All flows managed by Prefect
- ✅ Better observability
- ✅ Production-ready

**Cons**:
- Requires Prefect Server to be available
- Slightly more complex API calls

## Recommendation

### For Current Use Case

**Keep the current setup** because:

1. **Flow Server is for manual triggers only** (low frequency)
2. **Scheduled flows use Prefect Worker** (production-ready, multi-process)
3. **Prefect Server uses Uvicorn** (production-grade ASGI server)
4. **Simple and works** for the current requirements

### If You Need Production-Grade Flow Server

If manual triggers become high-frequency, consider:

1. **Option 2**: Replace with Gunicorn + Flask/FastAPI
2. **Option 3**: Use Prefect API only (remove Flow Server)

## Summary

| Component | Server Type | Production-Ready? | Purpose |
|-----------|-------------|-------------------|---------|
| **Flow Server** | Python `http.server` | ❌ No (single-threaded) | Manual flow triggers |
| **Prefect Server** | Uvicorn (ASGI) | ✅ Yes | API + UI + Orchestration |
| **Prefect Worker** | Process-based | ✅ Yes | Flow execution |

**Current Status**: 
- ✅ Prefect Server/Worker: Production-ready
- ⚠️ Flow Server: Simple HTTP server (suitable for low-traffic manual triggers)

