import os
import json
import copy
import time
import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import httpx

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

CACHE_TTL = int(os.getenv("CACHE_TTL", "30"))
DOCKER_SOCKET = "/var/run/docker.sock"
SELF_SERVICE = os.getenv("COMPOSE_SERVICE", "docs_service")

# Популярные пути OpenAPI-спеки — перебираются по порядку, если не задан docs.openapi
OPENAPI_PROBE_PATHS = [
    # Python
    "/openapi.json",              # FastAPI
    "/api/schema/",              # Django REST Framework (drf-spectacular)
    "/api/schema/swagger-ui/",   # DRF spectacular UI endpoint
    "/swagger.json",             # Flask-RESTX, Flasgger
    "/apispec.json",             # Flask-APISpec
    "/api/swagger.json",         # Flask-Smorest
    "/api/openapi.json",         # общий путь

    # JavaScript / TypeScript
    "/api-docs",                 # Express swagger-ui-express
    "/api-docs/swagger.json",    # Express swagger-jsdoc
    "/api-json",                 # NestJS
    "/swagger-json",             # NestJS (альтернатива)
    "/doc",                      # Hapi (hapi-swagger)
    "/documentation/json",       # Hapi (swagger-hapi)
    "/q/openapi",                # Quarkus

    # JVM (Java / Kotlin / Scala)
    "/v3/api-docs",              # Spring Boot (springdoc-openapi)
    "/v2/api-docs",              # Spring Boot (springfox)
    "/api/v3/api-docs",
    "/openapi/v3/api-docs",
    "/swagger/swagger-config",   # springfox (config)
    "/webjars/swagger-ui/index.html",  # springfox UI (не JSON, пропускаем)
    "/q/openapi",                # Quarkus

    # .NET
    "/swagger/v1/swagger.json",  # ASP.NET Core (Swashbuckle)
    "/swagger/v2/swagger.json",
    "/openapi/v1.json",          # ASP.NET Core (NSwag)
    "/api/swagger.json",

    # Go
    "/swagger/doc.json",         # swag (gin/echo/fiber)
    "/swagger/swagger.json",
    "/api/swagger.json",

    # Dart / Flutter
    "/openapi.json",             # Dart Frog (уже выше)

    # Ruby
    "/api-docs/v1/swagger.yaml", # rswag
    "/api-docs/swagger.yaml",

    # PHP
    "/api/doc.json",             # NelmioApiDocBundle (Symfony)
    "/api/openapi",              # API Platform

    # Rust / C++
    "/api-doc/openapi.json",     # utoipa (Rust/Axum/Actix)
    "/openapi",                  # общий fallback

    # Универсальные fallback-пути
    "/api/openapi.json",
    "/api/openapi",
    "/openapi/openapi.json",
    "/docs/openapi.json",
]

_cache_time: float = 0
_services: list[dict] = []


async def _list_services() -> list[dict]:
    """
    Находит сервисы в том же compose-проекте, у которых есть label docs.route.

    Поддерживаемые labels на сервисе:
      docs.route=/prefix   — обязательно, префикс пути в Caddy
      docs.port=8080       — явно задать порт (рекомендуется)
      docs.openapi=/path   — явно задать путь к OpenAPI-спеке
    """
    transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET)
    async with httpx.AsyncClient(transport=transport, base_url="http://docker") as client:
        r = await client.get("/containers/json")
        if r.status_code != 200:
            return []
        containers = r.json()

    project = None
    for c in containers:
        if c.get("Labels", {}).get("com.docker.compose.service") == SELF_SERVICE:
            project = c["Labels"].get("com.docker.compose.project")
            break

    if not project:
        return []

    result = []
    for c in containers:
        labels = c.get("Labels", {})
        if labels.get("com.docker.compose.project") != project:
            continue
        route = labels.get("docs.route")
        if not route:
            continue
        name = labels.get("com.docker.compose.service", "")

        # 1. Явный label docs.port — самый надёжный способ
        port = None
        if labels.get("docs.port"):
            try:
                port = int(labels["docs.port"])
            except ValueError:
                pass

        # 2. Fallback: ищем в массиве Ports (работает для published и exposed портов)
        if port is None:
            for p in c.get("Ports", []):
                if p.get("Type") == "tcp" and p.get("PrivatePort"):
                    port = p["PrivatePort"]
                    break

        if port is None:
            continue

        openapi_path = labels.get("docs.openapi")  # None = автоперебор
        result.append({
            "host": name,
            "port": port,
            "prefix": route,
            "openapi_path": openapi_path,
        })

    return result


async def _fetch_spec(client: httpx.AsyncClient, svc: dict) -> dict | None:
    base = f"http://{svc['host']}:{svc['port']}"

    # Если путь задан явно — пробуем только его
    if svc.get("openapi_path"):
        paths = [svc["openapi_path"]]
    else:
        paths = OPENAPI_PROBE_PATHS

    for path in paths:
        try:
            r = await client.get(f"{base}{path}", follow_redirects=True)
            if r.status_code == 200:
                content_type = r.headers.get("content-type", "")
                if "json" in content_type or "yaml" in content_type or path.endswith(".json"):
                    spec = r.json()
                    if isinstance(spec, dict) and ("paths" in spec or "openapi" in spec or "swagger" in spec):
                        return {
                            "host": svc["host"],
                            "prefix": svc["prefix"],
                            "title": spec.get("info", {}).get("title", svc["host"]),
                            "spec": spec,
                        }
        except Exception:
            continue

    return None


async def _discover():
    global _cache_time, _services
    if time.time() - _cache_time < CACHE_TTL and _services:
        return

    try:
        candidates = await _list_services()
    except Exception:
        return

    async with httpx.AsyncClient(timeout=5.0) as client:
        results = await asyncio.gather(*[_fetch_spec(client, s) for s in candidates])

    _services = [s for s in results if s]
    _cache_time = time.time()


@app.get("/specs/{host}")
async def get_spec(host: str):
    await _discover()
    for svc in _services:
        if svc["host"] == host:
            spec = copy.deepcopy(svc["spec"])
            spec["servers"] = [{"url": svc["prefix"]}]
            return JSONResponse(spec)
    return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/", response_class=HTMLResponse)
async def docs():
    await _discover()
    urls = [{"url": f"/docs/specs/{s['host']}", "name": s["title"]} for s in _services]
    primary = urls[0]["name"] if urls else ""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <title>API Docs</title>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
    <script>
    SwaggerUIBundle({{
        urls: {json.dumps(urls)},
        "urls.primaryName": {json.dumps(primary)},
        dom_id: "#swagger-ui",
        deepLinking: true,
        presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
        layout: "StandaloneLayout",
    }})
    </script>
</body>
</html>"""
