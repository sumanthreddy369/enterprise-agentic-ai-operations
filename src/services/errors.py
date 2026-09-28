"""Safe, transport-independent failure categories."""


class ServiceError(Exception):
    pass


class PermissionDenied(ServiceError):
    pass


class ToolNotFound(ServiceError):
    pass


class InvalidToolInput(ServiceError):
    pass


class ToolUnavailable(ServiceError):
    pass


class ToolTimeout(ServiceError):
    pass


class ToolBusy(ServiceError):
    pass


class InvalidToolOutput(ServiceError):
    pass
