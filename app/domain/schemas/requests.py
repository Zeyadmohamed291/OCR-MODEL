from pydantic import BaseModel

class OCRRequest(BaseModel):
    lang: str = "ar,en"
