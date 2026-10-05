#!/usr/bin/env python3
"""Quick latency check of the local Ollama server (port of scripts/testOllama.js)."""
import time

import requests

start = time.time()
print('Sending request to Ollama qwen3:8b...')
try:
    res = requests.post('http://localhost:11434/api/generate', timeout=120, json={
        'model': 'qwen3:8b',
        'prompt': 'You are a traffic parser. Convert query "Show speeding cars on Ring Road" into JSON with fields '
                  'vehicleType, overspeedOnly, location, explanation.',
        'format': 'json',
        'stream': False,
        'options': {'temperature': 0.1, 'num_predict': 80},
    })
    print(f'HTTP Status: {res.status_code} in {int((time.time() - start) * 1000)}ms')
    print('Response:\n', res.json().get('response'))
except Exception as err:  # noqa: BLE001
    print(f'Fetch error in {int((time.time() - start) * 1000)}ms:', err)
