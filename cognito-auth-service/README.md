# Cognito Auth Service

A minimal FastAPI application that exposes the Cognito-related endpoints from the
LeafLab API as a standalone service. Route `/v1/cognito/*` traffic from API
Gateway to this service once the environment variables below are configured.

## Configuration

Provide the following environment variables (for example via your task
definition, Lambda configuration, or a `.env` file):

- `COGNITO_REGION`
- `COGNITO_USER_POOL_ID`
- `COGNITO_CLIENT_ID`
- `COGNITO_CLIENT_SECRET` (optional, only required for app clients with a secret)
- `COGNITO_DOMAIN`
- `COGNITO_REDIRECT_URI`
- `COGNITO_LOGOUT_REDIRECT_URI` (optional)
- `COOKIE_DOMAIN` (optional, defaults to `localhost`)

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

The service mounts the Cognito router under `/v1/cognito`, matching the original
API structure.
