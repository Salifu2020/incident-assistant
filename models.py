# app/models.py
from pydantic import BaseModel

class QuestionRequest(BaseModel):
    query: str

class QuestionResponse(BaseModel):
    response: str

class UploadResponse(BaseModel):
    message: str
