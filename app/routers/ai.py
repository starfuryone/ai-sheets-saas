from fastapi import APIRouter
from ..llm.providers import EchoProvider

router = APIRouter()
provider = EchoProvider()

@router.post('/clean')
def clean(text: str):
    return {"result": provider.complete(text)}

@router.post('/summarize')
def summarize(text: str):
    return {"result": provider.complete(text)}

@router.post('/seo')
def seo(text: str):
    return {"result": provider.complete(text)}
