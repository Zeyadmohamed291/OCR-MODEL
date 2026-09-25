from app.services.classification.classifier import UniversalDocumentClassifier

class DocumentClassifier:
    """
    Backwards-compatible wrapper delegating to UniversalDocumentClassifier.
    """
    
    @staticmethod
    def classify(text: str) -> str:
        doc_type, _ = UniversalDocumentClassifier.classify(text)
        return doc_type

