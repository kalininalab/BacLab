from typing import Type, Dict, Any

TOOL_REGISTRY: Dict[str, Type] = {}

def register_tool(name: str):
    """
    Decorator to register a tool class in the TOOL_REGISTRY.
    """
    def decorator(cls: Type):
        TOOL_REGISTRY[name] = cls
        # Ensure the tool class knows its registered name
        cls.tool_name = name
        return cls
    return decorator

def get_tool(name: str) -> Type:
    """
    Retrieve a tool class from the registry by its registered name.
    """
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Tool '{name}' is not registered.")
    return TOOL_REGISTRY[name]
