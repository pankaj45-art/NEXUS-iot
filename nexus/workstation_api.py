"""Additive API for conversations, jobs, private designs, circuits and images."""
from __future__ import annotations
import base64
import binascii
import csv
import io
import json
import re
import time
from urllib.parse import urlparse
from .api import route,response,file_response,require_auth,require_admin,_project_row,_guard_project
from . import db,entitlements
from .errors import ApiError
from .providers import registry
from .services import chat,circuits,connections,designs,images,invention,jobs,research

ID = r'([0-9a-f-]{36})'


def integer(value,default=0):
    try:return int(value)
    except (ValueError,TypeError):return default


@route('GET',r'/api/ai/status')
def ai_status(ctx,m):
    require_auth(ctx)
    p=registry.chat_provider(ctx.conn);im=registry.image_provider(ctx.conn)
    return response({'chat':{'provider':p.name,'model':p.model,'configured':p.configured() and not p.missing(),
            'reachable':None,'missing':p.missing(),'capabilities':p.capabilities(),'last_test':connections.last_check(ctx.conn)},
        'image':{'provider':im.name,'model':im.model,'configured':im.configured() and not im.missing() and 'image_generation' in im.supports,'missing':im.missing() or (['image_generation_capability'] if 'image_generation' not in im.supports else []),'reachable':None},
        'message':'Configured is not the same as reachable. Admin Test connection performs a real provider request.',
        'offline_functions':registry.load(ctx.conn)['policy']['offline_basic_functions']})


@route('GET',r'/api/admin/providers')
def providers(ctx,m):
    require_admin(ctx);return response(registry.public_view(ctx.conn))


@route('PATCH',r'/api/admin/providers')
def patch_providers(ctx,m):
    ent=require_admin(ctx);patch={}
    for kind in ('chat','image','web_search'):
        if kind not in ctx.body:continue
        data=ctx.body[kind]
        if not isinstance(data,dict):raise ApiError(400,kind+' must be an object.','invalid_input')
        allow={'provider','model','base_url','api_key','enabled','timeout','max_retries','capabilities','default_size','quality'}
        if set(data)-allow:raise ApiError(400,'Unrecognized provider fields.','invalid_input')
        if 'enabled' in data and not isinstance(data['enabled'],bool): raise ApiError(400,'enabled must be boolean.','invalid_input')
        if 'capabilities' in data and (not isinstance(data['capabilities'],dict) or any(not isinstance(v,bool) for v in data['capabilities'].values())): raise ApiError(400,'Capability flags must be boolean.','invalid_input')
        if 'api_key' in data and (not isinstance(data['api_key'],str) or len(data['api_key'])>4096): raise ApiError(400,'Invalid API key value.','invalid_input')
        if 'timeout' in data:
            try: data['timeout']=float(data['timeout'])
            except (TypeError,ValueError): raise ApiError(400,'Timeout must be numeric.','invalid_input')
        available=('none','tavily','searxng') if kind=='web_search' else ('none','openai_compatible','gemini','ollama') if kind=='chat' else ('none','openai_compatible')
        if data.get('provider',available[0]) not in available:raise ApiError(400,'Unsupported '+kind+' adapter.','invalid_input')
        if 'base_url' in data and data['base_url']:
            parsed=urlparse(str(data['base_url']))
            if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ApiError(400,'Provider URL must be an HTTP(S) server URL without credentials/query/fragment.','invalid_input')
        if data.get('provider') == 'gemini':
            old = registry.load(ctx.conn)['chat']
            base = data.get('base_url') or (old.get('base_url') if old.get('provider') == 'gemini' else connections.GEMINI_BASE)
            data['base_url'] = connections._base_url(base, 'gemini')
            data.setdefault('model', old.get('model') if old.get('provider') == 'gemini' else connections.GEMINI_MODEL)
        if 'timeout' in data and not 2<=float(data['timeout'])<=180:raise ApiError(400,'Timeout must be 2–180 seconds.','invalid_input')
        if 'max_retries' in data and integer(data['max_retries'],-1) not in (0,1,2):raise ApiError(400,'Retries must be 0–2.','invalid_input')
        if 'model' in data and len(str(data['model']))>160:raise ApiError(400,'Model name too long.','invalid_input')
        patch[kind]=data
    if not patch:raise ApiError(400,'No provider configuration supplied.','invalid_input')
    registry.save(ctx.conn,patch)
    db.audit(ctx.conn,ent['user_id'],'admin.providers_update','',{'sections':list(patch)})
    return response({'ok':True,'config':registry.public_view(ctx.conn)})


