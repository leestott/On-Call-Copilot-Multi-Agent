"""Fetch container logs for a hosted agent.

Usage:
    python scripts/get_logs.py

Required environment variables:
    AZURE_AI_PROJECT_ENDPOINT  – e.g. https://<account>.services.ai.azure.com/api/projects/<project>

Optional:
    AGENT_NAME     – defaults to oncall-copilot
    AGENT_VERSION  – defaults to latest
"""
import os
import subprocess
import sys

import requests


def get_token() -> str:
    result = subprocess.run(
        ['az', 'account', 'get-access-token', '--resource', 'https://ai.azure.com',
         '--query', 'accessToken', '-o', 'tsv'],
        capture_output=True, text=True, shell=True,
    )
    if result.returncode != 0:
        print(f"ERROR: az login required: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()


project_endpoint = os.environ.get('AZURE_AI_PROJECT_ENDPOINT', '').rstrip('/')
if not project_endpoint:
    print('ERROR: AZURE_AI_PROJECT_ENDPOINT env var is required.')
    print('  e.g. https://<account>.services.ai.azure.com/api/projects/<project>')
    sys.exit(1)

agent = os.environ.get('AGENT_NAME', 'oncall-copilot')
version = os.environ.get('AGENT_VERSION', 'latest')

token = get_token()
headers = {'Authorization': f'Bearer {token}'}

for kind in ['console', 'system']:
    print(f'\n{"="*60}')
    print(f'=== {kind.upper()} LOGS ===')
    print(f'{"="*60}')
    url = (f'{project_endpoint}/agents/{agent}/versions/{version}/containers'
           f'/default:logstream?kind={kind}&tail=300&api-version=2025-11-15-preview')
    r = requests.get(url, headers=headers, timeout=30)
    print(f'Status: {r.status_code}')
    print(r.text[:5000] if r.text else '<empty>')
