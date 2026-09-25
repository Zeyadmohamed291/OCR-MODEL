from abc import ABC, abstractmethod
import numpy as np
from app.domain.schemas.core import OCRResult

class AbstractOCREngine(ABC):
    @abstractmethod
    def process_image(self, image: np.ndarray) -> OCRResult:
        """
        Process the given image and extract text.
        """
        pass
