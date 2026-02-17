#!/usr/bin/env python3
"""Directly test the health endpoint"""
import sys
sys.path.insert(0, '.')

from dashboard_unified import app

# Test the endpoint directly
with app.test_client() as client:
    response = client.get('/api/health')
    print(f"Status Code: {response.status_code}")
    print(f"Response:")
    import json
    print(json.dumps(response.get_json(), indent=2))
