# Security policy

Supported security fixes target the latest `0.1.x` release. Please report a vulnerability privately through GitHub Security Advisories rather than a public issue.

Do not include credentials, account data, personal data, or live wallet material in a report. Polymarket access uses public, unauthenticated read endpoints only; the project has no real transaction capability.

The only supported secrets are user-provided LLM API keys for translating public market text. DeepSeek uses its official HTTPS host; OpenAI-compatible providers must use public HTTPS Chat Completions endpoints on port 443. Private/localhost destinations, redirects and other API protocols are unsupported. Translation requests accept only public text already served by the app. Translations do not change market data or calculations.

Credentials stay on the backend in environment variables, an ignored `.env`, or the website's ignored `data/llm-config.json`. Native local website configuration uses an atomic owner-only file on Unix; reads never return the saved key or a key fragment. Never put credentials in frontend source, logs, examples or Git. Configuration saving does not make a paid provider test request. English is the default; Chinese requires a configured API key and translates only visible market text.

Credential changes require a same-origin request with both the host and peer on loopback. Configuration metadata is available to the same-origin website without returning credentials. Docker bridge peers cannot save/remove website credentials; container users configure DeepSeek through ignored `.env` and recreate the container. See [language setup](README.md#language-and-your-translation-api).

Run the app on localhost as intended. Its local settings, simulation, and translation endpoints have no user authentication; exposing them publicly would require an additional access-control boundary. Do not commit runtime databases, translation caches, logs, or virtual environments. See [the security boundary](docs/SECURITY_BOUNDARY.md).
