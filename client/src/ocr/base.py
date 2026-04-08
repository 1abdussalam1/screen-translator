from abc import ABC, abstractmethod
from PIL import Image


class OCREngine(ABC):
    """Abstract base class for OCR engines."""

    @abstractmethod
    def extract_text(self, image: Image.Image) -> str:
        """Extract text from a PIL Image and return as string."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this OCR engine is available on the current system."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Return the human-readable name of the engine."""
        ...
