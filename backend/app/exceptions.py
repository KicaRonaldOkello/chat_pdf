"""Domain-specific exceptions for the chat PDF application."""


class ChatPDFError(Exception):
    """Base exception for all chat PDF errors."""

    def __init__(self, message: str, details: str | None = None):
        self.message = message
        self.details = details
        super().__init__(message)


class RetrievalError(ChatPDFError):
    """Raised when document retrieval fails."""

    pass


class JudgmentError(ChatPDFError):
    """Raised when the judge node fails to evaluate an answer."""

    pass


class GuardrailRejection(ChatPDFError):
    """Raised when the guardrail rejects a query."""

    def __init__(self, reason: str, category: str = "inappropriate"):
        self.reason = reason
        self.category = category
        super().__init__(f"Query rejected: {reason}")


class RouterError(ChatPDFError):
    """Raised when the router node fails to plan retrieval."""

    pass


class AnswererError(ChatPDFError):
    """Raised when the answerer fails to generate a response."""

    pass


class VisionError(ChatPDFError):
    """Raised when vision analysis fails."""

    pass


class DocumentProcessingError(ChatPDFError):
    """Raised when document processing (chunking, embedding) fails."""

    pass


class MetadataExtractionError(ChatPDFError):
    """Raised when metadata extraction fails."""

    pass


class StructuredOutputError(ChatPDFError):
    """Raised when LLM structured output parsing fails."""

    pass


class TimeoutError(ChatPDFError):
    """Raised when an operation times out."""

    def __init__(self, operation: str, timeout_seconds: float):
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(f"{operation} timed out after {timeout_seconds}s")
