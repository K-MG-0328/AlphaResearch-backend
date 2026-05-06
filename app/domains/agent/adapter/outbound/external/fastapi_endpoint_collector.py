from fastapi import FastAPI

from app.domains.agent.application.port.endpoint_collector import EndpointCollector
from app.domains.agent.domain.entity.api_endpoint import ApiEndpoint, ParameterInfo


class FastApiEndpointCollector(EndpointCollector):
    def __init__(self, app: FastAPI):
        self.app = app

    def collect(self) -> list[ApiEndpoint]:
        openapi_schema = self.app.openapi()
        paths = openapi_schema.get("paths", {})
        component_schemas = openapi_schema.get("components", {}).get("schemas", {})

        endpoints: list[ApiEndpoint] = []

        for path, methods in paths.items():
            for method, operation in methods.items():
                if method in ("get", "post", "put", "delete", "patch"):
                    endpoint = self._parse_operation(
                        path, method, operation, component_schemas
                    )
                    endpoints.append(endpoint)

        return endpoints

    def _parse_operation(
        self,
        path: str,
        method: str,
        operation: dict,
        component_schemas: dict,
    ) -> ApiEndpoint:
        parameters = []
        for param in operation.get("parameters", []):
            parameters.append(
                ParameterInfo(
                    name=param["name"],
                    location=param["in"],
                    required=param.get("required", False),
                    schema=self._resolve_schema(
                        param.get("schema", {}), component_schemas
                    ),
                    description=param.get("description"),
                )
            )

        request_body_schema = None
        request_body = operation.get("requestBody", {})
        if request_body:
            content = request_body.get("content", {})
            json_content = content.get("application/json", {})
            if json_content:
                request_body_schema = self._resolve_schema(
                    json_content.get("schema", {}), component_schemas
                )

        response_schema = None
        responses = operation.get("responses", {})
        for status_code in ("200", "201"):
            if status_code in responses:
                resp_content = responses[status_code].get("content", {})
                json_resp = resp_content.get("application/json", {})
                if json_resp:
                    response_schema = self._resolve_schema(
                        json_resp.get("schema", {}), component_schemas
                    )
                    break

        return ApiEndpoint(
            path=path,
            method=method,
            summary=operation.get("summary"),
            description=operation.get("description"),
            tags=operation.get("tags"),
            parameters=parameters,
            request_body_schema=request_body_schema,
            response_schema=response_schema,
        )

    def _resolve_schema(self, schema: dict, component_schemas: dict) -> dict:
        if "$ref" in schema:
            ref_name = schema["$ref"].split("/")[-1]
            return self._resolve_schema(
                component_schemas.get(ref_name, {}), component_schemas
            )

        resolved = {}
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                resolved[key] = {
                    prop_name: self._resolve_schema(prop_schema, component_schemas)
                    for prop_name, prop_schema in value.items()
                }
            elif key == "items" and isinstance(value, dict):
                resolved[key] = self._resolve_schema(value, component_schemas)
            elif key == "allOf" and isinstance(value, list):
                merged = {}
                for item in value:
                    r = self._resolve_schema(item, component_schemas)
                    merged.update(r)
                return merged
            else:
                resolved[key] = value

        return resolved
