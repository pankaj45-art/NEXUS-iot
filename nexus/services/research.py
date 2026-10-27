"""Optional real search and explicit curated references; no invented citations."""
import json
import urllib.error
import urllib.parse
import urllib.request
from .. import ai
from ..providers import registry
from ..providers.base import ProviderError


def search(conn,query):
    cfg=registry._decrypt(registry.load(conn)['web_search']);provider=cfg.get('provider','none')
    if not cfg.get('enabled') or provider=='none':
        return {'mode':'curated_only','web_search_performed':False,'sources':ai.references_for(query,8),
                'limitation':'Web search is not configured. These are matched real documentation links, not live search results or a novelty/patent search.'}
    try:
        if provider=='tavily':
            if not cfg.get('api_key'):raise ProviderError('missing_credentials','Web search requires NEXUS_SEARCH_API_KEY.')
            base=(cfg.get('base_url') or 'https://api.tavily.com').rstrip('/')
            req=urllib.request.Request(base+'/search',data=json.dumps({'api_key':cfg['api_key'],'query':query[:2000],'max_results':6,'include_answer':False}).encode(),headers={'Content-Type':'application/json'},method='POST')
            with urllib.request.urlopen(req,timeout=15) as resp:data=json.loads(resp.read(2_000_000))
            results=data.get('results',[])
        elif provider=='searxng':
            if not cfg.get('base_url'):raise ProviderError('missing_credentials','Set the URL of a server-controlled SearXNG instance.')
            req=urllib.request.Request(cfg['base_url'].rstrip('/')+'/search?'+urllib.parse.urlencode({'q':query[:2000],'format':'json'}),headers={'User-Agent':'NEXUS-IoT/2'})
            with urllib.request.urlopen(req,timeout=15) as resp:data=json.loads(resp.read(2_000_000))
            results=data.get('results',[])[:6]
        else:raise ProviderError('unknown_provider','Supported search providers: tavily, searxng, none.')
    except ProviderError:raise
    except urllib.error.HTTPError as exc:
        raise ProviderError('search_failed','Search provider returned HTTP '+str(exc.code)+'. Verify credentials/quota.',status=exc.code,retryable=exc.code>=429) from exc
    except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
        raise ProviderError('search_failed','Search provider unavailable ('+type(exc).__name__+'). No fabricated search results returned.',retryable=True) from exc
    sources=[]
    for i,r in enumerate(results):
        url=r.get('url','');p=urllib.parse.urlparse(url)
        if p.scheme not in ('http','https'):continue
        sources.append({'id':'WEB-'+str(i+1),'title':str(r.get('title',''))[:300],'url':url,'excerpt':str(r.get('content',''))[:3000]})
    return {'mode':'live_search','web_search_performed':True,'provider':provider,'sources':sources,
            'limitation':'Search snippets are external evidence, not verification of physical designs or global novelty. Follow original sources and dates.'}