@route('POST',r'/api/admin/providers/connect')
def connect_provider(ctx,m):
    ent=require_admin(ctx)
    # nx_csrf is a transport-only fallback used by the embedded preview.
    body={k:v for k,v in ctx.body.items() if k!='nx_csrf'}
    return response(connections.connect_chat(ctx.conn,ent,body))


@route('POST',r'/api/admin/providers/connect/start')
def start_provider_connection(ctx,m):
    ent=require_admin(ctx)
    body={k:v for k,v in ctx.body.items() if k!='nx_csrf'}
    return response(connections.start_chat(ctx.conn,ent,body),202)


@route('POST',r'/api/admin/providers/test/start')
def start_provider_health(ctx,m):
    ent=require_admin(ctx)
    return response(connections.start_health(ctx.conn,ent),202)


@route('POST',r'/api/admin/providers/test')
def test_providers(ctx,m):
    require_admin(ctx);return response(registry.health(ctx.conn,force=True))


@route('GET',r'/api/conversations')
def conversations(ctx,m):
    ent=require_auth(ctx);pid=ctx.query.get('project_id');params=[ent['user_id']];where='user_id=?'
    if pid:designs.owned(ctx.conn,ent,pid);where+=' AND project_id=?';params.append(pid)
    rows=ctx.conn.execute('SELECT * FROM conversations WHERE '+where+' ORDER BY updated_at DESC LIMIT 100',params).fetchall()
    return response({'conversations':[dict(r) for r in rows]})


@route('POST',r'/api/conversations')
def create_conversation(ctx,m):
    ent=require_auth(ctx)
    return response({'id':chat.create(ctx.conn,ent,ctx.body.get('title','New conversation'),ctx.body.get('project_id') or None)},201)


@route('GET',r'/api/conversations/'+ID)
def get_conversation(ctx,m):
    ent=require_auth(ctx);cid=m.group(1);c=chat.conversation(ctx.conn,ent['user_id'],cid)
    return response({'conversation':dict(c),'messages':chat.messages(ctx.conn,ent['user_id'],cid),
        'active_job':next((r['id'] for r in ctx.conn.execute("SELECT id FROM ai_jobs WHERE conversation_id=? AND state IN ('queued','running')",(cid,))),None)})


@route('DELETE',r'/api/conversations/'+ID)
def delete_conversation(ctx,m):
    ent=require_auth(ctx);cid=m.group(1);chat.conversation(ctx.conn,ent['user_id'],cid)
    if ctx.conn.execute("SELECT 1 FROM ai_jobs WHERE conversation_id=? AND state IN ('queued','running')",(cid,)).fetchone():raise ApiError(409,'Cancel/wait for the active job before deleting.','job_running')
    ctx.conn.execute('DELETE FROM conversations WHERE id=? AND user_id=?',(cid,ent['user_id']))
    return response({'ok':True})


@route('POST',r'/api/conversations/'+ID+r'/messages')
def add_message(ctx,m):
    ent=require_auth(ctx);return response(chat.add(ctx.conn,ent,m.group(1),str(ctx.body.get('message','')).strip(),
        action=ctx.body.get('action','auto'),image_options=ctx.body.get('options',{})),202)


