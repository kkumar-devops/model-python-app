#!/usr/bin/env python3
"""
Simple HTTP server to trigger Prefect flows directly.
This allows the backend to trigger flows without needing deployments.
"""
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add flows directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'flows'))

# Import flow with error handling
try:
    from flows.dlt_pipeline_flow import run_connector_pipeline
    FLOW_AVAILABLE = True
    logger.info("Flow module imported successfully")
except Exception as e:
    logger.warning(f"Could not import flow module: {e}. Flow execution will be limited.")
    FLOW_AVAILABLE = False
    def run_connector_pipeline(connector_id):
        return {"status": "error", "message": "Flow module not available"}

class FlowHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/trigger':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                connector_id = data.get('connector_id')
                
                if not connector_id:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'connector_id required'}).encode())
                    return
                
                logger.info(f"Triggering flow for connector {connector_id}")
                
                if not FLOW_AVAILABLE:
                    self.send_response(503)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Flow module not available'}).encode())
                    return
                
                # Execute the flow directly
                # Note: When called directly (not via Prefect API), the flow runs but may not have context
                logger.info(f"Executing flow for connector {connector_id}")
                try:
                    result = run_connector_pipeline(connector_id, prefect_flow_run_id=f"manual-{connector_id}-{int(__import__('time').time())}")
                    logger.info(f"Flow execution completed: {result}")
                except Exception as flow_error:
                    logger.error(f"Flow execution failed: {flow_error}", exc_info=True)
                    raise
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'success',
                    'result': str(result) if result else 'completed'
                }).encode())
            except Exception as e:
                logger.error(f"Error executing flow: {e}", exc_info=True)
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'healthy'}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        logger.info(format % args)

if __name__ == '__main__':
    port = int(os.getenv('FLOW_SERVER_PORT', '5000'))
    server = HTTPServer(('0.0.0.0', port), FlowHandler)
    logger.info(f"Flow server starting on port {port}")
    server.serve_forever()

