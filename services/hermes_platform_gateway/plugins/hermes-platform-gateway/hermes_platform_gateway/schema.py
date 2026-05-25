"""Convert platform tool definitions to hermes JSON Schema format."""

from __future__ import annotations

_TYPE_MAP: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}


def convert_schema(tool_def: dict) -> dict:
    """Convert a platform tool definition to hermes JSON Schema format.

    A field is required unless is_required is explicitly False or a default is present.
    """
    name = tool_def["name"]
    description = tool_def.get("description", "")
    param_list: list[dict] = tool_def.get("parameters") or []

    properties: dict[str, dict] = {}
    required: list[str] = []

    for p in param_list:
        p_name = p.get("name")
        if not p_name:
            continue

        json_type = _TYPE_MAP.get(p.get("type", "str"), "string")
        prop: dict = {"type": json_type}

        p_desc = p.get("description", "")
        if p_desc:
            prop["description"] = p_desc

        if "default" in p:
            prop["default"] = p["default"]
        elif p.get("is_required", True) is not False:
            required.append(p_name)

        properties[p_name] = prop

    schema: dict = {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
        },
    }
    if required:
        schema["parameters"]["required"] = required

    return schema