@route('POST',r'/api/conversations/'+ID+r'/attachments')
def add_attachment(ctx,m):
    ent=require_auth(ctx);cid=m.group(1);chat.conversation(ctx.conn,ent['user_id'],cid)
    name=str(ctx.body.get('name','document.txt')).replace('/','_').replace('\\','_')[:150];text=ctx.body.get('text')
    if not re.search(r'\.(txt|md|csv|json|py|ino|cpp|c|h|js|ts|html|css|yaml|yml|log|xml)$',name,re.I):
        raise ApiError(415,'Only text, code and structured text files are currently supported. PDF/vision ingestion is not implemented; no file was pretended to be read.','unsupported_attachment')
    if not isinstance(text,str) or len(text.encode())>256000:raise ApiError(400,'Text attachment limit: 256 KB.','too_large')
    if ctx.conn.execute('SELECT COUNT(*) FROM attachments WHERE conversation_id=?',(cid,)).fetchone()[0]>=5:raise ApiError(429,'Limit: five attachments per conversation.','limit_reached')
    aid=jobs.uid();ctx.conn.execute('INSERT INTO attachments VALUES (?,?,?,?,?,?,?)',(aid,ent['user_id'],cid,name,'text/plain',text,time.time()))
    return response({'id':aid,'name':name,'context_limit':'Latest five files, first 10,000 characters each; full stored text remains available.'},201)


@route('GET',r'/api/conversations/'+ID+r'/attachments')
def list_attachments(ctx,m):
    ent=require_auth(ctx);chat.conversation(ctx.conn,ent['user_id'],m.group(1))
    return response({'attachments':[dict(r) for r in ctx.conn.execute('SELECT id,name,LENGTH(text) size FROM attachments WHERE conversation_id=? AND user_id=?',(m.group(1),ent['user_id']))]})


@route('GET',r'/api/jobs/'+ID)
def job(ctx,m):
    ent=require_auth(ctx);return response(jobs.get(ctx.conn,ent['user_id'],m.group(1),integer(ctx.query.get('after'))))


@route('GET',r'/api/jobs/'+ID+r'/events')
def job_events(ctx,m):
    ent=require_auth(ctx);jobs.get(ctx.conn,ent['user_id'],m.group(1))
    return 200,{'Content-Type':'text/event-stream; charset=utf-8','Cache-Control':'no-store','X-Accel-Buffering':'no','Connection':'close'},jobs.EventStream(ent['user_id'],m.group(1),integer(ctx.query.get('after')))


@route('POST',r'/api/jobs/'+ID+r'/cancel')
def cancel_job(ctx,m):
    ent=require_auth(ctx);j=jobs.get(ctx.conn,ent['user_id'],m.group(1))
    ctx.conn.execute('UPDATE ai_jobs SET cancelled=1 WHERE id=? AND user_id=?',(m.group(1),ent['user_id']))
    return response({'ok':True,'state':j['state'],'message':'Cancellation requested. An in-flight upstream request may finish and incur usage before it can be stopped.'})


@route('GET',r'/api/components')
def components(ctx,m):
    require_auth(ctx);return response({'schema':circuits.SCHEMA,'components':circuits.catalog(ctx.conn),
        'scope':'Exact-pin connection-level support: ESP32 and ESP32-S3. Other boards remain in the legacy library; no PCB routing/SPICE simulation.'})


