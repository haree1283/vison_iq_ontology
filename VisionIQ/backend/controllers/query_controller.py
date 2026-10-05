import json
import os
import re
import time

import requests
from flask import jsonify, request

OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')
DEFAULT_MODEL = os.getenv('OLLAMA_MODEL') or 'qwen2.5:1.5b'

ollama_cache = {'online': False, 'checkedAt': 0.0, 'models': []}
OLLAMA_CHECK_INTERVAL = 15.0  # 15s cache

PREFERRED_FAST_MODELS = [
    'qwen2.5:1.5b',
    'qwen2.5:0.5b',
    'llama3.2:1b',
    'llama3.2:3b',
    'qwen2.5:3b',
    'qwen3:8b',
]


def _js_num_str(value):
    """String(number) as JavaScript prints it (80, not 80.0)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_ollama_online():
    now = time.time()
    if now - ollama_cache['checkedAt'] < OLLAMA_CHECK_INTERVAL:
        return ollama_cache['online']
    try:
        response = requests.get(f'{OLLAMA_HOST}/api/tags', timeout=0.8)
        data = response.json() if response.ok else None
        models = [m.get('name') for m in (data or {}).get('models', [])]
        ollama_cache.update(online=response.ok, checkedAt=now, models=models)
        return response.ok
    except Exception:  # noqa: BLE001
        ollama_cache.update(online=False, checkedAt=now, models=[])
        return False


def select_best_model(installed_models=()):
    custom_name = os.getenv('OLLAMA_MODEL')
    if custom_name:
        custom = next((m for m in installed_models if m == custom_name or m.startswith(custom_name)), None)
        if custom:
            return custom
    for pref in PREFERRED_FAST_MODELS:
        match = next((m for m in installed_models if m == pref or m.startswith(pref.split(':')[0])), None)
        if match:
            return match
    return installed_models[0] if installed_models else DEFAULT_MODEL


def _has(q, *words):
    return any(w in q for w in words)


# Robust, comprehensive rule parser for natural language traffic queries
def fallback_rule_parser(query, facets=None):
    facets = facets or {}
    q = str(query or '').lower().strip()
    filters = {
        'vehicleType': None,
        'vehicleTypes': [],
        'minSpeed': None,
        'maxSpeed': None,
        'overspeedOnly': None,
        'location': None,
        'camera': None,
        'signalState': None,
        'weather': None,
        'plateSearch': None,
        'sortBy': 'timestamp-desc',
        'explanation': f'Natural query: "{query}"',
    }

    # Overspeed & Reckless Driving
    if _has(q, 'overspeed', 'speeding', 'violation', 'violator', 'fast', 'over speed', 'rash', 'reckless',
            'dangerously', 'challan', 'over limit', 'flying'):
        filters['overspeedOnly'] = True

    # Speed ranges (e.g. "between 40 and 70", "from 50 to 80")
    speed_range = re.search(r'(?:between|from)\s*(\d+)\s*(?:and|to|-)\s*(\d+)', q, re.I)
    if speed_range:
        filters['minSpeed'] = int(speed_range.group(1))
        filters['maxSpeed'] = int(speed_range.group(2))
    else:
        speed_min = re.search(
            r'(?:speed\s*(?:>|>=|above|over|exceeding|faster than|greater than|more than|higher than|of)?\s*'
            r'|>|>=|above|over|faster than|greater than|more than|exceeding)\s*(\d+)', q, re.I)
        if speed_min:
            filters['minSpeed'] = int(speed_min.group(1))
        speed_max = re.search(
            r'(?:speed\s*(?:<|<=|under|below|slower than|less than|lower than)\s*'
            r'|<|<=|under|below|slower than|less than|lower than)\s*(\d+)', q, re.I)
        if speed_max:
            filters['maxSpeed'] = int(speed_max.group(1))

    # Multi-vehicle types detection with broad category groupings
    detected = []
    type_patterns = [
        ('Car', r'\b(?:car|cars|sedan|suv|hatchback|cab|taxi|four[- ]?wheelers?|4[- ]?wheelers?)\b'),
        ('Bike', r'\b(?:bike|bikes|motorcycle|motorcycles|scooter|scooters|two[- ]?wheelers?|2[- ]?wheelers?'
                 r'|cycle|cycles|bicycle|bicycles|moped)\b'),
        ('Bus', r'\b(?:bus|buses|minibus|coach)\b'),
        ('Truck', r'\b(?:truck|trucks|lorry|lorries|trailer|trailers|heavy|dumper|tipper)\b'),
        ('Auto', r'\b(?:auto|autos|rickshaw|rickshaws|auto[- ]?rickshaws?|autorickshaw|autorickshaws'
                 r'|3[- ]?wheelers?|three[- ]?wheelers?|tuktuk)\b'),
        ('Tractor', r'\b(?:tractor|tractors)\b'),
        ('Jeep', r'\b(?:jeep|jeeps|4x4|thar)\b'),
        ('Pedestrian', r'\b(?:pedestrian|pedestrians|walking|people|person|edisetrain|edisetrains)\b'),
        ('Van', r'\b(?:van|vans|omni|eeco)\b'),
        ('Ambulance', r'\b(?:ambulance|ambulances|emergency)\b'),
        ('Train', r'\b(?:train|trains|metro|rail|tram)\b'),
    ]
    for name, pattern in type_patterns:
        if re.search(pattern, q, re.I):
            detected.append(name)

    if re.search(r'\bheavy(?:\s+vehicles?|\s+transport)?\b', q, re.I):
        for t in ('Truck', 'Bus'):
            if t not in detected:
                detected.append(t)
    if re.search(r'\bcommercial(?:\s+vehicles?|\s+transport)?\b', q, re.I):
        for t in ('Truck', 'Bus', 'Auto'):
            if t not in detected:
                detected.append(t)

    filters['vehicleTypes'] = detected
    filters['vehicleType'] = detected[0] if len(detected) == 1 else (detected if len(detected) > 1 else None)

    # Signals & Red Light Jumping
    if (_has(q, 'red light', 'red signal', 'ran red', 'jumped red', 'crossed red', 'signal jump', 'signal violation')
            or re.search(r'\bred\b', q, re.I)):
        filters['signalState'] = 'Red'
    elif _has(q, 'green signal', 'green light') or re.search(r'\bgreen\b', q, re.I):
        filters['signalState'] = 'Green'
    elif _has(q, 'yellow', 'amber'):
        filters['signalState'] = 'Yellow'

    # Weather
    if _has(q, 'rain', 'rainy', 'raining', 'monsoon', 'wet'):
        filters['weather'] = 'Rainy'
    elif _has(q, 'fog', 'foggy', 'mist', 'misty', 'smog'):
        filters['weather'] = 'Foggy'
    elif _has(q, 'clear', 'sunny'):
        filters['weather'] = 'Clear'

    # Camera matching
    ignore_cam_words = {'detections', 'records', 'view', 'network', 'graph', 'feed', 's', 'all', 'any'}
    cameras = facets.get('cameras')
    if isinstance(cameras, list):
        q_norm = re.sub(r'[^a-z0-9]', '', q)
        for cam in cameras:
            cam_norm = re.sub(r'[^a-z0-9]', '', str(cam).lower())
            if cam_norm in q_norm:
                filters['camera'] = cam
                break
    if not filters['camera']:
        cam_match = re.search(r'\bcam(?:era)?[-_\s]*(\d+|0[1-9])\b', q, re.I)
        if cam_match and cam_match.group(1).lower() not in ignore_cam_words:
            num = cam_match.group(1)
            filters['camera'] = f'CAM-0{num}' if len(num) == 1 else f'CAM-{num}'

    # Location matching from facets
    generic_loc_words = {'road', 'main', 'city', 'street', 'junction', 'lane', 'blvd', 'highway', 'crossing',
                         'expressway', 'traffic', 'zone', 'area', 'circle', 'bypass', 'way', 'north', 'south',
                         'east', 'west'}
    locations = facets.get('locations')
    if isinstance(locations, list):
        for loc in locations:
            loc_lower = str(loc).lower()
            if loc_lower in q:
                filters['location'] = loc
                break
            words = [w for w in re.split(r'[\s\-_]+', loc_lower) if len(w) > 3 and w not in generic_loc_words]
            if words and any(w in q for w in words):
                filters['location'] = loc
                break

    # Plate matching pattern: e.g. "TS09AB1234", "TS 09 AB 1234", "MH-12-DE-1433"
    plate = re.search(r'\b([a-z]{2}\s*[-]?\s*[0-9]{1,2}\s*[-]?\s*[a-z]{0,3}\s*[-]?\s*[0-9]{1,4})\b', q, re.I)
    if plate and len(re.sub(r'[^a-z0-9]', '', plate.group(1), flags=re.I)) >= 4:
        filters['plateSearch'] = re.sub(r'[\s-]', '', plate.group(1)).upper()

    # Sort & superlatives
    if _has(q, 'fastest', 'highest speed', 'top speed', 'maximum speed'):
        filters['sortBy'] = 'speed-desc'
    elif _has(q, 'slowest', 'lowest speed', 'traffic jam', 'crawl'):
        filters['sortBy'] = 'speed-asc'
    elif _has(q, 'highest confidence', 'most confident', 'clear plate'):
        filters['sortBy'] = 'confidence-desc'
    elif _has(q, 'lowest confidence', 'least confident', 'blurred', 'unclear'):
        filters['sortBy'] = 'confidence-asc'
    elif _has(q, 'latest', 'recent', 'newest'):
        filters['sortBy'] = 'timestamp-desc'
    elif _has(q, 'earliest', 'oldest'):
        filters['sortBy'] = 'timestamp-asc'

    parts = []
    if filters['vehicleTypes']:
        parts.append(f"Vehicle Type: {', '.join(filters['vehicleTypes'])}")
    elif filters['vehicleType']:
        parts.append(f"Vehicle Type: {filters['vehicleType']}")
    if filters['overspeedOnly']:
        parts.append('Over Speed: Yes')
    if filters['minSpeed'] and filters['maxSpeed']:
        parts.append(f"Speed: {filters['minSpeed']} - {filters['maxSpeed']} km/h")
    elif filters['minSpeed']:
        parts.append(f"Speed > {filters['minSpeed']} km/h")
    elif filters['maxSpeed']:
        parts.append(f"Speed < {filters['maxSpeed']} km/h")
    if filters['location']:
        parts.append(f"Road: {filters['location']}")
    if filters['camera']:
        parts.append(f"Camera: {filters['camera']}")
    if filters['signalState']:
        parts.append(f"Signal: {filters['signalState']}")
    if filters['weather']:
        parts.append(f"Weather: {filters['weather']}")
    if filters['plateSearch']:
        parts.append(f"Plate: {filters['plateSearch']}")

    filters['explanation'] = (f"Filtered telemetry graph segment for {', '.join(parts)}" if parts
                              else f'Retrieved telemetry graph segment matching "{query}"')
    return filters


# 1. Check Ollama server connectivity & model status
def check_ollama_status():
    try:
        response = requests.get(f'{OLLAMA_HOST}/api/tags', timeout=4)
    except Exception as error:  # noqa: BLE001
        return jsonify(connected=False, host=OLLAMA_HOST, model=DEFAULT_MODEL,
                       message=f'Could not connect to Ollama at {OLLAMA_HOST} ({error})')
    if not response.ok:
        return jsonify(connected=False, host=OLLAMA_HOST, model=DEFAULT_MODEL,
                       message=f'Ollama responded with HTTP {response.status_code}')
    models = [m.get('name') for m in (response.json() or {}).get('models', [])]
    active_model = select_best_model(models)
    return jsonify(connected=True, host=OLLAMA_HOST, targetModel=active_model, modelAvailable=bool(active_model),
                   installedModels=models, message=f'Ollama connected with high-speed model {active_model} ready.')


def _normalize_type(t):
    v = str(t or '').strip().lower()
    if v.startswith('car') or v in ('sedan', 'suv'):
        return 'Car'
    if v.startswith(('bike', 'motorcycle', 'scooter', 'cycle', 'two wheeler')):
        return 'Bike'
    if v.startswith('bus'):
        return 'Bus'
    if v.startswith(('truck', 'lorry', 'trailer')):
        return 'Truck'
    if v.startswith(('auto', 'rickshaw')):
        return 'Auto'
    if v.startswith('tractor'):
        return 'Tractor'
    if v.startswith('jeep'):
        return 'Jeep'
    if v.startswith(('pedestrian', 'walking')):
        return 'Pedestrian'
    if v.startswith('van'):
        return 'Van'
    if v.startswith(('train', 'metro')):
        return 'Train'
    return str(t).strip()


# 2. Parse natural language traffic query into structured filters using the local Ollama model
def parse_natural_language_query():
    body = request.get_json(silent=True) or {}
    query = body.get('query')
    facets = body.get('facets') or {}

    if not isinstance(query, str) or not query.strip():
        return jsonify(success=False, message='Query string is required.'), 400

    clean_query = query.strip()

    # Fast check: If Ollama is offline or unreachable, instantly return the rule parser result
    if not is_ollama_online():
        fb = fallback_rule_parser(clean_query, facets)
        return jsonify(success=True, aiSource='rule-fallback', filters=fb, explanation=fb['explanation'],
                       rawQuery=clean_query)

    active_model = select_best_model(ollama_cache['models'])
    known_locations = ', '.join(facets.get('locations', [])[:10]) if facets.get('locations') \
        else 'Ring Road, Main Junction, Highway 4, MG Road'
    known_cameras = ', '.join(facets.get('cameras', [])[:8]) if facets.get('cameras') else 'CAM-01, CAM-02, CAM-03'

    prompt = f'''You are a high-speed traffic intelligence parser. Convert natural language queries into structured JSON filters.
Available Vehicle Types: Car, Bus, Truck, Bike, Auto, Tractor, Jeep, Van, Pedestrian

Rules:
1. "vehicleTypes": Array of strings from available types (e.g. ["Bike", "Auto"]) or null if all vehicle types apply (e.g. "all vehicles", "speeding cars and bikes", "violators at junction").
   - "two-wheelers", "motorcycles", "bikes", "scooters" -> ["Bike"]
   - "three-wheelers", "auto rickshaws", "autos" -> ["Auto"]
   - "heavy vehicles", "commercial transport" -> ["Truck", "Bus"]
   - "four-wheelers" -> ["Car", "Jeep", "Van"]
   - If user doesn't specify a type (e.g. "which vehicles are speeding"), use null.
2. "overspeedOnly": true if query mentions speeding, rash, fast, reckless, violators, over limit. Otherwise null.
3. "minSpeed": number (e.g. "above 80" -> 80, "> 70" -> 70). Otherwise null.
4. "maxSpeed": number (e.g. "under 40" -> 40, "< 50" -> 50). Otherwise null.
5. "signalState": "Red" if jumped signal or red light violation; "Green" or "Yellow" if mentioned; else null.
6. "weather": "Rainy" (rain, monsoon, wet), "Foggy" (mist, fog, low visibility), "Clear" (sunny, clear); else null.
7. "location": matching road name from ({known_locations}) or null.
8. "camera": matching camera ID from ({known_cameras}) or null.
9. "plateSearch": plate substring or null.
10. "sortBy": "speed-desc" (fastest/speeding), "speed-asc" (slowest), "confidence-asc" (unclear/low confidence), "confidence-desc" (clear/high confidence), "timestamp-desc" (latest/recent).
11. "explanation": 1 concise sentence describing the telemetry segment found.

Query: "{clean_query}"
Return ONLY valid JSON:'''

    try:
        response = requests.post(f'{OLLAMA_HOST}/api/generate', timeout=15, json={
            'model': active_model,
            'prompt': prompt,
            'format': 'json',
            'stream': False,
            'keep_alive': '2h',
            'options': {'temperature': 0.1, 'num_predict': 120, 'num_thread': 8},
        })
        if not response.ok:
            raise RuntimeError(f'Ollama HTTP error {response.status_code}')

        raw_text = str((response.json() or {}).get('response') or '').strip()
        raw_text = re.sub(r'<think>[\s\S]*?</think>', '', raw_text, flags=re.I).strip()
        raw_text = re.sub(r'\s*```$', '', re.sub(r'^```(?:json)?\s*', '', raw_text, flags=re.I), flags=re.I).strip()
        try:
            parsed = json.loads(raw_text)
        except ValueError:
            match = re.search(r'\{[\s\S]*\}', raw_text)
            if not match:
                raise RuntimeError('Could not parse JSON from model output')
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise RuntimeError('Model output is not a JSON object')

        raw_types = []
        if isinstance(parsed.get('vehicleTypes'), list):
            raw_types += parsed['vehicleTypes']
        if isinstance(parsed.get('vehicleType'), list):
            raw_types += parsed['vehicleType']
        elif isinstance(parsed.get('vehicleType'), str):
            raw_types.append(parsed['vehicleType'])
        normalized = list(dict.fromkeys(t for t in (_normalize_type(t) for t in raw_types) if t))

        final_type = normalized[0] if len(normalized) == 1 else (normalized if len(normalized) > 1 else None)
        is_overspeed = parsed.get('overspeedOnly') in (True, 'true', 'Yes')

        fb = fallback_rule_parser(clean_query, facets)
        effective_plate = fb['plateSearch'] or parsed.get('plateSearch') or None

        # Validate minSpeed against hallucinations (e.g. 6900 from plate number TG 11 UV 6900)
        safe_min = parsed.get('minSpeed') if _is_number(parsed.get('minSpeed')) else fb['minSpeed']
        if safe_min and (safe_min > 200 or (effective_plate and _js_num_str(safe_min) in effective_plate)):
            safe_min = None
        safe_max = parsed.get('maxSpeed') if _is_number(parsed.get('maxSpeed')) else fb['maxSpeed']
        if safe_max and safe_max > 200:
            safe_max = None

        return jsonify(
            success=True,
            aiSource=f'ollama-{active_model}',
            filters={
                'vehicleType': final_type or fb['vehicleType'],
                'vehicleTypes': normalized if normalized else fb['vehicleTypes'],
                'minSpeed': safe_min,
                'maxSpeed': safe_max,
                'overspeedOnly': is_overspeed or fb['overspeedOnly'],
                'location': parsed.get('location') or fb['location'] or None,
                'camera': parsed.get('camera') or fb['camera'] or None,
                'signalState': parsed.get('signalState') or fb['signalState'] or None,
                'weather': parsed.get('weather') or fb['weather'] or None,
                'plateSearch': effective_plate,
                'sortBy': parsed.get('sortBy') or fb['sortBy'] or 'timestamp-desc',
            },
            explanation=parsed.get('explanation') or fb['explanation']
            or f'AI retrieved traffic telemetry matching "{clean_query}"',
            rawQuery=clean_query,
        )
    except Exception as err:  # noqa: BLE001
        print(f'[Ollama Query] AI generation failed or timed out ({err}). Using fallback parser.')
        fb = fallback_rule_parser(clean_query, facets)
        return jsonify(success=True, aiSource='rule-fallback', fallbackReason=str(err), filters=fb,
                       explanation=fb['explanation'], rawQuery=clean_query)
