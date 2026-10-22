"""Scenario definitions shared by the CLI and evidence evaluator."""

PATTERNS = {
    "P01": ("Direct user invocation", "direct", "probe"),
    "P02": ("Middleware OBO", "obo", "probe"),
    "P03": ("Trusted backend delegation", "delegation", "probe"),
    "P04": ("Direct user, A2A", "direct", "a2a"),
    "P05": ("Middleware OBO, A2A", "obo", "a2a"),
    "P06": ("Direct user, Responses chain", "direct", "chain"),
    "P07": ("Middleware OBO, Responses chain", "obo", "chain"),
    "P08": ("Direct user, MCP wrapper", "direct", "mcp"),
    "P09": ("Middleware OBO, MCP wrapper", "obo", "mcp"),
}

CONFIGURATIONS = ("user", "service", "drop-context")