@route('POST',r'/api/admin/components')
def add_component(ctx,m):
    ent=require_admin(ctx);key=str(ctx.body.get('model',''));d=ctx.body.get('definition')
    if not re.fullmatch(r'custom:[a-z0-9_-]{2,50}',key) or not isinstance(d,dict):raise ApiError(400,'Custom component ID must be custom:<slug>.','invalid_input')
    if not d.get('reviewed') or not d.get('reference') or not str(d['reference']).startswith('https://'):
        raise ApiError(400,'A reviewed definition and real HTTPS datasheet/reference are required.','unreviewed_component')
    ps=d.get('pins',[])
    if not isinstance(ps,list) or not 1<=len(ps)<=40:raise ApiError(400,'Provide 1–40 documented pins.','invalid_input')
    allowed={'passive','ground','power_in','power_out','analog_in','analog_out','digital_in','digital_out','digital_io','i2c_sda','i2c_scl','gate','source','drain','gpio'}
    names=[]
    for p in ps:
        if not isinstance(p,dict) or p.get('type') not in allowed or not re.fullmatch(r'[A-Za-z0-9_+.-]{1,16}',str(p.get('id',''))):raise ApiError(400,'Invalid documented pin definition.','invalid_input')
        p.setdefault('required',True);p.setdefault('voltage',None);names.append(p['id'])
    if len(set(names))!=len(names):raise ApiError(400,'Pin IDs must be unique.','invalid_input')
    # Definitions are inert metadata: never evaluate code/driver strings.
    safe={k:d.get(k) for k in ('name','pins','reference','supply_v','current_ma','notes','interface','compatible_boards','verification')};safe.update(reviewed=True,driver=None)
    existing=ctx.conn.execute('SELECT definition_json FROM component_definitions WHERE model=?',(key,)).fetchone()
    if existing and json.loads(existing['definition_json'])!=safe:
        raise ApiError(409,'Component definitions are immutable to protect saved pin graphs. Use a new versioned model ID (for example custom:sensor-v2).','component_definition_immutable')
    ctx.conn.execute('INSERT INTO component_definitions VALUES (?,?,?,?) ON CONFLICT(model) DO UPDATE SET definition_json=excluded.definition_json,author_id=excluded.author_id,updated_at=excluded.updated_at',(key,json.dumps(safe),ent['user_id'],time.time()))
    db.audit(ctx.conn,ent['user_id'],'admin.component_definition',key)
    return response({'ok':True,'model':key,'limitation':'No automatic driver is created for custom components; firmware is explicitly incomplete until manually implemented/reviewed.'},201)


@route('GET',r'/api/designs')
def list_designs(ctx,m):
    ent=require_auth(ctx);return response({'projects':[dict(r) for r in ctx.conn.execute('SELECT id,name,revision,created_at,updated_at FROM engineering_projects WHERE user_id=? ORDER BY updated_at DESC',(ent['user_id'],))]})


@route('POST',r'/api/designs')
def create_design(ctx,m):
    ent=require_auth(ctx);models=ctx.body.get('components',[])
    if not isinstance(models,list) or len(models)>8:raise ApiError(400,'Choose at most eight high-level components.','invalid_input')
    if not ent['is_pro'] and len(models)>2:raise ApiError(403,'Free basic creation supports two high-level components. Advanced designs require Pro.','pro_required')
    if ctx.body.get('circuit'):
        entitlements.require_feature(ent,'tools.circuit_designer');g=ctx.body['circuit']
    else:
        try:g=circuits.build(ctx.body.get('board','esp32'),models)
        except StopIteration as e:raise ApiError(400,'Insufficient supported pins. Choose fewer components.','pin_capacity') from e
    req=ctx.body.get('requirements',{})
    if not isinstance(req,dict):raise ApiError(400,'Requirements must be an object.','invalid_input')
    req.setdefault('problem',str(ctx.body.get('name','Custom prototype')));req.setdefault('source','explicit_manual_design')
    return response(designs.create(ctx.conn,ent,str(ctx.body.get('name','New engineering design')),req,g),201)


