#!/usr/bin/env python3
"""Protected local CLI: configure a provider without putting secrets in history."""
import argparse
import getpass
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nexus import db,config
from nexus.providers import registry

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--kind',choices=['chat','image','web_search'],default='chat')
p.add_argument('--provider',required=True,choices=['openai_compatible','gemini','ollama','tavily','searxng','none'])
p.add_argument('--model',default='')
p.add_argument('--base-url',default='')
a=p.parse_args()
if a.kind=='chat' and a.provider not in ('openai_compatible','gemini','ollama','none'):p.error('Unsupported chat adapter')
if a.kind=='image' and a.provider not in ('openai_compatible','none'):p.error('Unsupported image adapter')
if a.kind=='web_search' and a.provider not in ('tavily','searxng','none'):p.error('Unsupported search adapter')
if a.kind!='web_search' and a.provider!='none' and not a.model:p.error('--model is required')
key=''
if a.provider in ('openai_compatible','gemini','tavily'):key=getpass.getpass('Provider API key (blank keeps existing): ').strip()
patch={'provider':a.provider,'enabled':a.provider!='none'}
if a.model:patch['model']=a.model
if a.base_url:patch['base_url']=a.base_url
elif a.provider=='gemini':patch['base_url']='https://generativelanguage.googleapis.com/v1beta'
elif a.provider=='ollama':patch['base_url']=config.OLLAMA_BASE_URL
if key:patch['api_key']=key
db.init_db();c=db.connect()
try:
    registry.save(c,{a.kind:patch})
    db.audit(c,None,'cli.provider_config',a.kind,{'provider':a.provider})
    print('Saved',a.kind,'provider:',a.provider,'model:',a.model or '(search)')
    print('Credentials are encrypted in the database. No key is printed.')
    print('Use Admin > AI Providers > Test chat connection (a real, small billable call).')
finally:c.close()
