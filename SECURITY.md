# Security Policy

## Supported Versions

This project is a **sample / reference implementation** demonstrating Microsoft Agent Framework with Microsoft Foundry Hosted Agents. It is provided as-is for educational and demonstration purposes.

| Version | Supported |
|---------|-----------|
| Latest  | ✅        |
| Older   | ❌        |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

To report a security issue, use the GitHub Security Advisory ["Report a Vulnerability"](../../security/advisories/new) tab, or send an email to [secure@microsoft.com](mailto:secure@microsoft.com).

You should receive a response within 72 hours. If for some reason you do not, please follow up via email to ensure we received your original message.

Please include as much of the following information as possible to help us better understand and resolve the issue:

- Type of issue (e.g. prompt injection, credential leakage, SSRF)
- Full paths of affected source files
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

## Security Design Notes

### Authentication
- The hosted agent uses **Managed Identity** (no API keys or client secrets in code).
- `DefaultAzureCredential` is used for Azure OpenAI access; tokens are refreshed automatically via `get_bearer_token_provider`.
- No credentials are hardcoded. All configuration is injected via environment variables set by the Foundry platform.

### Prompt Input Handling
- Incident payloads are passed directly to Azure OpenAI via the Agent Framework. The system prompt instructs each agent to **redact credential-like material** as `[REDACTED]`.
- The application does **not** execute model-suggested shell commands — all runbook steps are returned as structured JSON for human review.
- There is no direct database access, file-system write access, or external network calls beyond Azure OpenAI.

### Container Security
- The Dockerfile uses `python:3.12-slim` (minimal attack surface).
- No secrets are baked into the image; all sensitive values come from the Foundry-injected environment at runtime.
- The container runs as a non-root user by default in the Foundry Agent Service hosting environment.

### Known Limitations
- This sample does not include network policies, WAF, or DDoS protection. Add these when moving to production.
- Structured JSON output from the LLM is validated against a schema but not sanitised for downstream HTML rendering — apply output encoding if surfacing agent output in a web UI.
- The Responses API endpoint exposed by the Foundry platform is authenticated; do not expose port 8088 directly to the internet.

## Microsoft Security Response Center

Microsoft takes the security of its software products and services seriously. For general Microsoft security issues, see the [Microsoft Security Response Center (MSRC)](https://msrc.microsoft.com).