@route('POST',r'/api/designs/from-library')
def fork_library(ctx,m):
    ent=require_auth(ctx);row=_project_row(ctx,str(ctx.body.get('slug','')));_guard_project(ctx,row,ent)
    c=json.loads(row['content_json']);parts=c['meta']['parts']
    board_key=c['meta'].get('board_key','esp32')
    # Comprehensive mapping: library vocabulary → Studio catalog IDs.
    # Unrecognised parts are placed as unwired stubs instead of blocking the fork.
    aliases={
        'oled':'oled_ssd1306','ssd1306':'oled_ssd1306','oled_ssd1306':'oled_ssd1306',
        'soil_cap':'soil_cap','soil':'soil_cap',
        'gas_mq2':'gas_mq2','mq2':'gas_mq2','gas_mq135':'gas_mq135','mq135':'gas_mq135',
        'bme280':'bme280','bme680':'bme680','bmp280':'bmp280',
        'dht22':'dht22','dht11':'dht11',
        'pump':'pump','buzzer':'buzzer','led':'led',
        'hcsr04':'hcsr04','ultrasonic':'hcsr04',
        'pir':'pir','motion':'pir',
        'relay':'relay1','relay1':'relay1','relay_2ch':'relay_2ch',
        'servo':'servo_sg90','servo_sg90':'servo_sg90','servo_mg996r':'servo_mg996r',
        'mpu6050':'mpu6050','imu':'mpu6050',
        'ds18b20':'ds18b20','temp':'ds18b20',
        'ldr':'ldr','light':'ldr',
        'sound':'sound_analog','mic':'sound_analog','mic_i2s':'microphone_i2s',
        'rain':'rain_sensor','rain_sensor':'rain_sensor',
        'water_level':'water_level','water_leak':'water_leak_sensor',
        'gps':'gps_neo6m','gps_neo6m':'gps_neo6m','gps_neo8m':'gps_neo8m',
        'rfid':'rfid_rc522','rfid_rc522':'rfid_rc522','rfid_pn532':'rfid_pn532',
        'ir_receiver':'ir_receiver','ir_led':'ir_led',
        'sdcard':'sd_card_spi','sd_card':'sd_card_spi',
        'rtc':'rtc_ds3231','ds3231':'rtc_ds3231','ds1307':'rtc_ds1307',
        'oled_spi':'oled_spi','lcd':'lcd_1602_i2c','lcd_1602':'lcd_1602_i2c','lcd_2004':'lcd_2004_i2c',
        'tft':'tft_ili9341','tft_ili9341':'tft_ili9341','tft_st7789':'tft_st7789',
        'ws2812b':'neopixel_strip','neopixel':'neopixel_strip',
        'max30102':'max30102','pulse':'max30102',
        'hx711':'load_cell_hx711','weight':'load_cell_hx711',
        'hall':'magnetic_hall_a3144','hall_sensor':'magnetic_hall_a3144',
        'flame':'flame_ir_ky026','flame_sensor':'flame_ir_ky026',
        'reed':'reed_switch','tilt':'tilt_ball_sw520d',
        'turbidity':'turbidity_sensor','tds':'tds_sensor_analog','ph':'ph_sensor_analog',
        'vl53l0x':'vl53l0x','lidar':'vl53l0x',
        'ina219':'ina219','current':'current_acs712_5a','acs712':'current_acs712_5a',
        'pressure':'bmp280','bmp180':'bmp180',
        'scd30':'scd30','pms5003':'pms5003','sds011':'sds011',
        'bh1750':'bh1750','color':'tcs34725',
        'ccs811':'ccs811','sgp30':'sgp30','bme680':'bme680','sht31':'sht31',
        'mlx90614':'mlx90614','amg8833':'amg8833',
        'touch':'ttp223_touch','cap_touch':'mpr121_touch',
        'button':'push_button','keypad':'keypad_4x4','rotary':'rotary_encoder',
        'joystick':'joystick_xy','potentiometer':'potentiometer',
        'stepper':'stepper_driver_a4988','stepper_driver':'stepper_driver_a4988',
        'fan':'fan_12v','valve':'solenoid_valve_12v',
        'ethernet':'ethernet_w5500','can':'can_transceiver','rs485':'rs485_module',
        'lora':'lora_sx1278','nrf24':'nrf24l01_plus','hc12':'hc12_wireless',
        'sim800':'sim800l','gsm':'sim800l','ble':'ble_hm10','hc05':'bluetooth_hc05',
        'fingerprint':'fingerprint_r503','camera':'ov2640_cam',
    }
    ignored=('r220','r10k','r4k7','r15k','r100','cap100','cap100n','cap10u',
             'buck5v','mosfet','diode','level_shifter','supply5','supply',
             'terminal_block','jst_ph2','breadboard','jumper_wires','crystal',
             'ferrite_bead','power_switch','dc_dc_regulator')
    cat = circuits.catalog()
    # Build models list: use alias if available, otherwise use as-is if it exists in catalog, skip if ignored
    models = []
    skipped = []
    for k in parts:
        if k in aliases:
            models.append(aliases[k])
        elif k in ignored:
            pass  # silently skip passive/structural parts
        elif k in cat:
            models.append(k)  # direct catalog match
        else:
            skipped.append(k)  # unknown - skip gracefully
    models = list(dict.fromkeys(models))
    g=circuits.build(board_key, models)
    req={'title':row['title'],'problem':c['overview'].get('problem_statement',row['summary']),'source_library_slug':row['slug'],
         'assumptions':['A new supported connection-level design was created. Review differences against the original; it is not a verified physical build.'] +
                       (['Skipped unrecognised parts (no catalog entry): ' + ', '.join(skipped)] if skipped else [])}
    return response(designs.create(ctx.conn,ent,row['title'],req,g),201)


