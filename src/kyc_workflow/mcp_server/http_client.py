"""Client for the bank's reference data API (bank_api/server.py).

This is the only code that knows the HTTP contract: the key header, the
request id header, paging and the error bodies. The MCP server's tools call
it; nothing else should.

Every call sends its own `X-Request-ID`, so the id in the bank's log and the
id in our audit trail are the same string.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MAX_PAGE = 500  # the server's hard cap on ?limit=


class BankApiError(Exception):
    def __init__(self, status: int, error: str, hint: str = "", request_id: str = ""):
        super().__init__(f"{status} {error}: {hint}".strip(": "))
        self.status = status
        self.error = error
        self.hint = hint
        self.request_id = request_id


class BankApiUnavailable(BankApiError):
    """The HTTP server is not reachable at all."""


@dataclass
class Page:
    dataset: str
    rows: list[dict[str, str]]
    truncated: bool
    request_id: str
    columns: list[str] = field(default_factory=list)


@dataclass
class Rows:
    """All rows matching a filter, gathered across pages."""

    dataset: str
    rows: list[dict[str, str]]
    request_ids: list[str]


class BankApi:
    def __init__(self, base_url: str, api_key: str, *, timeout_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    # -- transport ---------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None, *, raw: bool = False):
        request_id = str(uuid.uuid4())
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urlencode({k: v for k, v in params.items() if v is not None})
        req = Request(url, headers={"X-VGB-API-Key": self.api_key, "X-Request-ID": request_id})
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read()
                echoed = resp.headers.get("X-Request-ID", request_id)
        except HTTPError as err:
            try:
                payload = json.loads(err.read().decode("utf-8"))
            except Exception:
                payload = {}
            rid = err.headers.get("X-Request-ID", request_id) if err.headers else request_id
            raise BankApiError(err.code, payload.get("error", "http_error"), payload.get("hint", ""), rid) from err
        except URLError as err:
            raise BankApiUnavailable(0, "unreachable", f"{url}: {err.reason}", request_id) from err
        if raw:
            return body, echoed
        return json.loads(body.decode("utf-8")), echoed

    # -- endpoints ---------------------------------------------------------

    def index(self) -> dict[str, Any]:
        payload, _ = self._get("/")
        return payload

    def datasets(self) -> list[str]:
        return list(self.index().get("datasets", []))

    def page(self, dataset: str, filters: dict[str, str] | None = None,
             *, limit: int = MAX_PAGE, offset: int = 0) -> Page:
        params: dict[str, Any] = dict(filters or {})
        params["limit"] = min(limit, MAX_PAGE)
        params["offset"] = offset
        payload, rid = self._get(f"/api/{dataset}", params)
        return Page(dataset=dataset, rows=payload["rows"], truncated=payload["truncated"],
                    request_id=rid, columns=payload.get("columns", []))

    def rows(self, dataset: str, filters: dict[str, str] | None = None,
             *, max_rows: int = 100_000) -> Rows:
        """Every row matching `filters`, paging until the server says done."""
        collected: list[dict[str, str]] = []
        request_ids: list[str] = []
        offset = 0
        while True:
            page = self.page(dataset, filters, offset=offset)
            collected.extend(page.rows)
            request_ids.append(page.request_id)
            if not page.truncated or len(collected) >= max_rows:
                break
            offset += len(page.rows)
        return Rows(dataset=dataset, rows=collected[:max_rows], request_ids=request_ids)

    def columns(self, dataset: str) -> list[str]:
        return self.page(dataset, limit=1).columns

    def document(self, stored_filename: str) -> tuple[str, str]:
        """Text of one customer document and the request id that fetched it."""
        body, rid = self._get(f"/api/documents/{stored_filename}", raw=True)
        return body.decode("utf-8"), rid

    def file(self, filename: str) -> tuple[bytes, str]:
        return self._get(f"/api/files/{filename}", raw=True)

    def worklist(self) -> tuple[list[dict[str, str]], str]:
        """Rows of reviews_due.xlsx as strings, dummy and system rows dropped. Cached per client."""
        cached = getattr(self, "_worklist", None)
        if cached is not None:
            return cached
        import io

        import openpyxl

        body, rid = self.file("reviews_due.xlsx")
        ws = openpyxl.load_workbook(io.BytesIO(body), read_only=True).worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        header = [str(h) for h in rows[0]]
        out: list[dict[str, str]] = []
        for r in rows[1:]:
            row = {k: ("" if v is None else str(v)) for k, v in zip(header, r)}
            rid_ = row.get("review_id", "")
            if not rid_ or rid_.startswith(("DUMMY", "SYS")) or not row.get("customer_ref") or row["customer_ref"] in ("0", "CIF-0000000"):
                continue
            out.append(row)
        self._worklist = (out, rid)
        return self._worklist
