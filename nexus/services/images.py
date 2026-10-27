"""Real image generation with protected storage, limits and project association."""
import base64
import binascii
import json
import time
from .. import db, entitlements
from ..errors import ApiError
from ..providers import registry
from ..providers.base import ProviderError
from . import designs,jobs


def generate(conn,ent,prompt,*,project_id=None,conversation_id=None,message_id=None,size='1024x1024',style='',reference_id=None):
    entitlements.require_feature(ent,'tools.images')
    if not prompt or len(prompt)>3800:raise ApiError(400,'Image prompt must be 1–3800 characters.','invalid_input')
    if size not in ('1024x1024','1536x1024','1024x1536','1792x1024','1024x1792'):
        raise ApiError(400,'Select a supported aspect/size; provider model support may vary.','invalid_input')
    if project_id:designs.owned(conn,ent,project_id)
    if conversation_id:
        from .chat import conversation
        cv=conversation(conn,ent['user_id'],conversation_id)
        if project_id and cv['project_id']!=project_id:raise ApiError(400,'Conversation/project association differs.','context_mismatch')
    p=registry.image_provider(conn)
    if not p.configured() or p.missing() or 'image_generation' not in p.supports:
        raise ProviderError('image_not_configured','Image generation is not configured. Set NEXUS_IMAGE_PROVIDER, NEXUS_IMAGE_MODEL and NEXUS_IMAGE_API_KEY in the server or Admin > AI Providers. No placeholder image was generated.',detail={'missing':p.missing()})
    original=prompt
    if reference_id:
        r=owned(conn,ent,reference_id)
        # Explicitly prompt-based regeneration, not pretending to edit pixels.
        prompt='New concept variation. Previous concept prompt: '+r['prompt'][:1200]+'\nRequested revision: '+prompt
    if style:prompt+='\nVisual style: '+str(style)[:160]
    if project_id:
        project=designs.view(designs.owned(conn,ent,project_id),conn)
        prompt+='\nProject requirements (concept reference, not a technical diagram): '+json.dumps(project['spec']['requirements'])[:1800]
    entitlements.consume(conn,ent,'image_generation',meta={'project_id':project_id})
    result=p.generate_image(prompt,size=size,n=1,quality=p.settings.get('quality','auto' if 'gpt-image' in p.model else 'standard'))[0]
    try:raw=base64.b64decode(result.b64,validate=True)
    except (binascii.Error,ValueError) as exc:raise ProviderError('bad_image_response','Provider returned invalid image bytes.') from exc
    if len(raw)>10*1024*1024:raise ProviderError('image_too_large','Generated image exceeds 10 MB storage limit.')
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):mime='image/png'
    elif raw.startswith(b'\xff\xd8\xff'):mime='image/jpeg'
    elif raw.startswith(b'RIFF') and raw[8:12]==b'WEBP':mime='image/webp'
    else:raise ProviderError('bad_image_response','Provider output is not a supported PNG/JPEG/WebP image; it was not saved.')
    iid=jobs.uid();meta={'provider':result.provider,'model':result.model,'revised_prompt':result.revised_prompt,
          'size':size,'kind':'concept_visual_not_verified_circuit','reference_id':reference_id,
          'variation_mode':'prompt_based_new_generation' if reference_id else None}
    conn.execute('INSERT INTO generated_images VALUES (?,?,?,?,?,?,?,?,?,?)',
                 (iid,ent['user_id'],project_id,conversation_id,message_id,original,mime,raw,json.dumps(meta),time.time()))
    db.audit(conn,ent['user_id'],'image.generated',iid,{'provider':result.provider,'project_id':project_id})
    return {'id':iid,'project_id':project_id,'conversation_id':conversation_id,'meta':meta,
            'label':'AI concept visual — not a verified circuit, PCB layout or buildability proof.'}


def owned(conn,ent,iid):
    r=conn.execute('SELECT * FROM generated_images WHERE id=? AND user_id=?',(iid,ent['user_id'])).fetchone()
    if not r:raise ApiError(404,'Image not found.','not_found')
    return r


def view(r,include_data=False):
    d={'id':r['id'],'project_id':r['project_id'],'conversation_id':r['conversation_id'],
       'prompt':r['prompt'],'mime':r['mime'],'meta':json.loads(r['meta_json']),'created_at':r['created_at']}
    if include_data:d['data_uri']='data:'+r['mime']+';base64,'+base64.b64encode(r['bytes']).decode()
    return d
