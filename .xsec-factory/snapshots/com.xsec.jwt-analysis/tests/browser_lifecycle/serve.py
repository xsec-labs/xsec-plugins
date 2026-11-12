"""Serve the JWT frontend against real isolated SQLite operations on loopback.

This component boundary does not implement Desktop authorization or MCP.
The browser page drives actual lifecycle methods, DOM, timers and HTTP calls.
"""
from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
from urllib.parse import urlsplit

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--data', type=Path, required=True)
parser.add_argument('--baseline', type=Path, required=True)
parser.add_argument('--evidence', type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.root/'src'))
os.environ['PLUGIN_ROOT'] = str(args.root)
from jwt_analysis_mcp.store import Store
from jwt_analysis_mcp.jwt_tool_adapter import diagnostics
from jwt_analysis_mcp.reports import report

store = Store(str(args.data))
jobs = {}
for project in ['lifecycle-project-a', 'lifecycle-project-b']:
    job = store.create_job(project, 'passive', {'items': [], 'profile': 'passive'})
    store.status(job, 'completed', 'completed')
    jobs[project] = job

lock = threading.Lock()
requests = []
gates = {}
for project in jobs:
    gates[project] = {'entered': threading.Event(), 'release': threading.Event(), 'armed': False}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, status, value, content_type='application/json'):
        body = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        files = {
            '/': (Path(__file__).with_name('browser.html'), 'text/html; charset=utf-8'),
            '/case.html': (Path(__file__).with_name('case.html'), 'text/html; charset=utf-8'),
            '/current.js': (args.root/'com.xsec.desktop/frontend/index.js', 'text/javascript; charset=utf-8'),
            '/baseline.js': (args.baseline, 'text/javascript; charset=utf-8'),
        }
        if path in files:
            file, content_type = files[path]
            self.respond(200, file.read_bytes(), content_type)
        elif path == '/stats':
            with lock:
                self.respond(200, {'requests': list(requests), 'jobs': jobs})
        else:
            self.respond(404, {'error': 'unknown boundary path'})

    def do_POST(self):
        path = urlsplit(self.path).path
        value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if path == '/finish':
            (args.evidence/'browser-results.json').write_text(json.dumps(value, indent=2)+'\n')
            self.respond(200, {'recorded': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path == '/control':
            gate = gates[value['projectId']]
            if value['action'] == 'pause-diagnostics':
                gate['entered'].clear()
                gate['release'].clear()
                gate['armed'] = True
            elif value['action'] == 'wait-diagnostics':
                if not gate['entered'].wait(10):
                    self.respond(500, {'error': 'diagnostics did not reach the real HTTP boundary'})
                    return
            elif value['action'] == 'release-diagnostics':
                gate['release'].set()
            elif value['action'] == 'make-jobs-unavailable':
                with store.connection() as database:
                    database.execute('ALTER TABLE jobs RENAME TO lifecycle_unavailable_jobs')
            elif value['action'] == 'restore-jobs':
                with store.connection() as database:
                    database.execute('ALTER TABLE lifecycle_unavailable_jobs RENAME TO jobs')
            else:
                self.respond(400, {'error': 'unknown control action'})
                return
            self.respond(200, {'action': value['action']})
            return
        if path != '/rpc':
            self.respond(404, {'error': 'unknown boundary path'})
            return
        project = value['projectId']
        if project not in jobs:
            self.respond(403, {'error': 'project outside isolated boundary'})
            return
        method, params = value['method'], value['params']
        with lock:
            requests.append({'method': method, 'projectId': project, 'time': time.monotonic()})
        try:
            if method == 'xsec.jwt-analysis.diagnostics':
                gate = gates[project]
                if gate['armed']:
                    gate['armed'] = False
                    gate['entered'].set()
                    if not gate['release'].wait(20):
                        raise TimeoutError('test-controlled network backpressure deadline exceeded')
                result = diagnostics()
            elif method == 'xsec.jwt-analysis.jobs.list':
                result = {'items': store.list_jobs(project, params['limit'])}
            elif method == 'xsec.jwt-analysis.jobs.get':
                result = store.job(project, params['job_id'])
            elif method == 'xsec.jwt-analysis.jobs.events':
                result = store.events(project, params['job_id'], params['cursor'], 200)
            elif method == 'xsec.jwt-analysis.report':
                result = report(store.job(project, params['job_id']), params['format'])
            else:
                raise ValueError('method outside this read-only browser boundary')
            self.respond(200, result)
        except (ValueError, OSError, sqlite3.Error, TimeoutError) as error:
            self.respond(500, {'error': str(error)})

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
server.daemon_threads = True
url = 'http://127.0.0.1:'+str(server.server_port)+'/'
(args.evidence/'browser-server.json').write_text(json.dumps({'url': url, 'pid': os.getpid(), 'componentBoundary': True})+'\n')
print(url, flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
