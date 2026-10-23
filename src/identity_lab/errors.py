"""Fixed operational failures; never include upstream messages or credentials."""

ERROR_STATUS = {
    "toolbox-not-configured": 503,
    "toolbox-schema-invalid": 503,
    "toolbox-tool-unavailable": 503,
    "toolbox-execution-failed": 502,
}


class LabError(RuntimeError):
    def __init__(self, code: str):
        if code not in ERROR_STATUS:
            raise ValueError("Unknown operational error code.")
        self.code = code
        self.status = ERROR_STATUS[code]
        super().__init__(code)

    def public(self):
        return {"kind": "identity-lab-error-v1", "code": self.code}
