#!/usr/bin/env python3
"""Veridian Global Bank (VGB) reference data API.

A small read-only HTTP server over the VGB data export. It serves the
review reference data the way internal consumers see the source systems:
HTTP endpoints with required headers, tracing IDs on every response.

Run it:

    python3 server.py

No dependencies beyond the Python standard library (Python 3.10+; tested on 3.13).

Configuration (environment variables):

    VGB_DATA_DIR   directory holding the data export
                   (default: ../data, the project's data folder)
    VGB_API_KEY    the API key the server requires   (default: vgb-demo-key)
    VGB_PORT       port to listen on                 (default: 8000)

Every request under /api/ must carry the header:

    X-VGB-API-Key: <your key>

Requests without it get a 401 with a hint. Every response echoes an
X-Request-ID header (yours if you sent one, a generated one otherwise) —
the same pattern our production gateways use for support tickets.

The server returns export rows verbatim. It does not clean, normalise,
or join anything: what is in the files is what you get.
"""

import csv
import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

HERE = os.path.dirname(os.path.abspath(__file__))
# In this repo the export lives in kyc-workflow/data, one level above this file.
# VGB_DATA_DIR still overrides it. Absolute, so the banner shows where it really looked.
DEFAULT_DATA_DIR = os.path.join(HERE, "..", "data")
DATA_DIR = os.path.abspath(os.environ.get("VGB_DATA_DIR", DEFAULT_DATA_DIR))
API_KEY = os.environ.get("VGB_API_KEY", "vgb-demo-key")
PORT = int(os.environ.get("VGB_PORT", "8000"))

DEFAULT_LIMIT = 50
MAX_LIMIT = 500

RESERVED_PARAMS = {"limit", "offset"}

SETUP_HINT = (
    "No data export is wired up yet. Unzip the data export you received "
    "from Data Ops into kyc-workflow/data (the CSVs directly inside it), or "
    "point the server at the export folder: "
    'VGB_DATA_DIR="/path/to/vgb_data_export_final_v2" python3 server.py. '
    "See README.md, 'Quick start'."
)


def list_datasets():
    """CSV files in the data directory, by stem — each is one dataset."""
    try:
        names = os.listdir(DATA_DIR)
    except FileNotFoundError:
        return []
    return sorted(n[:-4] for n in names if n.endswith(".csv") and not n.startswith("."))


def list_files():
    """Top-level non-CSV files (xlsx reference files, README)."""
    try:
        names = os.listdir(DATA_DIR)
    except FileNotFoundError:
        return []
    return sorted(
        n for n in names
        if os.path.isfile(os.path.join(DATA_DIR, n))
        and not n.endswith(".csv")
        and not n.startswith(".")  # skip .DS_Store and the like
    )


def query_dataset(dataset, filters, limit, offset):
    """Stream a CSV, applying exact-match filters. Returns (fieldnames, rows, truncated)."""
    path = os.path.join(DATA_DIR, dataset + ".csv")
    rows = []
    matched = 0
    truncated = False
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        unknown = [k for k in filters if k not in fieldnames]
        if unknown:
            raise KeyError(unknown[0])
        for row in reader:
            if all(row.get(k) == v for k, v in filters.items()):
                if matched >= offset:
                    if len(rows) < limit:
                        rows.append(row)
                    else:
                        truncated = True
                        break
                matched += 1
    return fieldnames, rows, truncated