@route('GET',r'/api/designs/'+ID)
def get_design(ctx,m):
    ent=require_auth(ctx);return response(designs.view(designs.owned(ctx.conn,ent,m.group(1)),ctx.conn))


@route('PATCH',r'/api/designs/'+ID)
def save_design(ctx,m):
    ent=require_auth(ctx);return response(designs.save(ctx.conn,ent,m.group(1),integer(ctx.body.get('revision'),-1),ctx.body.get('patch',{}),ctx.body.get('summary','Saved design')))


@route('DELETE',r'/api/designs/'+ID)
def delete_design(ctx,m):
    ent=require_auth(ctx);designs.owned(ctx.conn,ent,m.group(1))
    if ctx.conn.execute("SELECT 1 FROM ai_jobs j JOIN conversations c ON c.id=j.conversation_id WHERE c.project_id=? AND j.state IN ('running','queued')",(m.group(1),)).fetchone():raise ApiError(409,'Cancel the active project job before deleting.','job_running')
    ctx.conn.execute('DELETE FROM engineering_projects WHERE id=? AND user_id=?',(m.group(1),ent['user_id']));return response({'ok':True})


@route('GET',r'/api/designs/'+ID+r'/versions')
def design_versions(ctx,m):
    ent=require_auth(ctx);entitlements.require_feature(ent,'workspace.full');designs.owned(ctx.conn,ent,m.group(1))
    return response({'versions':[dict(r) for r in ctx.conn.execute('SELECT revision,summary,created_at FROM engineering_versions WHERE project_id=? ORDER BY revision DESC',(m.group(1),))]})


@route('POST',r'/api/designs/'+ID+r'/restore')
def restore_design(ctx,m):
    ent=require_auth(ctx);return response(designs.restore(ctx.conn,ent,m.group(1),integer(ctx.body.get('version')),integer(ctx.body.get('revision'))))


@route('POST',r'/api/designs/'+ID+r'/validate')
def validate_design(ctx,m):
    ent=require_auth(ctx);entitlements.require_feature(ent,'tools.circuit_designer');s=designs.view(designs.owned(ctx.conn,ent,m.group(1)),ctx.conn)
    result=designs.static_checks(s['spec'],ctx.conn)
    designs.save(ctx.conn,ent,m.group(1),s['revision'],{'testing':s['spec']['testing']+[result]},'Static checks (not compilation/simulation/hardware)')
    return response(result)


@route('POST',r'/api/circuits/validate')
def validate_circuit(ctx,m):
    ent=require_auth(ctx);entitlements.require_feature(ent,'tools.circuit_designer')
    return response(circuits.validate(ctx.body.get('circuit'),ctx.conn))

@route('POST',r'/api/circuits/guidance')
def circuit_guidance(ctx,m):
    # Build guidance is a read-only safety aid; keep it available to all authenticated tiers.
    require_auth(ctx)
    return response(circuits.build_guide(ctx.body.get('circuit'),ctx.conn))


