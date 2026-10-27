"""Workstation integration tests. External API fixtures are NOT live-provider proof."""
import base64
import copy
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

from nexus import api,config,db,entitlements
from nexus.providers import registry
from nexus.providers.base import ChatMessage,ProviderError
from nexus.providers.openai_compat import OpenAICompatProvider
from nexus.services import chat,circuits,designs,images,jobs
from nexus.security import pbkdf2
from test_nexus import call

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jbc8AAAAASUVORK5CYII=')

class FixtureProvider(BaseHTTPRequestHandler):
    """Explicit test double: echoes payload/history; never used by production."""
    seen=[];failure=0;failure_code=None;failure_message=None;invalid_json=False;unsupported=False;delay_seconds=0;request_seen=threading.Event()
    def log_message(self,*args):pass
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.seen.append({'path':self.path,'payload':data,'auth':self.headers.get('Authorization'),'google_key':self.headers.get('x-goog-api-key')})
        self.request_seen.set()
        if self.delay_seconds:time.sleep(self.delay_seconds)
        if self.failure:
            body=json.dumps({'error':{'message':self.failure_message or 'fixture failure: model/key/quota','code':self.failure_code}}).encode();self.send_response(self.failure);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if self.path.endswith('/images/generations'):
            self.respond({'data':[{'b64_json':base64.b64encode(PNG).decode(),'revised_prompt':'fixture image, not real generation'}]});return
        native=':generateContent' in self.path or ':streamGenerateContent' in self.path
        if native:
            data['messages']=([{'role':'system','content':'\n'.join(p.get('text','') for p in data.get('systemInstruction',{}).get('parts',[]))}] if data.get('systemInstruction') else []) + [{'role':'assistant' if m['role']=='model' else 'user','content':'\n'.join(p.get('text','') for p in m.get('parts',[]))} for m in data.get('contents',[])]
            data['stream']=':streamGenerateContent' in self.path
        messages=data.get('messages',[]);system=messages[0]['content'] if messages and messages[0]['role']=='system' else '';last=messages[-1]['content'] if messages else ''
        if 'You are a firmware engineer' in system:
            request=json.loads(last)
            content=json.dumps({'code':request['existing_source']+'\n// TEST FIXTURE requested change: '+request['request']+'\n', 'summary':'Fixture source proposal; not model quality proof','libraries':[],'manual_work':['Compile and validate on real hardware.']})
        elif 'JSON object only' in system:
            user=json.loads(last)
            obj={'title':'Novel fixture design - '+user['idea'][:50],'problem':user['idea'],'board':'esp32','components':['bme280','led'],'architecture':'BME280 to ESP32 to LED/serial','requirements':['document assumptions'],'assumptions':['Fixture proposal, not a real model'],'unsupported_components':[{'name':'new spectral detector','reason':'No definition'}] if self.unsupported else [],'hypotheses':['Requires user algorithm implementation']}
            content='not valid json' if self.invalid_json else json.dumps(obj)
        else:content='[TEST FIXTURE] Received: '+last+' | history_messages='+str(len(messages))
        if native:
            def chunk(text,done=False):
                return {'modelVersion':'fixture-only','candidates':[{'content':{'role':'model','parts':[{'text':text}]},**({'finishReason':'STOP'} if done else {})}],'usageMetadata':{'totalTokenCount':10}}
            if data.get('stream'):
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','close');self.end_headers()
                for text,done in [(content[:len(content)//2],False),(content[len(content)//2:],True)]:
                    self.wfile.write(('data: '+json.dumps(chunk(text,done))+'\n\n').encode());self.wfile.flush()
                self.close_connection=True
            else:self.respond(chunk(content,True))
            return
        if data.get('stream'):
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','close');self.end_headers()
            for token in [content[:len(content)//2],content[len(content)//2:]]:
                self.wfile.write(('data: '+json.dumps({'choices':[{'delta':{'content':token}}]})+'\n\n').encode());self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n');self.close_connection=True
        else:self.respond({'model':'fixture-only','choices':[{'message':{'content':content},'finish_reason':'stop'}],'usage':{'total_tokens':10}})
    def respond(self,data):
        body=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

class WorkstationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.real_db=config.DB_PATH;config.DB_PATH=Path(cls.tmp.name)/'ws.sqlite';db.init_db()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),FixtureProvider);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.base='http://127.0.0.1:'+str(cls.server.server_port)+'/v1'
        c=db.connect();now=time.time();cls.uids={}
        for name,role in [('free','free'),('pro','pro'),('other','free'),('admin','admin')]:
            cur=c.execute('INSERT INTO users(email,name,password_hash,role,created_at,updated_at) VALUES (?,?,?,?,?,?)',(name+'@ws.local',name,pbkdf2('Workstation2026!x'),role,now,now));uid=cur.lastrowid;cls.uids[name]=uid
            c.execute('INSERT INTO subscriptions(user_id,plan,status,provider,started_at,expires_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',(uid,'pro' if name=='pro' else 'free','active' if name=='pro' else 'inactive','manual',now,now+3600,now,now))
        c.close();cls.sessions={}
        for name in cls.uids:
            s,_,d,sess=call('POST','/api/auth/login',{'email':name+'@ws.local','password':'Workstation2026!x'});assert s==200,d;cls.sessions[name]=sess
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
        for t in threading.enumerate():
            if t.name.startswith('nexus-'):t.join(timeout=2)
        config.DB_PATH=cls.real_db;cls.tmp.cleanup()
    def setUp(self):
        self.c=db.connect();self.c.execute("DELETE FROM usage_events WHERE kind='provider_check'");FixtureProvider.delay_seconds=0;FixtureProvider.request_seen.clear();FixtureProvider.failure=0;FixtureProvider.failure_code=None;FixtureProvider.failure_message=None;FixtureProvider.invalid_json=False;FixtureProvider.unsupported=False;FixtureProvider.seen.clear()
        registry.save(self.c,{'chat':{'provider':'none','enabled':True},'image':{'provider':'none','enabled':False},'web_search':{'provider':'none','enabled':False}})
    def tearDown(self):self.c.close()
    def ent(self,name):return entitlements.resolve(self.c,self.c.execute('SELECT * FROM users WHERE id=?',(self.uids[name],)).fetchone())
    def configured(self,kind='chat',stream=True):
        registry.save(self.c,{kind:{'provider':'openai_compatible','base_url':self.base,'model':'fixture-model','api_key':'TEST-ONLY-KEY','enabled':True,'max_retries':0,'capabilities':{'streaming':stream}}})
    def req(self,method,path,body=None,user='pro'):
        s,_,d,_=call(method,path,body,session=self.sessions[user]);return s,d
    def create(self,name='A irrigation',parts=None):
        s,d=self.req('POST','/api/designs',{'name':name,'components':parts or ['soil_cap','pump'],'requirements':{'problem':name}});self.assertEqual(s,201,d);return d
    def wait(self,jid,user='pro'):
        end=time.monotonic()+8
        while time.monotonic()<end:
            s,j=self.req('GET','/api/jobs/'+jid,user=user)
            if j['state'] in jobs.TERMINAL:return j
            threading.Event().wait(.01)
        self.fail('job timed out')

    def test_missing_provider_is_error_not_generic_answer(self):
        s,d=self.req('POST','/api/assistant',{'question':'A new question about recursion'},'free')
        self.assertEqual(s,503);self.assertEqual(d['error']['code'],'provider_not_configured');self.assertNotIn('result',d)
        cid=chat.create(self.c,self.ent('free'));r=chat.add(self.c,self.ent('free'),cid,'Explain a programming idea');j=self.wait(r['job_id'],'free')
        self.assertEqual(j['state'],'failed');self.assertEqual(j['error']['code'],'provider_not_configured');self.assertEqual(FixtureProvider.seen,[])

    def test_quick_connect_activates_key_and_free_online_chat(self):
        key='TEST-ONLY-QUICK-CONNECT-SECRET'
        s,r=self.req('POST','/api/admin/providers/connect',{'api_key':key,'base_url':self.base+'/chat/completions','model':'fixture-model'},'admin')
        self.assertEqual(s,200,r);self.assertTrue(r['connected']);self.assertFalse(r['requires_restart']);self.assertTrue(r['last_test']['recent']);self.assertNotIn(key,json.dumps(r))
        self.assertEqual(registry.chat_config(self.c)['base_url'],self.base)
        self.assertTrue(FixtureProvider.seen[-1]['payload']['stream'])
        s,r=self.req('POST','/api/assistant',{'question':'An online free-tier question'},'free');self.assertEqual(s,200,r);self.assertIn('[TEST FIXTURE]',r['result']['answer'])
        s,r=self.req('GET','/api/ai/status','',user='admin');self.assertTrue(r['chat']['last_test']['ok'])
        settings=''.join(row['value_json'] for row in self.c.execute('SELECT value_json FROM settings'))
        self.assertNotIn(key,settings)

    def test_quick_connect_failure_preserves_previous_settings_and_masks_key(self):
        self.configured();before=registry.chat_config(self.c);FixtureProvider.failure=401
        newkey='TEST-ONLY-REJECTED-SECRET'
        s,r=self.req('POST','/api/admin/providers/connect',{'provider':'openai_compatible','base_url':self.base,'model':'bad-model','api_key':newkey},'admin')
        self.assertEqual(s,502,r);self.assertEqual(r['error']['code'],'auth_failed');self.assertFalse(r['error']['detail']['saved']);self.assertNotIn(newkey,json.dumps(r))
        self.assertEqual(before,registry.chat_config(self.c))

    def test_quick_save_without_test_never_claims_connected(self):
        FixtureProvider.failure=503
        s,r=self.req('POST','/api/admin/providers/connect',{'provider':'openai_compatible','base_url':self.base,'api_key':'TEST-ONLY-SAVE-KEY','model':'fixture-model','verify':False},'admin')
        self.assertEqual(s,200,r);self.assertTrue(r['saved']);self.assertFalse(r['connected']);self.assertIsNone(r['last_test']);self.assertEqual(FixtureProvider.seen,[])
        s,r=self.req('GET','/api/ai/status',user='admin');self.assertTrue(r['chat']['configured']);self.assertIsNone(r['chat']['last_test'])

    def test_quick_connect_blank_reuses_key_and_enables_saved_disabled_provider(self):
        self.configured();registry.save(self.c,{'chat':{'enabled':False}})
        s,r=self.req('POST','/api/admin/providers/connect',{'provider':'openai_compatible','api_key':'','base_url':self.base,'model':'fixture-model','streaming':False},'admin')
        self.assertEqual(s,200,r);self.assertTrue(r['connected']);self.assertTrue(registry.chat_config(self.c)['enabled']);self.assertEqual(registry.chat_config(self.c)['api_key'],'TEST-ONLY-KEY');self.assertFalse(FixtureProvider.seen[-1]['payload']['stream'])

    def test_quick_connect_still_enforces_admin_and_csrf(self):
        body={'api_key':'TEST-ONLY-KEY','base_url':self.base,'model':'fixture-model'}
        for name in ('free','pro'):
            s,r=self.req('POST','/api/admin/providers/connect',body,name);self.assertEqual(s,403,r)
        s,_,r,_=call('POST','/api/admin/providers/connect',body,session=self.sessions['admin'],csrf=False);self.assertEqual(s,403,r);self.assertEqual(FixtureProvider.seen,[])

    def test_quick_connect_optional_images_not_falsely_verified(self):
        s,r=self.req('POST','/api/admin/providers/connect',{'api_key':'TEST-ONLY-SHARED','base_url':self.base,'model':'fixture-model','enable_images':True,'image_model':'fixture-image'},'admin')
        self.assertEqual(s,200,r);self.assertTrue(r['images_configured']);self.assertFalse(r['images_verified'])
        self.assertEqual(registry.image_provider(self.c).model,'fixture-image');self.assertFalse(any(x['path'].endswith('/images/generations') for x in FixtureProvider.seen))

    def test_quick_connect_test_identity_invalidates_when_model_changes(self):
        s,r=self.req('POST','/api/admin/providers/connect',{'api_key':'TEST-ONLY-KEY','base_url':self.base,'model':'fixture-model'},'admin');self.assertEqual(s,200,r)
        s,r=self.req('PATCH','/api/admin/providers',{'chat':{'model':'changed-model'}},'admin');self.assertEqual(s,200,r)
        s,r=self.req('GET','/api/ai/status',user='admin');self.assertIsNone(r['chat']['last_test'])

    def test_quick_connect_query_session_body_csrf_fallback(self):
        s,_,login,_=call('POST','/api/auth/login',{'email':'admin@ws.local','password':'Workstation2026!x'});self.assertEqual(s,200)
        s,_,r,_=call('POST','/api/admin/providers/connect?nx_session='+login['session_token'],{'api_key':'TEST-ONLY-PREVIEW','base_url':self.base,'model':'fixture-model','nx_csrf':login['csrf']})
        self.assertEqual(s,200,r);self.assertTrue(r['connected'])

    def test_quick_connect_rejects_missing_key_and_remote_plaintext_url(self):
        for body,code in [({'provider':'openai_compatible'},'api_key_required'),({'api_key':'TEST-ONLY-KEY','base_url':'http://example.com/v1'},'insecure_provider_url')]:
            s,r=self.req('POST','/api/admin/providers/connect',body,'admin');self.assertEqual(s,400,r);self.assertEqual(r['error']['code'],code)
        self.assertEqual(FixtureProvider.seen,[])

    def test_gemini_quick_connect_streaming_encryption_and_free_chat(self):
        key='TEST-ONLY-GEMINI-KEY'
        before_image=registry.load(self.c)['image']
        s,r=self.req('POST','/api/admin/providers/connect',{'provider':'gemini','api_key':key,'base_url':self.base,'model':'gemini-3.8-flash'},'admin')
        self.assertEqual(s,200,r);self.assertTrue(r['connected']);self.assertEqual(r['provider'],'gemini');self.assertNotIn(key,json.dumps(r))
        sent=FixtureProvider.seen[-1];self.assertEqual(sent['google_key'],key);self.assertEqual(sent['path'],'/v1/models/gemini-3.8-flash:streamGenerateContent?alt=sse');self.assertEqual(sent['payload']['generationConfig']['thinkingConfig']['thinkingLevel'],'LOW');self.assertGreaterEqual(sent['payload']['generationConfig']['maxOutputTokens'],1280)
        self.assertEqual(before_image,registry.load(self.c)['image']);self.assertFalse(registry.chat_provider(self.c).capabilities()['image_generation'])
        self.assertNotIn(key,json.dumps(registry.public_view(self.c)));self.assertNotIn(key,db.get_setting(self.c,registry.SETTINGS_KEY)['chat']['api_key_encrypted'])
        s,r=self.req('POST','/api/assistant',{'question':'A general Gemini transport question'},'free');self.assertEqual(s,200,r);self.assertEqual(r['result']['provider'],'gemini');self.assertIn('[TEST FIXTURE]',r['result']['answer'])

    def test_gemini_defaults_save_only_and_no_false_image_activation(self):
        s,r=self.req('POST','/api/admin/providers/connect',{'provider':'gemini','api_key':'TEST-ONLY-GEMINI-DEFAULT','verify':False},'admin')
        self.assertEqual(s,200,r);self.assertFalse(r['connected']);self.assertFalse(r['images_configured']);self.assertEqual(FixtureProvider.seen,[])
        c=registry.chat_config(self.c);self.assertEqual(c['base_url'],'https://generativelanguage.googleapis.com/v1beta');self.assertEqual(c['model'],'gemini-3.5-flash-lite')
        s,r=self.req('GET','/api/ai/status',user='admin');self.assertEqual(r['chat']['provider'],'gemini');self.assertIsNone(r['chat']['last_test']);self.assertFalse(r['image']['configured'])

    def test_gemini_same_scope_blank_key_nonstream_and_health(self):
        registry.save(self.c,{'chat':{'provider':'gemini','base_url':self.base,'model':'gemini-3.5-flash-lite','api_key':'TEST-ONLY-GEMINI-REUSE','enabled':False}})
        s,r=self.req('POST','/api/admin/providers/connect',{'provider':'gemini','api_key':'','streaming':False},'admin')
        self.assertEqual(s,200,r);self.assertTrue(r['connected']);self.assertFalse(FixtureProvider.seen[-1]['payload']['stream']);self.assertEqual(FixtureProvider.seen[-1]['google_key'],'TEST-ONLY-GEMINI-REUSE')
        h=registry.health(self.c,force=True);self.assertTrue(h['online']);self.assertEqual(h['chat']['provider'],'gemini')

    def test_provider_switch_cannot_reuse_other_vendor_or_endpoint_key(self):
        self.configured();before=registry.chat_config(self.c)
        for provider,base in [('gemini',self.base),('openai_compatible',self.base+'/another-endpoint')]:
            s,r=self.req('POST','/api/admin/providers/connect',{'provider':provider,'base_url':base,'model':'gemini-3.8-flash'},'admin')
            self.assertEqual(s,400,r);self.assertEqual(r['error']['code'],'api_key_required');self.assertEqual(before,registry.chat_config(self.c))
        self.assertEqual(FixtureProvider.seen,[])

    def test_gemini_advanced_switch_clears_old_key_and_uses_google_defaults(self):
        self.configured()
        s,r=self.req('PATCH','/api/admin/providers',{'chat':{'provider':'gemini','capabilities':{'streaming':True}}},'admin')
        self.assertEqual(s,200,r);self.assertFalse(r['config']['chat']['api_key_set']);self.assertEqual(r['config']['chat']['model'],'gemini-3.5-flash-lite');self.assertEqual(r['config']['chat']['base_url'],'https://generativelanguage.googleapis.com/v1beta')
        self.assertTrue(registry.chat_provider(self.c).capabilities()['chat']);self.assertIn('api_key',registry.chat_provider(self.c).missing());self.assertEqual(FixtureProvider.seen,[])

    def test_gemini_rejects_wrong_endpoint_and_image_capability(self):
        for body,code in [({'provider':'gemini','api_key':'TEST-ONLY-KEY','base_url':'https://api.openai.com/v1'},'invalid_provider_url'),({'provider':'gemini','api_key':'TEST-ONLY-KEY','enable_images':True},'unsupported_capability')]:
            s,r=self.req('POST','/api/admin/providers/connect',body,'admin');self.assertEqual(s,400,r);self.assertEqual(r['error']['code'],code)
        from nexus.providers.gemini import GeminiProvider
        p=GeminiProvider({'base_url':'https://example.com/v1','model':'gemini-3.8-flash','api_key':'TEST-ONLY-KEY'})
        with self.assertRaises(ProviderError) as e:p.chat([ChatMessage('user','never send to another host')])
        self.assertEqual(e.exception.code,'invalid_provider_url')
        with self.assertRaises(ProviderError) as e:p.generate_image('never send an image request')
        self.assertEqual(e.exception.code,'unsupported_capability');self.assertEqual(FixtureProvider.seen,[])

    def test_failed_gemini_test_preserves_openai_settings(self):
        self.configured();before=registry.chat_config(self.c);FixtureProvider.failure=401
        s,r=self.req('POST','/api/admin/providers/connect',{'provider':'gemini','base_url':self.base,'model':'gemini-3.8-flash','api_key':'TEST-ONLY-REJECTED-GEMINI'},'admin')
        self.assertEqual(s,502,r);self.assertEqual(r['error']['provider'],'gemini');self.assertTrue(r['error']['detail']['previous_configuration_preserved']);self.assertEqual(before,registry.chat_config(self.c))

    def test_exhausted_credits_is_not_a_retryable_rate_limit(self):
        self.configured();registry.save(self.c,{'chat':{'max_retries':2}})
        FixtureProvider.failure=429;FixtureProvider.failure_code='credit_balance_exhausted';FixtureProvider.failure_message='You have no credits remaining.'
        s,r=self.req('POST','/api/assistant',{'question':'Do not retry exhausted balances'},'free')
        self.assertEqual(s,429,r);self.assertEqual(r['error']['code'],'quota_exhausted');self.assertFalse(r['error']['retryable']);self.assertEqual(len(FixtureProvider.seen),1)

    def test_gemini_environment_credential_separation(self):
        import subprocess,sys
        names=('GEMINI_API_KEY','GOOGLE_API_KEY','OPENAI_API_KEY','NEXUS_AI_API_KEY','NEXUS_AI_PROVIDER','NEXUS_AI_BASE_URL','OPENAI_BASE_URL','NEXUS_AI_MODEL','NEXUS_IMAGE_API_KEY','NEXUS_IMAGE_BASE_URL','NEXUS_IMAGE_PROVIDER')
        with tempfile.TemporaryDirectory() as td:
            env={k:v for k,v in os.environ.items() if k not in names};env.update(NEXUS_DATA_DIR=td,NEXUS_AI_PROVIDER='gemini',GEMINI_API_KEY='TEST-GEMINI-ENV',OPENAI_API_KEY='TEST-OPENAI-ENV',OPENAI_BASE_URL='https://other.example/v1')
            script='from nexus import config; from nexus.providers import registry; import json; print(json.dumps(dict(p=config.AI_ENV_PROVIDER,k=config.AI_ENV_KEY,b=config.AI_ENV_BASE,m=config.AI_ENV_MODEL,i=registry._decrypt(registry.defaults()["image"])["api_key"])))'
            r=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,check=True);d=json.loads(r.stdout)
            self.assertEqual(d['p'],'gemini');self.assertEqual(d['k'],'TEST-GEMINI-ENV');self.assertEqual(d['i'],'TEST-OPENAI-ENV');self.assertEqual(d['m'],'gemini-3.5-flash-lite');self.assertIn('generativelanguage.googleapis.com',d['b'])

    def test_async_connect_ack_is_fast_and_job_contains_no_secret(self):
        key='TEST-ONLY-ASYNC-KEY';FixtureProvider.delay_seconds=.35;t=time.monotonic()
        s,r=self.req('POST','/api/admin/providers/connect/start',{'provider':'gemini','base_url':self.base,'model':'gemini-3.5-flash-lite','api_key':key},'admin')
        self.assertEqual(s,202,r);self.assertLess(time.monotonic()-t,.25);self.assertFalse(r['saved']);self.assertFalse(r['connected'])
        j=self.wait(r['job_id'],'admin');self.assertEqual(j['state'],'complete',j);self.assertTrue(j['output']['connected']);self.assertEqual(registry.chat_config(self.c)['provider'],'gemini')
        for table,column in [('ai_jobs','output_json'),('ai_jobs','error_json'),('ai_job_events','data_json'),('audit_logs','detail_json')]:
            self.assertNotIn(key,' '.join(str(x[0]) for x in self.c.execute('SELECT '+column+' FROM '+table)))
        s,r=self.req('GET','/api/jobs/'+j['id'],user='other');self.assertEqual(s,404)

    def test_async_connect_cancel_does_not_replace_saved_settings(self):
        self.configured();before=registry.chat_config(self.c);FixtureProvider.delay_seconds=.3
        s,r=self.req('POST','/api/admin/providers/connect/start',{'provider':'gemini','base_url':self.base,'model':'gemini-3.5-flash-lite','api_key':'TEST-ONLY-CANCEL'},'admin');self.assertEqual(s,202,r)
        s,r2=self.req('POST','/api/jobs/'+r['job_id']+'/cancel',{},'admin');self.assertEqual(s,200,r2)
        j=self.wait(r['job_id'],'admin');self.assertEqual(j['state'],'cancelled',j);self.assertEqual(before,registry.chat_config(self.c))

    def test_async_failed_connect_preserves_settings_and_reports_typed_error(self):
        self.configured();before=registry.chat_config(self.c);FixtureProvider.failure=401
        s,r=self.req('POST','/api/admin/providers/connect/start',{'provider':'gemini','base_url':self.base,'model':'gemini-3.5-flash-lite','api_key':'TEST-ONLY-FAIL-ASYNC'},'admin');self.assertEqual(s,202,r)
        j=self.wait(r['job_id'],'admin');self.assertEqual(j['state'],'failed');self.assertEqual(j['error']['code'],'auth_failed');self.assertTrue(j['error']['detail']['previous_configuration_preserved']);self.assertEqual(before,registry.chat_config(self.c))

    def test_async_does_not_overwrite_newer_configuration(self):
        self.configured();FixtureProvider.delay_seconds=.4
        s,r=self.req('POST','/api/admin/providers/connect/start',{'provider':'gemini','base_url':self.base,'model':'gemini-3.5-flash-lite','api_key':'TEST-ONLY-STALE'},'admin');self.assertEqual(s,202,r);self.assertTrue(FixtureProvider.request_seen.wait(2))
        registry.save(self.c,{'chat':{'model':'newer-manual-model'}})
        j=self.wait(r['job_id'],'admin');self.assertEqual(j['state'],'failed',j);self.assertEqual(j['error']['code'],'configuration_changed');self.assertEqual(registry.chat_config(self.c)['model'],'newer-manual-model')

    def test_async_connect_admin_csrf_and_duplicate_guards(self):
        payload={'provider':'gemini','base_url':self.base,'model':'gemini-3.5-flash-lite','api_key':'TEST-ONLY-DUPLICATE'}
        s,r=self.req('POST','/api/admin/providers/connect/start',payload,'pro');self.assertEqual(s,403)
        admin=self.sessions['admin'];bad=dict(admin);bad['nexus_csrf']='bad';s,_,r,_=call('POST','/api/admin/providers/connect/start',payload,session=bad);self.assertEqual(s,403)
        FixtureProvider.delay_seconds=.4;s,r=self.req('POST','/api/admin/providers/connect/start',payload,'admin');self.assertEqual(s,202,r)
        s,r2=self.req('POST','/api/admin/providers/connect/start',payload,'admin');self.assertEqual(s,409,r2);self.assertEqual(r2['error']['code'],'connection_busy')
        self.assertEqual(self.wait(r['job_id'],'admin')['state'],'complete')

    def test_async_saved_health_is_background_and_read_only(self):
        self.configured();before=registry.chat_config(self.c);FixtureProvider.delay_seconds=.25;t=time.monotonic()
        s,r=self.req('POST','/api/admin/providers/test/start',{},'admin');self.assertEqual(s,202,r);self.assertLess(time.monotonic()-t,.2)
        j=self.wait(r['job_id'],'admin');self.assertEqual(j['state'],'complete',j);self.assertTrue(j['output']['online']);self.assertEqual(before,registry.chat_config(self.c))

    def test_gemini_legacy_compatible_url_reuses_key_without_vendor_switch(self):
        registry.save(self.c,{'chat':{'provider':'gemini','base_url':'https://generativelanguage.googleapis.com/v1beta/openai','api_key':'TEST-ONLY-LEGACY','model':'gemini-3.8-flash'}})
        from nexus.services.connections import _prepare
        plan=_prepare(self.c,self.ent('admin'),{'provider':'gemini','base_url':'https://generativelanguage.googleapis.com/v1beta','model':'gemini-3.5-flash-lite'})
        self.assertEqual(plan['candidate']['api_key'],'TEST-ONLY-LEGACY')

    def test_real_http_adapter_payloads_differ_and_free_online_is_not_gated(self):
        self.configured();outputs=[]
        # Payload propagation, NOT a model-relevance/online-provider acceptance test.
        for question in ('different topic one '+jobs.uid(),'another question '+jobs.uid()):
            s,d=self.req('POST','/api/assistant',{'question':question},'free');self.assertEqual(s,200,d);outputs.append(d['result']['answer'])
            self.assertEqual(FixtureProvider.seen[-1]['payload']['messages'][-1]['content'],question)
        self.assertNotEqual(*outputs)
        self.assertTrue(all(x['auth']=='Bearer TEST-ONLY-KEY' for x in FixtureProvider.seen))

    def test_provider_http_failures_are_truthful(self):
        self.configured()
        for status,code in ((401,'auth_failed'),(404,'invalid_model'),(429,'rate_limited'),(503,'provider_unavailable')):
            FixtureProvider.failure=status
            with self.assertRaises(ProviderError) as e:registry.chat_provider(self.c).chat([ChatMessage('user','question')])
            self.assertEqual(e.exception.code,code);self.assertNotIn('offline',e.exception.message)

    def test_streaming_history_and_durable_messages(self):
        self.configured();cid=chat.create(self.c,self.ent('pro'))
        r=chat.add(self.c,self.ent('pro'),cid,'First question unique');j=self.wait(r['job_id']);self.assertEqual(j['state'],'complete',j)
        self.assertTrue(any(e['kind']=='delta' for e in j['events']))
        r2=chat.add(self.c,self.ent('pro'),cid,'Remember my first question?');j2=self.wait(r2['job_id']);self.assertEqual(j2['state'],'complete')
        payload=FixtureProvider.seen[-1]['payload']['messages'];self.assertTrue(any(m['content']=='First question unique' for m in payload));self.assertEqual(len(chat.messages(self.c,self.uids['pro'],cid)),4)
        chunks=list(jobs.EventStream(self.uids['pro'],r2['job_id']));self.assertIn(b'event: delta',b''.join(chunks))

    def test_context_isolation_and_cross_user_privacy(self):
        a=self.create();b=self.create('B gas',['gas_mq2','buzzer']);ca=chat.create(self.c,self.ent('pro'),project_id=a['id']);cb=chat.create(self.c,self.ent('pro'),project_id=b['id'])
        sa,_=chat.assemble(self.c,self.ent('pro'),ca);sb,_=chat.assemble(self.c,self.ent('pro'),cb)
        self.assertIn('soil_cap',sa);self.assertNotIn('gas_mq2',sa);self.assertIn('gas_mq2',sb);self.assertNotIn('soil_cap',sb)
        for route in ('/api/designs/'+a['id'],'/api/conversations/'+ca,'/api/designs/'+a['id']+'/export?kind=code'):
            s,d=self.req('GET',route,user='other');self.assertIn(s,(403,404),d)

    def test_irrigation_and_gas_distinct_saved_reload_switches(self):
        a=self.create();b=self.create('B gas',['gas_mq2','buzzer'])
        self.assertNotEqual(a['spec']['circuit'],b['spec']['circuit']);self.assertNotEqual(a['wiring'],b['wiring']);self.assertNotEqual(a['spec']['firmware']['code'],b['spec']['firmware']['code'])
        for p in (a,b,a,b,a,b):
            s,r=self.req('GET','/api/designs/'+p['id']);self.assertEqual(s,200);self.assertEqual(r['spec']['circuit'],p['spec']['circuit']);self.assertEqual(r['spec']['firmware']['code'],p['spec']['firmware']['code'])

    def test_pin_sync_preserves_custom_code_and_revision_conflicts(self):
        a=self.create();pid=a['id'];custom=a['spec']['firmware']['code']+'\n// MY USER EDIT 13927\n'
        s,a=self.req('PATCH','/api/designs/'+pid,{'revision':a['revision'],'patch':{'firmware':{'code':custom}}});self.assertEqual(s,200,a)
        g=copy.deepcopy(a['spec']['circuit'])
        for e in g['connections']:
            for k in ('from','to'):
                if e[k]=={'component':'board','pin':'34'}:e[k]['pin']='35'
        s,r=self.req('PATCH','/api/designs/'+pid,{'revision':a['revision'],'patch':{'circuit':g}});self.assertEqual(s,200,r)
        self.assertIn('#define NX_SOIL_CAP_AO 35',r['spec']['firmware']['code']);self.assertIn('MY USER EDIT 13927',r['spec']['firmware']['code']);self.assertFalse(r['sync']['requires_regeneration'])
        s,r2=self.req('PATCH','/api/designs/'+pid,{'revision':a['revision'],'patch':{'circuit':g}});self.assertEqual(s,409,r2)

    def test_component_change_flags_driver_work_no_overwrite(self):
        p=self.create();g=copy.deepcopy(p['spec']['circuit']);g['components'].append({'id':'extra','model':'bme280','position':{'x':40,'y':700}})
        s,r=self.req('PATCH','/api/designs/'+p['id'],{'revision':p['revision'],'patch':{'circuit':g}});self.assertEqual(s,200,r);self.assertTrue(r['sync']['requires_regeneration']);self.assertTrue(r['spec']['firmware']['mismatch'])
        s,preview=self.req('POST','/api/designs/'+p['id']+'/code-preview',{});self.assertEqual(s,200);self.assertEqual(preview['firmware']['status'],'incomplete');self.assertTrue(any('I2C bus unassigned' in w for w in preview['firmware']['warnings']));self.assertIn('diff',preview)

    def test_versions_restore_and_exports(self):
        p=self.create();s,r=self.req('PATCH','/api/designs/'+p['id'],{'revision':1,'patch':{'requirements':{'problem':'Changed requirement'}}});self.assertEqual(s,200)
        s,v=self.req('GET','/api/designs/'+p['id']+'/versions');self.assertEqual(len(v['versions']),2)
        s,r=self.req('POST','/api/designs/'+p['id']+'/restore',{'revision':2,'version':1});self.assertEqual(s,200,r);self.assertEqual(r['spec']['requirements'],p['spec']['requirements'])
        for kind in ('json','svg','code','wiring','markdown'):
            s,out=self.req('GET',f'/api/designs/{p["id"]}/export?kind={kind}');self.assertEqual(s,200,(kind,out));self.assertTrue(out)

    def test_graph_validation_detects_electrical_errors(self):
        g=circuits.build('esp32',['soil_cap','pump']);self.assertTrue(circuits.validate(g)['passed'])
        def codes(gr):return {i['code'] for i in circuits.validate(gr)['issues']}
        bad=copy.deepcopy(g);bad['connections'].append({'id':'short','from':{'component':'board','pin':'3V3'},'to':{'component':'board','pin':'GND'}});self.assertIn('RAIL_SHORT',codes(bad))
        bad=copy.deepcopy(g);bad['connections']=[e for e in bad['connections'] if 'flyback' not in (e['from']['component'],e['to']['component'])];self.assertIn('PUMP_DRIVER',codes(bad))
        bad=circuits.build('esp32',['gas_mq2','buzzer']);bad['connections'].append({'id':'bad-level','from':{'component':'gas_mq2','pin':'AO'},'to':{'component':'board','pin':'35'}});self.assertIn('LOGIC_VOLTAGE',codes(bad))
        bad=copy.deepcopy(g);bad['connections'][0]['to']['pin']='999'
        with self.assertRaises(Exception):circuits.validate(bad)

    def test_missing_markers_flags_mismatch_and_static_not_faked(self):
        p=self.create();p['spec']['firmware']['code']='// custom source, no managed region'
        g=copy.deepcopy(p['spec']['circuit']);g['connections'][2]['from']['pin']='3V3' if g['connections'][2]['from']['component']=='board' else g['connections'][2]['from']['pin']
        # Force a real pin change.
        for e in g['connections']:
            if e['to']=={'component':'board','pin':'34'}:e['to']['pin']='35'
        fw,change=circuits.sync(p['spec']['firmware'],g);self.assertTrue(fw['mismatch']);self.assertEqual(fw['code'],'// custom source, no managed region')
        result=designs.static_checks(p['spec']);self.assertFalse(result['passed']);self.assertEqual(result['simulation']['status'],'not_run');self.assertEqual(result['compiler']['status'],'not_run')

    def test_novel_invention_uses_model_spec_not_library(self):
        self.configured();idea='An unfamiliar plant-canopy thermal comfort tag '+jobs.uid()
        s,r=self.req('POST','/api/inventions',{'idea':idea});self.assertEqual(s,202,r);j=self.wait(r['job_id']);self.assertEqual(j['state'],'complete',j)
        o=j['output'];self.assertTrue(o['created']);s,p=self.req('GET','/api/designs/'+o['project_id']);self.assertEqual(s,200);self.assertEqual(p['spec']['requirements']['problem'],idea)
        self.assertIn('bme280',[n['model'] for n in p['spec']['circuit']['components']]);self.assertEqual(len(p['spec']['guide']['assembly']),12)
        self.assertFalse(p['spec']['quality']['physical_tested'])

    def test_novel_invalid_model_json_honest_failure(self):
        self.configured();FixtureProvider.invalid_json=True
        s,r=self.req('POST','/api/inventions',{'idea':'Novel sensing concept not in catalogue'});j=self.wait(r['job_id']);self.assertEqual(j['state'],'failed');self.assertEqual(j['error']['code'],'invalid_design_response')

    def test_real_image_http_transport_storage_association_and_limits(self):
        self.configured('image');p=self.create();cid=chat.create(self.c,self.ent('pro'),project_id=p['id'])
        s,r=self.req('POST','/api/images',{'prompt':'A concept fixture','project_id':p['id'],'conversation_id':cid});self.assertEqual(s,202,r);j=self.wait(r['job_id']);self.assertEqual(j['state'],'complete',j)
        iid=j['output']['id'];s,im=self.req('GET','/api/images/'+iid);self.assertEqual(s,200);self.assertEqual(im['project_id'],p['id']);self.assertIn('data:image/png;base64,',im['data_uri'])
        msgs=chat.messages(self.c,self.uids['pro'],cid);self.assertIn(iid,msgs[-1]['meta']['images'])
        self.assertTrue(any(s['path'].endswith('/images/generations') for s in FixtureProvider.seen))
        s,d=self.req('GET','/api/images/'+iid,user='other');self.assertEqual(s,404)
        limits=self.ent('pro');limits['limits']['images_per_day']=0
        with self.assertRaises(Exception):images.generate(self.c,limits,'This must hit quota')

    def test_online_source_proposal_is_reviewed_not_auto_applied(self):
        self.configured();p=self.create();before=p['spec']['firmware']['code']
        s,r=self.req('POST','/api/designs/'+p['id']+'/ai-code',{'request':'Add a special sampling state machine'});self.assertEqual(s,202,r)
        j=self.wait(r['job_id']);self.assertEqual(j['state'],'complete',j)
        self.assertIn('TEST FIXTURE requested change',j['output']['code']);self.assertIn('diff',j['output'])
        s,saved=self.req('GET','/api/designs/'+p['id']);self.assertEqual(saved['spec']['firmware']['code'],before)
        s,applied=self.req('PATCH','/api/designs/'+p['id'],{'revision':j['output']['source_revision'],'patch':{'firmware':{'code':j['output']['code']}}});self.assertEqual(s,200,applied)
        self.assertIn('TEST FIXTURE requested change',applied['spec']['firmware']['code'])

    def test_i2c_driver_uses_graph_constants_after_bus_remap(self):
        g=circuits.build('esp32',['bme280'])
        for e in g['connections']:
            if e['from']=={'component':'bme280','pin':'SDA'}:e['to']['pin']='4'
            if e['from']=={'component':'bme280','pin':'SCL'}:e['to']['pin']='16'
        v=circuits.validate(g);f=circuits.firmware(g)
        self.assertTrue(v['passed'],v);self.assertIn('#define NX_BME280_SDA 4',f['code']);self.assertIn('#define NX_BME280_SCL 16',f['code'])
        self.assertIn('Wire.begin(NX_BME280_SDA, NX_BME280_SCL)',f['code'])

    def test_no_online_source_key_means_failed_proposal_not_fallback(self):
        p=self.create();s,r=self.req('POST','/api/designs/'+p['id']+'/ai-code',{'request':'Implement advanced processing'})
        j=self.wait(r['job_id']);self.assertEqual(j['state'],'failed');self.assertEqual(j['error']['code'],'provider_not_configured')

    def test_secret_encryption_versioning_tamper_and_legacy_compatibility(self):
        import hmac,hashlib
        from nexus.security import encrypt_secret,decrypt_secret,_keystream
        value='TEST-ONLY-confidential-provider-value'
        enc=encrypt_secret(value);self.assertTrue(enc.startswith('v2.'));self.assertEqual(decrypt_secret(enc),value)
        raw=bytearray(base64.urlsafe_b64decode(enc[3:]));raw[-1]^=1
        with self.assertRaises(ValueError):decrypt_secret('v2.'+base64.urlsafe_b64encode(raw).decode())
        # Old records remain readable; no existing admin key is lost on upgrade.
        nonce=b'legacy-test-1234';ct=bytes(a^b for a,b in zip(value.encode(),_keystream(nonce,len(value))));mac=hmac.new(config.APP_SECRET,nonce+ct,hashlib.sha256).digest()
        legacy=base64.urlsafe_b64encode(nonce+mac+ct).decode();self.assertEqual(decrypt_secret(legacy),value)

    def test_private_image_url_is_rejected_before_fetch(self):
        provider=OpenAICompatProvider({'base_url':self.base,'model':'fixture','api_key':'TEST-ONLY'})
        for url in ('http://example.org/a.png','https://127.0.0.1/a.png','https://localhost/a.png'):
            with self.assertRaises(ProviderError):provider._fetch_url(url)

    def test_atomic_quotas_under_concurrency(self):
        ent=self.ent('pro');used=db.count_usage(self.c,ent['user_id'],'image_generation',86400);ent['limits']['images_per_day']=used+1
        results=[]
        def reserve():
            c=db.connect()
            try:entitlements.consume(c,ent,'image_generation');results.append('allowed')
            except Exception:results.append('blocked')
            finally:c.close()
        ts=[threading.Thread(target=reserve) for _ in range(2)]
        for t in ts:t.start()
        for t in ts:t.join()
        self.assertEqual(sorted(results),['allowed','blocked'])

    def test_image_missing_config_and_free_denied(self):
        s,r=self.req('POST','/api/images',{'prompt':'Generate new concept'});j=self.wait(r['job_id']);self.assertEqual(j['state'],'failed');self.assertEqual(j['error']['code'],'image_not_configured')
        s,r=self.req('POST','/api/images',{'prompt':'Generate new concept'},user='free');self.assertEqual(s,403)

    def test_attachments_context_and_unsupported_formats(self):
        cid=chat.create(self.c,self.ent('pro'));s,r=self.req('POST','/api/conversations/'+cid+'/attachments',{'name':'example.py','text':'private_reference_value=29'});self.assertEqual(s,201,r)
        system,_=chat.assemble(self.c,self.ent('pro'),cid);self.assertIn('private_reference_value=29',system)
        s,r=self.req('POST','/api/conversations/'+cid+'/attachments',{'name':'unread.pdf','text':'opaque'});self.assertEqual(s,415)
        s,r=self.req('GET','/api/conversations/'+cid,user='other');self.assertEqual(s,404)

    def test_admin_provider_secret_policy_and_pro_not_admin(self):
        s,r=self.req('PATCH','/api/admin/providers',{'chat':{'provider':'openai_compatible','api_key':'SENSITIVE-NEVER-RETURNED','model':'fixture','base_url':self.base}},'admin');self.assertEqual(s,200,r)
        s,r=self.req('GET','/api/admin/providers',user='admin');self.assertNotIn('SENSITIVE-NEVER-RETURNED',json.dumps(r));self.assertNotIn('api_key_encrypted',json.dumps(r))
        s,r=self.req('GET','/api/admin/providers',user='pro');self.assertEqual(s,403)
        h=registry.health(self.c,force=True);self.assertTrue(h['online']);self.assertIsNone(h['image']['reachable'])

    def test_expiry_blocks_new_premium_work_but_preserves_private_design(self):
        p=self.create();now=time.time();uid=self.uids['pro'];self.c.execute('UPDATE subscriptions SET expires_at=? WHERE user_id=?',(now-1,uid))
        try:
            s,r=self.req('GET','/api/designs/'+p['id']);self.assertEqual(s,200)
            s,r=self.req('PATCH','/api/designs/'+p['id'],{'revision':p['revision'],'patch':{'circuit':p['spec']['circuit']}});self.assertEqual(s,403)
            s,r=self.req('POST','/api/inventions',{'idea':'A new invention'});self.assertEqual(s,403)
        finally:self.c.execute('UPDATE subscriptions SET expires_at=? WHERE user_id=?',(now+3600,uid))

    def test_unknown_component_cannot_fabricate_pinout(self):
        s,r=self.req('POST','/api/designs',{'name':'Unknown','components':['imaginary_sensor']});self.assertEqual(s,400);self.assertEqual(r['error']['code'],'unsupported_component')
        s,r=self.req('POST','/api/admin/components',{'model':'custom:sensor','definition':{'reviewed':False}},'admin');self.assertEqual(s,400)

    def test_research_is_explicitly_curated_and_saved(self):
        p=self.create();s,r=self.req('POST','/api/research/search',{'query':'ESP32 ADC','project_id':p['id']});self.assertEqual(s,200,r);self.assertFalse(r['web_search_performed']);self.assertEqual(r['mode'],'curated_only');self.assertTrue(r['sources'])
        s,p2=self.req('GET','/api/designs/'+p['id']);self.assertTrue(p2['spec']['research'])

    def test_cancellation_and_foreign_job_access(self):
        cid=chat.create(self.c,self.ent('pro'));self.configured()
        # Explicit cancellation before work starts is tested without a fake answer.
        jid=jobs.uid();now=time.time();self.c.execute("INSERT INTO ai_jobs(id,user_id,kind,state,created_at,updated_at) VALUES (?,?,?,'queued',?,?)",(jid,self.uids['pro'],'chat',now,now))
        s,r=self.req('POST','/api/jobs/'+jid+'/cancel',{});self.assertEqual(s,200);self.assertTrue(jobs.cancelled(self.c,jid))
        s,r=self.req('GET','/api/jobs/'+jid,user='other');self.assertEqual(s,404)
        self.c.execute("UPDATE ai_jobs SET state='cancelled' WHERE id=?",(jid,))


    def test_circuit_build_guide_is_derived_from_graph_and_never_claims_physical_test(self):
        g=circuits.build('esp32',['soil_cap','pump'])
        guide=circuits.build_guide(g)
        self.assertEqual(guide['connection_count'],len(g['connections']))
        self.assertEqual(len([x for x in guide['steps'] if x['kind']=='connection']),len(g['connections']))
        self.assertEqual(guide['status'],'graph_derived_guidance_not_physical_verification')
        self.assertIn('not a guarantee of error-free hardware', ' '.join(guide['limitations']))
        self.assertIsInstance(guide['blocking_errors'],list)
        self.assertTrue(guide['bill_of_materials'])
        self.assertEqual(sum(x['quantity'] for x in guide['bill_of_materials']),len([n for n in g['components'] if not n['model'].startswith('board:')]))
        self.assertTrue(any(x['kind']=='safety' for x in guide['steps']))

    def test_circuit_guidance_endpoint_requires_auth_and_returns_graph_derived_steps(self):
        p=self.create(parts=['soil_cap'])
        s,r=self.req('POST','/api/circuits/guidance',{'circuit':p['spec']['circuit']},'free')
        self.assertEqual(s,200,r)
        self.assertEqual(r['connection_count'],len(p['spec']['circuit']['connections']))
        self.assertTrue(r['steps'])
        s,_,r,_=call('POST','/api/circuits/guidance',{'circuit':p['spec']['circuit']})
        self.assertIn(s,(401,403))

class LiveAcceptance(unittest.TestCase):
    """Opt-in real provider smoke tests; absent creds = SKIPPED, never passed."""
    @unittest.skipUnless(os.environ.get('NEXUS_RUN_LIVE_TESTS')=='1' and (config.AI_ENV_KEY or config.AI_ENV_PROVIDER=='ollama'), 'BLOCKED: configure a real chat provider and NEXUS_RUN_LIVE_TESTS=1')
    def test_live_chat_question(self):
        c=db.connect()
        try:
            p=registry.chat_provider(c);r=p.chat([ChatMessage('user','Explain recursion in C with a tiny example and a base case.')]);self.assertGreater(len(r.text),50)
        finally:c.close()
    @unittest.skipUnless(os.environ.get('NEXUS_RUN_LIVE_TESTS')=='1' and (config.IMAGE_ENV_KEY or config.AI_ENV_KEY),'BLOCKED: configure real image credentials and NEXUS_RUN_LIVE_TESTS=1')
    def test_live_image_generation(self):
        c=db.connect()
        try:
            r=registry.image_provider(c).generate_image('Clean concept illustration of an environmental sensor prototype. No wiring instructions.');self.assertTrue(r[0].b64)
        finally:c.close()
