# VGB reference data API (the bank's "Veridian KYC Starter")

Folder `bank_api/`. The MCP server that sits on top of this API lives in
`src/kyc_workflow/mcp_server/`; see the project README.

This folder holds the reference server that VGB Group Data Services shipped
with the data pack (`vgb_kyc_pack.zip`, written by Leo in Platform
Engineering). It serves the Data Ops export over HTTP the way an internal
consumer would see the bank's five record systems: one endpoint per source
file, an API key required on every call, and a request ID echoed on every
response for tracing.

**It is not an MCP server.** Inside the bank the five systems are also
exposed as MCP services, but that surface does not leave the network. What
carries over from this starter is the contract: guarded endpoints, required
headers, tracing IDs, and each source system's own data conventions. This
project puts one MCP server of its own in front of it, with tools grouped by
record system, each of which calls this HTTP API. The workflow talks to the
MCP server; this server stays as the bank delivered it.

## What was changed from the bank's copy

`server.py` is the bank's file with one functional change: the default data
directory is `../data` (that is, `kyc-workflow/data`) instead of `./data` next
to `server.py`, because the export was unzipped into `kyc-workflow/data`.
`VGB_DATA_DIR` still overrides it. Hidden files such as `.DS_Store` are
skipped when listing datasets and files. Everything else (endpoints, headers,
paging, error shapes) is as delivered.

## Quick start

Python 3.10+ and the standard library only. From the `kyc-workflow/` folder:

```bash
make bank-api
```

which runs `uv run bank_api/server.py` with `VGB_DATA_DIR` set to `./data`. Pass
`VGB_PORT=8010` or `VGB_API_KEY=...` on the make command line to override.
Or run it directly:

```bash
uv run bank_api/server.py
```

or, without uv:

```bash
python3 bank_api/server.py
```

The startup banner lists the datasets it found. With the export in place it
names `accounts`, `beneficial_owners`, `case_history`, `case_notes`,
`customers`, `doc_index`, `officers`, `qa_sample`, `screening_hits` and the
four `transactions_*` files. If the banner says no data was found, check
that the CSVs sit directly inside `kyc-workflow/data` (not in a subfolder), or
set `VGB_DATA_DIR` to wherever the export is.

First call, in another terminal:

```bash
curl -s -H 'X-VGB-API-Key: vgb-demo-key' 'http://127.0.0.1:8000/api/customers?limit=2'
```

`GET /` (no key needed) returns a JSON index of every endpoint, dataset and
required header. Start there.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `VGB_DATA_DIR` | `../data` relative to `server.py`, i.e. `kyc-workflow/data` | Directory holding the unzipped data export. |
| `VGB_API_KEY` | `vgb-demo-key` | The key the server requires on `/api/` requests. |
| `VGB_PORT` | `8000` | Port to listen on (always binds to 127.0.0.1). |

## Required headers

Every request under `/api/` must carry:

```
X-VGB-API-Key: <key>
```

Missing or wrong key gives a `401` with a JSON hint. This mirrors the
production gateways: no key, no data.

Optionally send `X-Request-ID: <anything>`. The server echoes it back on the
response, and generates one if you do not send it. Inside the bank this is
how calls are traced across systems. The workflow should generate one per
case run and carry it through its own audit log, so joint debugging with
the bank's team lines up.

## Endpoints

| Endpoint | What it returns |
|---|---|
| `GET /` | Index: endpoints, datasets, files, required headers. No key needed. |
| `GET /api/{dataset}` | Rows from that CSV as JSON. Any column name is an exact-match filter (`?customer_type=entity`), plus `?limit=` (default 50, max 500) and `?offset=`. The response carries `truncated: true` when more rows matched than were returned. |
| `GET /api/documents/{stored_filename}` | One customer document as plain text. Filenames come from `doc_index.csv` (`stored_filename` column). |
| `GET /api/files/{filename}` | One top-level non-CSV file (the xlsx reference sheets, the policy, the export README) as raw bytes. |

`{dataset}` is the CSV filename without `.csv`. Filters are exact string
matches on the raw cell value, one value per column; an unknown column
returns `400` with the list of valid columns.

Examples that reference real records in the export:

```bash
# a customer record
curl -s -H 'X-VGB-API-Key: vgb-demo-key' \
  'http://127.0.0.1:8000/api/customers?customer_ref=CIF-1004823'

# screening hits for a customer
curl -s -H 'X-VGB-API-Key: vgb-demo-key' \
  'http://127.0.0.1:8000/api/screening_hits?customer_ref=CIF-6244597'

# transactions on one account (note the column name differs by file, see below)
curl -s -H 'X-VGB-API-Key: vgb-demo-key' \
  'http://127.0.0.1:8000/api/transactions_2025H1?acct=5583716687&limit=5'

# a document
curl -s -H 'X-VGB-API-Key: vgb-demo-key' \
  'http://127.0.0.1:8000/api/documents/1004823_employment_letter_1.txt'

# the policy text, POL-042 v4.2
curl -s -H 'X-VGB-API-Key: vgb-demo-key' \
  'http://127.0.0.1:8000/api/files/risk-rating-policy-v4.2.md'

# the review worklist
curl -s -H 'X-VGB-API-Key: vgb-demo-key' \
  'http://127.0.0.1:8000/api/files/reviews_due.xlsx' -o reviews_due.xlsx
```

## How the export maps to the five record systems

The server is a thin pane of glass over the export: one dataset endpoint per
CSV, rows returned verbatim. It does not clean, normalise, join or interpret
anything. Data Ops does not normalise on export either, so each file keeps
its source system's conventions and consumers handle them as-is, the same
way internal consumers do.

| Record system (Ben's MCP server) | Export files served |
|---|---|
| Customer master | `customers`, `accounts`, `beneficial_owners`, `officers` |
| Transaction summary | `transactions_2024H2`, `transactions_2025H1`, `transactions_2025H2`, `transactions_2026H1` |
| Screening | `screening_hits` |
| Case history | `case_history` |
| Document store | `doc_index` plus `documents/*.txt` |

Files in the export that are not one of the five systems:

| File | What it is | Served at |
|---|---|---|
| `case_notes.csv` | Completed periodic-review write-ups: analyst, outcome, rationale text, clauses cited, checker | `/api/case_notes` |
| `qa_sample.csv` | The QA function's re-review log, 75 cases, with the recorded and QA outcomes and the reason for any difference | `/api/qa_sample` |
| `reviews_due.xlsx` | The review worklist | `/api/files/reviews_due.xlsx` |
| `codes_master.xlsx` | Reference codes | `/api/files/codes_master.xlsx` |
| `risk-rating-policy-v4.2.md` | POL-042 v4.2, the Customer Risk Rating and Periodic Review Policy | `/api/files/risk-rating-policy-v4.2.md` |
| `branch_nps_survey_2019.xlsx` | Unrelated to reviews; in the export as delivered | `/api/files/branch_nps_survey_2019.xlsx` |
| `README.txt` | Data Ops' note on the export window | `/api/files/README.txt` |

The data pack's zip is also sitting in `kyc-workflow/data`, so it shows up under
`/api/files` too. It is harmless but not part of the export.

## Known conventions in this export

There is no data dictionary ("ask if a column is unclear"). These are the
things a consumer trips over first. They are properties of the data, not of
the server, and the workflow's connectors have to handle them.

- **Customer identifiers come in four shapes** in `customers`, `accounts`,
  `beneficial_owners`, `officers` and `case_history`: `CIF-1234567`,
  `CIF1234567`, `CIF123456` and a bare `1234567`. Filters are exact-match,
  so a lookup has to try the shape the file uses. `doc_index.customer_id`
  always uses `CIF-1234567`.
- **`screening_hits.customer_ref` is sometimes a name**, not an identifier,
  for a handful of rows.
- **Review identifiers come in four shapes** in `case_notes.review_id`:
  `VGB-PR-2026-0041`, `PR2026-0014`, `vgb_pr_26_0032` and a bare `0032`.
  `doc_index.review_id` and `qa_sample.review_id` always use
  `VGB-PR-2026-0041`.
- **`transactions_2026H1` has different column names** from the three
  earlier files: `transaction_date, account_number, amount, direction,
  counterparty_name, counterparty_country` versus `txn_dt, acct, amt, dr_cr,
  cpty, cpty_ctry`. Direction is `credit`/`debit` in 2026H1 and `C`/`D`
  before. Amounts are sometimes quoted with thousands separators
  (`"3,059.80"`).
- **`doc_index` covers 826 of the 1,032 files in `documents/`.** The 206
  unindexed files follow two other naming patterns (`doc0014-0002.txt` and
  `VGB-PR-2026-0041__sof-letter-1.txt`) plus some in the indexed pattern.
  The document endpoint serves any file in the folder by name, indexed or
  not.
- **Transactions cover Dec 2024 onward** (Data Ops' README). Reviews that
  need a twelve-month window before that have no transaction data.

## Layout

```
kyc-workflow/
├── data/              the unzipped export (CSVs, documents/, xlsx, policy)
├── bank_api/
│   ├── README.md      this file
│   └── server.py      the whole API, standard library only
└── src/kyc_workflow/mcp_server/   the MCP server whose tools call this API
```

Questions about the export contents go to Data Ops (data-ops@vgb.example);
questions about the server go to Group Data Services integration engineering.