@route('GET',r'/api/designs/'+ID+r'/engineering-pack')
def engineering_pack(ctx,m):
    """Export one traceable engineering package from the saved canonical design."""
    ent=require_auth(ctx)
    row=designs.owned(ctx.conn,ent,m.group(1))
    viewed=designs.view(row,ctx.conn)
    spec=viewed['spec']; graph=spec['circuit']
    guide=circuits.build_guide(graph,ctx.conn)
    validation=circuits.validate(graph,ctx.conn)
    return response({
        'format':'nexus-engineering-pack/1',
        'project':{'id':row['id'],'name':row['name'],'revision':row['revision'],'updated_at':row['updated_at']},
        'objective':spec.get('requirements',{}).get('problem',''),
        'requirements_and_assumptions':spec.get('requirements',{}),
        'architecture':spec.get('requirements',{}).get('architecture',
            'Architecture is not explicitly specified. Review the saved requirements and component graph before implementation.'),
        'controller_and_components':[{'id':n['id'],'model':n['model'],'label':n.get('label',n['id'])} for n in graph['components']],
        'wiring':viewed['wiring'],
        'bill_of_materials':guide['bill_of_materials'],
        'step_by_step_build_guide':guide['steps'],
        'component_notes':guide['component_notes'],
        'validation':validation,
        'unconnected_required_terminals':guide['unconnected_required_terminals'],
        'firmware':spec.get('firmware',{}),
        'research_sources':spec.get('research',[]),
        'verification_status':{'static_rule_check':True,'compiled':False,'simulated':False,'physical_hardware_tested':False,
            'meaning':'This package is derived from the saved design. It is not proof of compilation, simulation, electrical safety or successful hardware operation.'},
        'limitations':guide['limitations']
    })


@route('POST',r'/api/designs/'+ID+r'/code-preview')
def preview_code(ctx,m):
    ent=require_auth(ctx);return response(designs.code_preview(ctx.conn,ent,m.group(1)))


@route('GET',r'/api/designs/'+ID+r'/export')
def design_export(ctx,m):
    ent=require_auth(ctx);entitlements.require_feature(ent,'exports');r=designs.owned(ctx.conn,ent,m.group(1));s=json.loads(r['spec_json']);kind=ctx.query.get('kind','json');filename='nexus-'+r['id']
    if kind=='json':return file_response(json.dumps(s,indent=2),'application/json',filename+'.json')
    if kind=='code':return file_response(s['firmware']['code'],'text/plain; charset=utf-8',filename+'.ino')
    if kind=='svg':return file_response(circuits.svg(s['circuit'],ctx.conn),'image/svg+xml',filename+'.svg')
    if kind=='markdown':return file_response(designs.report(r,ctx.conn),'text/markdown; charset=utf-8',filename+'.md')
    if kind=='wiring':
        out=io.StringIO();w=csv.DictWriter(out,fieldnames=['id','from','to','signal']);w.writeheader();w.writerows(circuits.wiring(s['circuit'],ctx.conn));return file_response(out.getvalue(),'text/csv',filename+'-wiring.csv')
    raise ApiError(400,'Supported exports: json, code, svg, markdown, wiring.','invalid_input')


@route('POST',r'/api/inventions')
def invent(ctx,m):
    ent=require_auth(ctx);entitlements.require_feature(ent,'tools.invention');b=ctx.body
    if b.get('project_id'):designs.owned(ctx.conn,ent,b['project_id'])
    jid=jobs.launch(ctx.conn,ent,'invention',lambda c,e,j:invention.plan(c,e,str(b.get('idea','')),constraints=str(b.get('constraints','')),project_id=b.get('project_id'),do_research=bool(b.get('research'))))
    return response({'job_id':jid},202)


@route('POST',r'/api/inventions/'+ID+r'/apply')
def apply_invention(ctx,m):
    ent=require_auth(ctx);entitlements.require_feature(ent,'tools.invention');j=jobs.get(ctx.conn,ent['user_id'],m.group(1));o=j['output']
    if j['state']!='complete' or j['kind']!='invention' or not o.get('source_revision'):
        raise ApiError(400,'This is not a completed iteration proposal.','invalid_input')
    return response(designs.save(ctx.conn,ent,o['project_id'],o['source_revision'],{'circuit':o['circuit'],'requirements':o['proposal'],'research':o['research']['sources']},'Applied invention iteration; custom code preserved'))