class Handler(BaseHTTPRequestHandler):
    server_version = "VGBReferenceAPI/1.0"

    # -- helpers ---------------------------------------------------------

    def _request_id(self):
        return self.headers.get("X-Request-ID") or str(uuid.uuid4())

    def _send_json(self, status, payload):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", self._request_id())
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", self._request_id())
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        return self.headers.get("X-VGB-API-Key") == API_KEY

    # -- routing ---------------------------------------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        parts = [unquote(p) for p in parsed.path.split("/") if p]

        if not parts:
            return self._index()

        if parts[0] != "api":
            return self._send_json(404, {"error": "not_found",
                                         "hint": "All data lives under /api/. GET / lists the endpoints."})

        if not self._authorized():
            return self._send_json(401, {
                "error": "missing_or_invalid_api_key",
                "hint": "Send the header 'X-VGB-API-Key' with your key. "
                        "For local runs the default key is set by VGB_API_KEY "
                        "(see README).",
            })

        if not list_datasets() and not list_files():
            return self._send_json(503, {"error": "no_data_configured",
                                         "hint": SETUP_HINT})

        if len(parts) == 3 and parts[1] == "documents":
            return self._document(parts[2])
        if len(parts) == 3 and parts[1] == "files":
            return self._file(parts[2])
        if len(parts) == 2:
            return self._dataset(parts[1], parse_qs(parsed.query))

        return self._send_json(404, {"error": "not_found",
                                     "hint": "GET / lists every endpoint this server has."})

    # -- endpoints -------------------------------------------------------

    def _index(self):
        payload = {
            "service": "Veridian Global Bank reference data API",
            "data_dir": DATA_DIR,
            "required_headers": {
                "X-VGB-API-Key": "required on every /api/ request",
                "X-Request-ID": "optional; echoed back on the response for tracing",
            },
            "endpoints": {
                "GET /api/{dataset}": "rows from that CSV; any column is an "
                                      "exact-match filter (?col=value), plus "
                                      "?limit= and ?offset=",
                "GET /api/documents/{stored_filename}": "one customer document (text)",
                "GET /api/files/{filename}": "one top-level non-CSV file (e.g. xlsx), raw bytes",
            },
            "datasets": list_datasets(),
            "files": list_files(),
            "example": "curl -H 'X-VGB-API-Key: <key>' "
                       "'http://127.0.0.1:%d/api/customers?limit=2'" % PORT,
        }
        if not list_datasets() and not list_files():
            payload["notice"] = SETUP_HINT
        self._send_json(200, payload)

    def _dataset(self, dataset, query):
        if dataset not in list_datasets():
            return self._send_json(404, {"error": "unknown_dataset",
                                         "datasets": list_datasets()})
        try:
            limit = int(query.get("limit", [DEFAULT_LIMIT])[0])
            offset = int(query.get("offset", [0])[0])
            if limit < 0 or offset < 0:
                raise ValueError
        except ValueError:
            return self._send_json(400, {"error": "bad_paging",
                                         "hint": "limit and offset must be non-negative integers"})
        limit = min(limit, MAX_LIMIT)
        repeated = [k for k, v in query.items()
                    if k not in RESERVED_PARAMS and len(v) > 1]
        if repeated:
            return self._send_json(400, {"error": "repeated_filter_param",
                                         "column": repeated[0],
                                         "hint": "Each filter column may appear at most once; "
                                                 "filters are exact-match."})
        filters = {k: v[0] for k, v in query.items() if k not in RESERVED_PARAMS}
        try:
            fieldnames, rows, truncated = query_dataset(dataset, filters, limit, offset)
        except KeyError as e:
            path = os.path.join(DATA_DIR, dataset + ".csv")
            with open(path, newline="", encoding="utf-8-sig") as f:
                fields = csv.DictReader(f).fieldnames or []
            return self._send_json(400, {"error": "unknown_filter_column",
                                         "column": str(e.args[0]),
                                         "valid_columns": fields})
        self._send_json(200, {
            "dataset": dataset,
            "columns": fieldnames,
            "filters": filters,
            "offset": offset,
            "limit": limit,
            "returned": len(rows),
            "truncated": truncated,
            "rows": rows,
        })

    def _document(self, name):
        name = os.path.basename(name)
        path = os.path.join(DATA_DIR, "documents", name)
        if not os.path.isfile(path):
            return self._send_json(404, {"error": "document_not_found",
                                         "hint": "Filenames come from doc_index.csv "
                                                 "(the stored_filename column)."})
        with open(path, "rb") as f:
            self._send_bytes(200, f.read(), "text/plain; charset=utf-8")

    def _file(self, name):
        name = os.path.basename(name)
        if name.endswith(".csv") or name not in list_files():
            return self._send_json(404, {"error": "file_not_found",
                                         "files": list_files()})
        with open(os.path.join(DATA_DIR, name), "rb") as f:
            self._send_bytes(200, f.read(), "application/octet-stream")

    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args), flush=True)


class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second process bind the same port silently;
    # keep the stdlib default (reuse) everywhere else.
    allow_reuse_address = os.name != "nt"
    request_queue_size = 64   # stdlib default (5) sheds connections when an agent fans out requests
    daemon_threads = True


def main():
    try:
        server = Server(("127.0.0.1", PORT), Handler)
    except OSError as e:
        print("Could not listen on 127.0.0.1:%d (%s)." % (PORT, e), flush=True)
        print("Another server is probably using that port. Stop it, or pick another port:", flush=True)
        print('  VGB_PORT=8010 python3 server.py     (PowerShell: $env:VGB_PORT = "8010"; python server.py)', flush=True)
        raise SystemExit(1)
    print("VGB reference API listening on http://127.0.0.1:%d" % PORT, flush=True)
    if list_datasets():
        print("Serving data from: %s" % DATA_DIR, flush=True)
        print("Datasets: %s" % ", ".join(list_datasets()), flush=True)
    else:
        print("", flush=True)
        print("No data export found (looked in: %s)." % DATA_DIR, flush=True)
        print("The server is up, but /api/ requests will return a setup hint", flush=True)
        print("until it can see the data. To wire it up:", flush=True)
        print("", flush=True)
        print("  1. Unzip the data export you received from Data Ops.", flush=True)
        print("  2. Put its files (the CSVs, documents/, xlsx) in kyc-workflow/data,", flush=True)
        print("     or restart with VGB_DATA_DIR pointing at the export folder:", flush=True)
        print("", flush=True)
        print('     VGB_DATA_DIR="/path/to/vgb_data_export_final_v2" python3 server.py', flush=True)
        print("", flush=True)
        print("See README.md, 'Quick start'.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
