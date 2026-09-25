class BaseOCRError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class InvalidImageError(BaseOCRError): pass
class OCRFailureError(BaseOCRError): pass
class ConfigurationError(BaseOCRError): pass
class UnsupportedFormatError(BaseOCRError): pass
class ModelLoadingError(BaseOCRError): pass
class ValidationFailureError(BaseOCRError): pass
class PayloadTooLargeError(BaseOCRError): pass
