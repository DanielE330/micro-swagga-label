# Swagger Aggregator

Автономный микросервис, который автоматически находит все ваши API-сервисы в Docker Compose и собирает их OpenAPI-документацию в единый Swagger UI.

Не привязан к конкретному reverse-proxy. Работает с Caddy, Nginx, Traefik, HAProxy и любым другим.

## Как это работает

1. Подключается к Docker Socket и находит все контейнеры в текущем compose-проекте
2. Отбирает только те, у которых есть label `docs.route`
3. Перебирает известные пути OpenAPI (или использует явный `docs.openapi`) и забирает спеку
4. Подменяет `servers` на значение из label, чтобы «Try it out» работал через ваш gateway
5. Отдаёт всё в единый Swagger UI

## Быстрый старт

### 1. Скопируйте папку `docs_service/` в ваш проект

Внутри всего 3 файла: `main.py`, `Dockerfile`, `requirements.txt`.

### 2. Добавьте docs_service в docker-compose.yml

```yaml
docs_service:
  build: ./docs_service
  expose:
    - "8000"
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro
```

### 3. Добавьте labels к каждому микросервису

```yaml
auth_service:
  build: ./auth_service
  labels:
    - "docs.route=/auth"   # обязательно — префикс в gateway
    - "docs.port=8002"     # рекомендуется — явный порт
  expose:
    - "8002"
```

`docs.route` — публичный префикс, по которому сервис доступен снаружи через gateway.  
`docs.port` — внутренний порт контейнера (без него docs_service угадывает через Docker API, что менее надёжно).

### 4. Готово

Пробросьте `/docs` на `docs_service:8000` в вашем reverse-proxy и откройте `http://localhost:8080/docs`.

## Поддерживаемые фреймворки

Сервис автоматически перебирает все популярные пути к OpenAPI-спеке.

| Язык | Фреймворк | Путь к спеке |
| :--- | :--- | :--- |
| Python | **FastAPI** | `/openapi.json` |
| Python | **Django REST Framework** (drf-spectacular) | `/api/schema/` |
| Python | **Flask-RESTX**, Flasgger | `/swagger.json` |
| Python | **Flask-Smorest** | `/api/swagger.json` |
| Python | **Flask-APISpec** | `/apispec.json` |
| JavaScript | **Express** (swagger-ui-express) | `/api-docs` |
| JavaScript | **Express** (swagger-jsdoc) | `/api-docs/swagger.json` |
| JavaScript | **NestJS** | `/api-json`, `/swagger-json` |
| JavaScript | **Hapi** (hapi-swagger) | `/doc` |
| Java | **Spring Boot** (springdoc) | `/v3/api-docs` |
| Java | **Spring Boot** (springfox) | `/v2/api-docs` |
| Java | **Quarkus** | `/q/openapi` |
| .NET | **ASP.NET Core** (Swashbuckle) | `/swagger/v1/swagger.json` |
| .NET | **ASP.NET Core** (NSwag) | `/openapi/v1.json` |
| Go | **swag** (Gin / Echo / Fiber) | `/swagger/doc.json` |
| Dart | **Dart Frog** | `/openapi.json` |
| Ruby | **rswag** (Rails) | `/api-docs/v1/swagger.yaml` |
| PHP | **API Platform** (Symfony) | `/api/openapi` |
| PHP | **NelmioApiDocBundle** | `/api/doc.json` |
| Rust | **utoipa** (Axum / Actix) | `/api-doc/openapi.json` |
| C++ | **Drogon** / **Boost.Beast** + ручной эндпоинт | указать через `docs.openapi` |

Если ваш фреймворк использует нестандартный путь — укажите его явно:

```yaml
labels:
  - "docs.openapi=/my-service/api-spec.json"
```

## Добавление нового микросервиса

Минимально — одна обязательная метка:

```yaml
new_service:
  build: ./new_service
  labels:
    - "docs.route=/new"          # обязательно
    - "docs.port=9000"           # рекомендуется
    # - "docs.openapi=/v3/api-docs"  # если нестандартный путь
  expose:
    - "9000"
```

Название в Swagger подтянется из `info.title` спецификации автоматически.  
Сервисы без label `docs.route` в документацию не попадают — БД, кеши, очереди и gateway фильтруются автоматически.

## Labels (справочник)

| Label | Обязательный | Описание |
| :--- | :---: | :--- |
| `docs.route=/prefix` | ✅ | Публичный префикс в gateway (`servers[0].url` в спеке) |
| `docs.port=8080` | — | Внутренний порт контейнера. Без него ищется в Ports через Docker API |
| `docs.openapi=/path` | — | Явный путь к OpenAPI JSON. Без него перебираются все известные пути |

## Переменные окружения

| Переменная | По умолчанию | Описание |
| :--- | :--- | :--- |
| `CACHE_TTL` | `30` | Время кеширования спецификаций (секунды) |
| `COMPOSE_SERVICE` | `docs_service` | Имя этого сервиса в docker-compose (менять только если переименовали) |
