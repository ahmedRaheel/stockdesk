"""Optional vision-assisted catalog draft. Never saves an unverified model suggestion."""
import base64
import io
import json
import os
import re
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from PIL import Image, UnidentifiedImageError
import httpx
from .contracts import Contract
from .router import User, authenticated
from .. import db, security, service
from ..rules import fail

router=APIRouter(prefix='/api/v1/tenants/{tenant}/smart-capture',tags=['Smart product capture'],dependencies=[Depends(authenticated)])


class Photo(Contract):
    image_base64: str=Field(min_length=100,max_length=3_000_000)


def validate_photo(image_base64):
    try:
        raw=base64.b64decode(image_base64,validate=True)
        if len(raw)>2_000_000: fail('Photo exceeds 2 MB.',413)
        with Image.open(io.BytesIO(raw)) as picture:
            if picture.format not in ('JPEG','PNG','WEBP'):
                fail('Use a JPEG, PNG or WebP product photo.',415)
            if picture.width*picture.height>12_000_000:
                fail('Photo resolution exceeds the safe limit.',413)
            picture.verify()
        with Image.open(io.BytesIO(raw)) as picture:
            rgb=picture.convert('RGB')
            rgb.thumbnail((1024,1024))
            output=io.BytesIO()
            rgb.save(output,format='JPEG',quality=82)
            return base64.b64encode(output.getvalue()).decode()
    except (ValueError,UnidentifiedImageError,OSError,Image.DecompressionBombError):
        fail('Invalid or damaged product image.',422)


def sanitize_suggestion(result):
    if not isinstance(result,dict): return {'name':'','category_code':'general','barcode':'','notes':'Review the photo and enter product details manually.'}
    name=str(result.get('name') or '')[:150].strip()
    code=re.sub('[^a-z0-9_-]','',str(result.get('category_code') or 'general').lower())[:60] or 'general'
    barcode=str(result.get('barcode') or '').strip()[:60]
    barcode=barcode if re.fullmatch(r'[ -~]*',barcode) else ''
    return {'name':name,'category_code':code,'barcode':barcode,
            'notes':'AI draft only. Verify brand, name, barcode, category and all prices before saving.'}


@router.post('/suggest')
async def suggest(tenant:str,payload:Photo,request:Request,user:User):
    security.csrf(request)
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'product')
    # Opt-in deployment-side model, no implicit transmission of customer photos.
    model=os.getenv('STOCKDESK_VISION_MODEL','').strip()
    if not model:
        fail('Vision model is not configured. Set STOCKDESK_VISION_MODEL on the backend.',503)
    image=validate_photo(payload.image_base64)
    base=os.getenv('STOCKDESK_OLLAMA_URL','http://ollama:11434').rstrip('/')
    if not re.fullmatch(r'https?://[a-zA-Z0-9._:-]+',base):
        fail('Invalid configured model endpoint.',503)
    prompt=("Identify this retail product for a human-reviewed draft. Return one JSON object "
       "with fields name, category_code, barcode. Never infer a price or stock quantity. "
       "Choose category_code from general, pantry, produce, medicine. "
       "Leave name or barcode blank if not visually legible. Do not invent facts.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0,connect=4.0)) as client:
            response=await client.post(base+'/api/chat',json={'model':model,'stream':False,'format':'json',
                'messages':[{'role':'user','content':prompt,'images':[image]}]})
            response.raise_for_status()
        content=response.json().get('message',{}).get('content','{}')
        proposed=json.loads(content)
    except (httpx.HTTPError,ValueError,KeyError):
        fail('Product recognition is temporarily unavailable. Use manual catalog entry.',503)
    return {'draft':sanitize_suggestion(proposed),'source':'optional_local_vision_model','saved':False}
