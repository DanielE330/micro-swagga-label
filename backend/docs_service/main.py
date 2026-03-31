import os
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def get_service_urls() -> list[dict]:
    """Парсит SERVICES env: 'Auth Service=/auth,User Service=/users'"""
    raw = os.getenv("SERVICES", "")
    urls = []
    for entry in raw.split(","):
        entry = entry.strip()
        if "=" not in entry:
            continue
        name, path = entry.split("=", 1)
        urls.append({
            "url": f"{path.strip()}/openapi.json",
            "name": name.strip(),
        })
    return urls


@app.get("/", response_class=HTMLResponse)
def docs():
    urls = get_service_urls()
    primary = urls[0]["name"] if urls else ""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <link rel="shortcut icon" href="https://fastapi.tiangolo.com/img/favicon.png">
    <title>API Documentation - Swagger UI</title>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
    <script>
    const ui = SwaggerUIBundle({{
        urls: {json.dumps(urls)},
        "urls.primaryName": {json.dumps(primary)},
        dom_id: "#swagger-ui",
        deepLinking: true,
        showExtensions: true,
        showCommonExtensions: true,
        presets: [
            SwaggerUIBundle.presets.apis,
            SwaggerUIStandalonePreset
        ],
        plugins: [
            SwaggerUIBundle.plugins.DownloadUrl
        ],
        layout: "StandaloneLayout",
    }})
    </script>
</body>
</html>"""
