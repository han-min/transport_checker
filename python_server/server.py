import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import os
from datetime import datetime
from auth import AuthMixin

PORT = 8080
DIRECTORY = "html"

# === TFL CONFIG - PUT YOUR KEYS HERE ===
TFL_APP_ID = "xxx"
TFL_APP_KEY = "xxx"

# === raildata.org.uk Live departure board consumer key ===
RAIL_API_KEY="xxx"
RAIL_PRODUCT_PREFIX="1010-live-departure-board-dep1_2"


def location_database_handler(handler):
    """Handles /api/proxy?v=xxx -> proxies to creativecarrot API"""
    parsed_url = urllib.parse.urlparse(handler.path)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    name_val = query_params.get('v', ['Han'])[0]
    target_url = (
        f"https://xxx.yyy.com/"
        f"?action=get&k=name&v={urllib.parse.quote(name_val)}"
    )
    try:
        req = urllib.request.Request(target_url, headers={'User-Agent': 'Python-Proxy'})
        with urllib.request.urlopen(req) as response:
            data = response.read()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.end_headers()
        handler.wfile.write(data)
    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.end_headers()
        handler.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))

def train_times_handler(handler):
    """Handles /api/trains?from=CLJ&to=WAT -> uses raildata.org.uk"""
    parsed_url = urllib.parse.urlparse(handler.path)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    from_crs = query_params.get('from', ['CLJ'])[0].upper()
    to_crs = query_params.get('to', ['WAT'])[0].upper()

    if not RAIL_API_KEY:
        handler.send_response(500)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.end_headers()
        handler.wfile.write(json.dumps({"success": False, "error": "RAIL_API_KEY not set"}).encode('utf-8'))
        return

    base = f"https://api1.raildata.org.uk/{RAIL_PRODUCT_PREFIX}/LDBWS/api/20220120/GetDepBoardWithDetails/{urllib.parse.quote(from_crs)}"
    qs = urllib.parse.urlencode({
        "numRows": "10",
        "filterCrs": to_crs,
        "filterType": "to",
        "timeOffset": "0",
        "timeWindow": "120"
    })
    target_url = f"{base}?{qs}"

    try:
        req = urllib.request.Request(
            target_url,
            headers={'x-apikey': RAIL_API_KEY, 'User-Agent': 'Python-Proxy'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = json.loads(response.read().decode('utf-8'))

        services = []
        for s in (raw.get('trainServices') or [])[:10]:
            dest_name = None
            if s.get('destination') and len(s['destination']) > 0:
                dest_name = s['destination'][0].get('locationName')

            services.append({
                "std": s.get('std'),
                "etd": s.get('etd'),
                "platform": s.get('platform'),
                "isCancelled": s.get('isCancelled', False),
                "cancelReason": s.get('cancelReason'),
                "delayReason": s.get('delayReason'),
                "operator": s.get('operator'),
                "destination": dest_name
            })

        out = {
            "from": raw.get('crs', from_crs),
            "to": to_crs,
            "generatedAt": raw.get('generatedAt', datetime.now().isoformat()),
            "services": services
        }

        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(json.dumps(out).encode('utf-8'))

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        handler.send_response(e.code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.end_headers()
        handler.wfile.write(json.dumps({"success": False, "error": f"Rail API {e.code}", "body": body}).encode('utf-8'))
    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.end_headers()
        handler.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))

def bus_times_handler(handler):
    """Handles /api/bus?stop=490008660N -> TFL live arrivals"""
    parsed_url = urllib.parse.urlparse(handler.path)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    stop_id = query_params.get('stop', ['490008660N'])[0]

    # Build TFL URL with keys if provided
    base_url = f"https://api.tfl.gov.uk/StopPoint/{urllib.parse.quote(stop_id)}/Arrivals"
    query_string = ""
    if TFL_APP_ID and TFL_APP_KEY and "YOUR_" not in TFL_APP_ID:
        query_string = f"?app_id={urllib.parse.quote(TFL_APP_ID)}&app_key={urllib.parse.quote(TFL_APP_KEY)}"
    target_url = base_url + query_string

    try:
        req = urllib.request.Request(target_url, headers={'User-Agent': 'Python-Proxy'})
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = json.loads(response.read().decode('utf-8'))

        # Sort by time to station
        raw.sort(key=lambda x: x.get('timeToStation', 9999))

        arrivals = []
        for b in raw[:8]:
            arrivals.append({
                "line": b.get('lineName'),
                "destination": b.get('destinationName'),
                "dueInMin": b.get('timeToStation', 0) // 60,
                "dueIn": f"{b.get('timeToStation', 0) // 60} min",
                "expected": b.get('expectedArrival', '')[11:16] if b.get('expectedArrival') else "",
                "vehicleId": b.get('vehicleId')
            })

        out = {
            "stopId": stop_id,
            "timestamp": datetime.now().isoformat(),
            "arrivals": arrivals
        }

        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(json.dumps(out).encode('utf-8'))

    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.end_headers()
        handler.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))

class ProxyHTTPRequestHandler(AuthMixin, http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "":
            self.path = "/location.html"

        if self.path.startswith('/api/proxy'):
            location_database_handler(self)
        elif self.path.startswith('/api/trains'):
            train_times_handler(self)
        elif self.path.startswith('/api/bus'):
            bus_times_handler(self)
        else:
            super().do_GET()

    def do_POST(self):
        if self.handle_auth_routes():
            return
        self.send_error(404)

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), ProxyHTTPRequestHandler) as httpd:
        print(f"Server running at http://localhost:{PORT}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.server_close()