@route('POST',r'/api/images')
def generate_image(ctx,m):
    ent=require_auth(ctx);entitlements.require_feature(ent,'tools.images');b=ctx.body
    if b.get('project_id'):designs.owned(ctx.conn,ent,b['project_id'])
    if b.get('conversation_id'):chat.conversation(ctx.conn,ent['user_id'],b['conversation_id'])
    # If generated outside chat, create a correctly scoped conversation/message.
    cid=b.get('conversation_id') or chat.create(ctx.conn,ent,'Concept: '+str(b.get('prompt',''))[:60],b.get('project_id'))
    mid=jobs.uid();ctx.conn.execute("INSERT INTO messages VALUES (?,?,?,'','streaming','{}',?)",(mid,cid,'assistant',time.time()))
    def work(c,e,j):
        r=images.generate(c,e,str(b.get('prompt','')),project_id=b.get('project_id'),conversation_id=cid,message_id=mid,
                           size=b.get('size','1024x1024'),style=b.get('style',''),reference_id=b.get('reference_id'))
        c.execute("UPDATE messages SET content=?,status='complete',meta_json=? WHERE id=?",(r['label'],json.dumps({'images':[r['id']],'project_id':b.get('project_id')}),mid));return r
    jid=jobs.launch(ctx.conn,ent,'image',work,conversation_id=cid,message_id=mid)
    return response({'job_id':jid,'conversation_id':cid,'message_id':mid},202)


@route('GET',r'/api/images')
def list_images(ctx,m):
    ent=require_auth(ctx);where='user_id=?';params=[ent['user_id']]
    for k in ('project_id','conversation_id'):
        if ctx.query.get(k):where+=' AND '+k+'=?';params.append(ctx.query[k])
    return response({'images':[images.view(r) for r in ctx.conn.execute('SELECT * FROM generated_images WHERE '+where+' ORDER BY created_at DESC LIMIT 60',params)]})


@route('GET',r'/api/images/'+ID)
def get_image(ctx,m):
    ent=require_auth(ctx);return response(images.view(images.owned(ctx.conn,ent,m.group(1)),True))


@route('GET',r'/api/images/'+ID+r'/download')
def download_image(ctx,m):
    ent=require_auth(ctx);r=images.owned(ctx.conn,ent,m.group(1));return file_response(r['bytes'],r['mime'],'concept-'+r['id']+'.'+r['mime'].split('/')[1])


@route('POST',r'/api/research/search')
def do_search(ctx,m):
    ent=require_auth(ctx);entitlements.require_feature(ent,'tools.research');entitlements.consume(ctx.conn,ent,'tool_call')
    query=str(ctx.body.get('query','')).strip()
    if not query: raise ApiError(400,'Enter a research question.','invalid_input')
    pid=ctx.body.get('project_id')
    if pid: designs.owned(ctx.conn,ent,pid)
    result=research.search(ctx.conn,query)
    cur=ctx.conn.execute('INSERT INTO tool_runs(user_id,tool,input_json,output_json,mode,created_at) VALUES (?,?,?,?,?,?)',
          (ent['user_id'],'research_search',json.dumps({'query':query,'project_id':pid}),json.dumps(result),result['mode'],time.time()))
    result['run_id']=cur.lastrowid
    if pid:
        p=designs.view(designs.owned(ctx.conn,ent,pid),ctx.conn)
        unique={s['url']:s for s in p['spec']['research']+result['sources']}
        designs.save(ctx.conn,ent,pid,p['revision'],{'research':list(unique.values())},'Research references saved')
    return response(result)


@route('GET',r'/api/jobs')
def list_jobs(ctx,m):
    ent=require_auth(ctx);kind=ctx.query.get('kind');where='user_id=?';params=[ent['user_id']]
    if kind:
        where+=' AND kind=?';params.append(kind)
    rows=ctx.conn.execute('SELECT id,kind,state,created_at,updated_at FROM ai_jobs WHERE '+where+' ORDER BY created_at DESC LIMIT 50',params).fetchall()
    return response({'jobs':[dict(r) for r in rows]})


@route('POST',r'/api/designs/'+ID+r'/ai-code')
def ai_code(ctx,m):
    from .services import code_ai
    ent=require_auth(ctx);entitlements.require_feature(ent,'tools.code_engineer');pid=m.group(1);designs.owned(ctx.conn,ent,pid)
    request=str(ctx.body.get('request',''))
    jid=jobs.launch(ctx.conn,ent,'ai_code',lambda c,e,j:code_ai.propose(c,e,pid,request))
    return response({'job_id':jid},202)
