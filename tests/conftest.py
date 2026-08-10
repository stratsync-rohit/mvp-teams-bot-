import os

# Ensure a predictable, credential-free test environment regardless of any
# local .env file, so tests never accidentally hit real Teams/n8n endpoints.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("MICROSOFT_APP_ID", "")
os.environ.setdefault("MICROSOFT_APP_PASSWORD", "")
os.environ.setdefault("MICROSOFT_TENANT_ID", "")
os.environ.setdefault("N8N_ACTION_WEBHOOK_URL", "https://n8n.example.com/webhook/risk-actions")
os.environ.setdefault("INTERNAL_API_KEY", "")
