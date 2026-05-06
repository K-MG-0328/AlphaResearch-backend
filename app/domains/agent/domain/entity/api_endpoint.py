from typing import Optional


class ParameterInfo:
    def __init__(
        self,
        name: str,
        location: str,
        required: bool,
        schema: dict,
        description: Optional[str] = None,
    ):
        self.name = name
        self.location = location
        self.required = required
        self.schema = schema
        self.description = description


class ApiEndpoint:
    def __init__(
        self,
        path: str,
        method: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        parameters: Optional[list[ParameterInfo]] = None,
        request_body_schema: Optional[dict] = None,
        response_schema: Optional[dict] = None,
    ):
        self.path = path
        self.method = method.upper()
        self.summary = summary
        self.description = description
        self.tags = tags or []
        self.parameters = parameters or []
        self.request_body_schema = request_body_schema
        self.response_schema = response_schema

    def to_agent_tool(self) -> dict:
        tool = {
            "name": self._build_tool_name(),
            "description": self._build_description(),
            "method": self.method,
            "path": self.path,
            "parameters": {},
        }

        if self.parameters:
            tool["parameters"]["path_params"] = [
                {
                    "name": p.name,
                    "required": p.required,
                    "schema": p.schema,
                    "description": p.description,
                }
                for p in self.parameters
                if p.location == "path"
            ]
            tool["parameters"]["query_params"] = [
                {
                    "name": p.name,
                    "required": p.required,
                    "schema": p.schema,
                    "description": p.description,
                }
                for p in self.parameters
                if p.location == "query"
            ]

            if not tool["parameters"]["path_params"]:
                del tool["parameters"]["path_params"]
            if not tool["parameters"]["query_params"]:
                del tool["parameters"]["query_params"]

        if self.request_body_schema:
            tool["parameters"]["request_body"] = self.request_body_schema

        if self.response_schema:
            tool["response_schema"] = self.response_schema

        if not tool["parameters"]:
            del tool["parameters"]

        return tool

    def _build_tool_name(self) -> str:
        path_parts = [p for p in self.path.split("/") if p and not p.startswith("{")]
        name = "_".join(path_parts)
        return f"{self.method.lower()}_{name}"

    def _build_description(self) -> str:
        if self.summary:
            return self.summary
        return f"{self.method} {self.path}"
