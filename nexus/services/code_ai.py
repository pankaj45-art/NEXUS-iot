"""Online project-specific firmware proposals. Never execute model/user source."""
import difflib
import json
import re
from .. import entitlements
from ..errors import ApiError
from ..providers import registry
from ..providers.base import ChatMessage,ProviderError
from . import circuits,designs


def propose(conn,ent,pid,request):
    entitlements.require_feature(ent,'tools.code_engineer')
    p=designs.view(designs.owned(conn,ent,pid),conn);spec=p['spec'];provider=registry.chat_provider(conn)
    if not provider.configured() or provider.missing():raise ProviderError('provider_not_configured','Online firmware engineering needs a configured chat provider. Deterministic driver rebuild/static checks remain separate functions.')
    if not str(request).strip():raise ApiError(400,'Describe the code change or algorithm.','invalid_input')
    entitlements.consume(conn,ent,'tool_call',meta={'tool':'ai_code','project_id':pid})
    block=circuits.managed(spec['circuit'],conn)
    system='''You are a firmware engineer. Propose a complete Arduino C++ source file
for the saved project, fulfilling the requested change where feasible. Preserve
unrelated user code. Return JSON only with keys code (complete source string),
summary, libraries (array of real dependency names), manual_work (array).
Never invent an unsupported sensor driver/pinout or claim compilation, simulation,
or physical tests. Keep exactly the supplied NEXUS managed pin region. Use its
pin constants in every hardware driver; do not introduce independent literal pin
assignments. No real credentials. Clearly mark calibration/broker placeholders,
errors/retries, safe output defaults and unimplemented requirements. If a driver or
algorithm cannot be justified, say so in manual_work instead of faking readings.'''
    prompt={'request':str(request)[:10000],'project_id':pid,'revision':p['revision'],
            'requirements':spec['requirements'],'circuit':spec['circuit'],'exact_managed_region':block,
            'existing_source':spec['firmware']['code'],'references':spec['guide']['references']}
    r=provider.chat([ChatMessage('user',json.dumps(prompt))],system=system,max_tokens=6000,temperature=.2)
    text=re.sub(r'^```(?:json)?\s*|\s*```$','',r.text.strip())
    try:data=json.loads(text)
    except ValueError as exc:raise ProviderError('invalid_code_response','Provider did not return a valid source proposal. Nothing was overwritten; retry.',retryable=True) from exc
    if not isinstance(data,dict) or not isinstance(data.get('code'),str) or len(data['code'])>120000:
        raise ProviderError('invalid_code_response','Expected a complete code string within 120,000 characters. Nothing applied.')
    if block not in data['code']:
        raise ProviderError('pin_config_mismatch','Model changed or removed the canonical pin region. Proposal rejected; saved source is unchanged.')
    diff='\n'.join(difflib.unified_diff(spec['firmware']['code'].splitlines(),data['code'].splitlines(),fromfile='saved/firmware.ino',tofile='AI-proposal/firmware.ino',lineterm=''))
    libs=data.get('libraries',[])
    return {'project_id':pid,'source_revision':p['revision'],'code':data['code'],
            'libraries':[str(x)[:150] for x in libs[:40]] if isinstance(libs,list) else [],
            'summary':str(data.get('summary',''))[:3000], 'manual_work':data.get('manual_work',[]),
            'diff':diff,'provider':r.provider,'model':r.model,'status':'proposal_not_compiled_not_applied',
            'warning':'Model source must be reviewed and compiled locally. Applying requires explicit confirmation; no test result is implied.'}
