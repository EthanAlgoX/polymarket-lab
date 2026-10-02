# Security policy

Supported security fixes target the latest `0.1.x` release. Please report a vulnerability privately through GitHub Security Advisories rather than a public issue.

Do not include credentials, account data, personal data, or live wallet material in a report. Polymarket access uses public, unauthenticated read endpoints only; the project has no real transaction capability.

The only supported secret is an optional server-side DeepSeek API key for translating public market text. Keep it in environment variables or an ignored local `.env`; never put it in the browser, logs, examples, or Git. Translation requests are restricted to public text already served by the app, sent only to the official HTTPS DeepSeek endpoint, and cached locally. Translations do not change market data or calculations.

Run the app on localhost as intended. Its local settings, simulation, and translation endpoints have no user authentication; exposing them publicly would require an additional access-control boundary. Do not commit runtime databases, translation caches, logs, or virtual environments. See [the security boundary](docs/SECURITY_BOUNDARY.md).
