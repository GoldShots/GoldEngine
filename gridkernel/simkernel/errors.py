"""Exception types raised by the kernel."""
class KernelError(Exception):
    """Base class for all kernel errors."""
class InvalidCommandError(KernelError, ValueError):
    """A command is malformed. The engine is left unchanged."""
class CommandConflictError(KernelError):
    """A command ID was reused with different contents. The engine is left unchanged."""
class TickError(KernelError, ValueError):
    """A tick argument is invalid or refers to a tick that has not been simulated."""
class ConfigurationError(KernelError, ValueError):
    """The engine was configured incorrectly."""
