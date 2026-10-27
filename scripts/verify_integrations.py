#!/usr/bin/env python3
"""Opt-in, billable live acceptance. No fixtures and no production-data changes.

python scripts/verify_integrations.py --run-live --images
Results/answers are saved for manual relevance review. Missing credentials are
BLOCKED, never PASS. This script uses the real configured backend adapters and
services in a disposable DB so test conversations do not pollute user history.
"""
import argparse
import base64
import json
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nexus import config,db,entitlements
from nexus.providers import registry
from nexus.providers.base import ChatMessage,ProviderError
from nexus.services import chat,circuits,designs,images

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--run-live',action='store_true',help='Explicitly permit real provider calls and charges')
p.add_argument('--images',action='store_true',help='Also generate a real concept image (may incur charges)')
p.add_argument('--report',default='docs/LIVE_INTEGRATION_STATUS.json')
a=p.parse_args()
c=db.connect()
try:
    configured=registry.load(c);provider=registry.chat_provider(c)
    state={'checked_at':time.time(),'chat':{'provider':provider.name,'model':provider.model,'configured':provider.configured() and not provider.missing()},
           'image':{'configured':registry.image_provider(c).configured() and not registry.image_provider(c).missing()},'tests':[]}
finally:c.close()
if not a.run_live or not state['chat']['configured']:
    state['status']='BLOCKED';state['reason']='Explicit --run-live permission and configured online chat credentials/model are required. No model answers or images were fabricated.'
    Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(state,indent=2));print(state['reason']);raise SystemExit(2)
old=config.DB_PATH
with tempfile.TemporaryDirectory() as temp:
    config.DB_PATH=Path(temp)/'live-tests.sqlite';db.init_db();c=db.connect();db.set_setting(c,registry.SETTINGS_KEY,configured);now=time.time()
    c.execute("INSERT INTO users(email,name,password_hash,role,created_at,updated_at) VALUES ('acceptance@local','Live acceptance','disabled-auth','admin',?,?)",(now,now));uid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
    ent=entitlements.resolve(c,c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())
    try:
        questions=['Explain recursion in C with a small example and base case.',
          'Design an ESP32 smart irrigation system. Identify voltage/driver constraints and sensor calibration.',
          'Debug this Python NameError: print(total); total = 3. Explain the actual cause and fixes.',
          'Explain MQTT versus HTTP for intermittently connected sensors.',
          'Propose a startup to reduce food waste; label market assumptions and propose validation experiments.',
          'Design an unfamiliar sensor-based IoT concept; identify unsupported hardware rather than inventing pinouts.']
        answers=[]
        for q in questions:
            r=chat.synchronous(c,ent,q);answers.append(r['answer']);state['tests'].append({'question':q,'status':'real_response_received_manual_relevance_review_required','answer':r['answer'],'conversation_id':r['conversation_id']})
        state['distinct_responses']=len(set(answers))==len(answers)
        proj=designs.create(c,ent,'Live acceptance context',{'problem':'Test isolated project context'},circuits.build('esp32',['bme280']))
        cid=chat.create(c,ent,project_id=proj['id']);from nexus.services.jobs import uid as new_id
        c.execute("INSERT INTO messages VALUES (?,?,? ,?,'complete','{}',?)",(new_id(),cid,'user','Remember the test tag BLUE-HERON-729.',time.time()))
        system,history=chat.assemble(c,ent,cid);history.append(ChatMessage('user','What exact test tag did I ask you to remember?'))
        r=registry.chat_provider(c).chat(history,system=system);state['history']={'status':'response_received','answer':r.text,'tag_present':'BLUE-HERON-729' in r.text}
        if a.images:
            if not state['image']['configured']:state['image']['status']='BLOCKED: image provider not configured'
            else:
                im=images.generate(c,ent,'Clean industrial concept rendering of an environmental sensor enclosure. Concept only, no wiring.',project_id=proj['id'],conversation_id=cid)
                stored=images.owned(c,ent,im['id']);filename=Path(a.report).with_suffix('.generated.png');filename.write_bytes(stored['bytes'])
                state['image'].update(status='real_provider_bytes_received_and_project_conversation_association_checked',project_id=stored['project_id'],conversation_id=stored['conversation_id'],file=str(filename))
        state['status']='RESPONSES_RECEIVED_REVIEW_REQUIRED'
    except ProviderError as exc:
        state['status']='FAILED';state['error']=exc.payload()
    finally:c.close();config.DB_PATH=old
Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(state,indent=2));print('Status:',state['status'],'Report:',a.report)
raise SystemExit(0 if state['status']=='RESPONSES_RECEIVED_REVIEW_REQUIRED' else 1)
