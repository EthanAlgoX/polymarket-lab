# Polymarket Lab
Polymarket Lab is a local, public-data research workspace for people exploring prediction markets. Its core mechanism joins a broad Gamma market catalog to a bounded binary-market CLOB scanner, executable-depth estimates and auditable paper observations.

The main task is to discover a market, inspect its rules and source snapshots, evaluate a full-set estimate and keep an observation that can be traced later. Visitors frequently filter and inspect large tables; operational health and configuration support this work.

The platform is web, rendered with FastAPI/Jinja2, native CSS and vanilla JavaScript, without a frontend build step. The interface defaults to English. Chinese requires a user-configured backend LLM API and translates only public market text while preserving financial values and identifiers.

Public-data-only is a permanent boundary: no wallet connections, signing, authenticated trading APIs, orders, transfers or geographic bypass. Estimates use Decimal arithmetic, are snapshot-based, and do not establish realized returns. Catalog coverage, bounded scanner scope, API fetch time and quote source time remain distinct. Unknown fees or stale/incomplete depth cannot be passing candidates.

Users work on laptops or desktop monitors, often in daylight while comparing sources. Narrow screens must retain every navigation destination and the ability to inspect wide data without expanding the page itself.

Original MIT attribution and source research remain visible. API credentials stay on the local backend, are never returned to the browser, and are never committed.
