"""Private UUID projects, revisioned canonical specs and non-destructive code sync."""
import ast
import copy
import difflib
import json
import time
from .. import db, entitlements, hardware
from ..errors import ApiError
from . import circuits, jobs


def owned(conn, ent, pid):
    r=conn.execute('SELECT * FROM engineering_projects WHERE id=? AND user_id=?',(pid,ent['user_id'])).fetchone()
    if not r:raise ApiError(404,'Project not found.','not_found')
    return r


def view(row, conn=None):
    spec=json.loads(row['spec_json']);g=spec['circuit']
    return {'id':row['id'],'name':row['name'],'revision':row['revision'],'created_at':row['created_at'],
            'updated_at':row['updated_at'],'spec':spec,'validation':circuits.validate(g,conn),'wiring':circuits.wiring(g,conn)}


def guide(req,g,fw,conn=None):
    cat=circuits.catalog(conn);name=req.get('title','Custom IoT prototype');parts=[cat[n['model']]['name'] for n in g['components']]
    return {
      'objective':req.get('problem') or name,
      'architecture':req.get('architecture') or 'Supported sensors → selected ESP32 controller → local serial telemetry / actuator driver. Network transport must be added and verified if required.',
      'bom':[{'instance':n['id'],'model':n['model'],'name':cat[n['model']]['name'],'quantity':1,
              'supply_v':cat[n['model']].get('supply_v'),'current_ma_assumed':cat[n['model']].get('current_ma'),
              'price':'Not quoted; obtain current local pricing','reference':cat[n['model']]['reference'],
              'notes':cat[n['model']].get('notes','')} for n in g['components']],
      'assembly':[
         {'step':1,'title':'Requirements and hazards','detail':'Confirm '+req.get('problem',name)+'. '+str(req.get('constraints',''))+' Confirm environment, budget, power/current and intended behavior before ordering parts.'},
         {'step':2,'title':'Identify parts','detail':'Check exact board revision and module terminals against source documentation: '+', '.join(parts)+'. Named schematic terminals are not generic package lead numbers.'},
         {'step':3,'title':'Prepare software','detail':'Install Arduino IDE, Espressif ESP32 core 3.x and libraries listed in the saved firmware. Preserve local secrets outside source control.'},
         {'step':4,'title':'Assemble power-off','detail':'Follow the current graph-derived wiring table, including passive resistors, driver, shared ground and flyback diode where present. Do not use artistic concept images for wiring.'},
         {'step':5,'title':'Pre-power checks','detail':'Measure for shorts and polarity; verify supply and ADC maximum voltage. Use a current-limited isolated low-voltage supply. Confirm motor stall current and thermal limits.'},
         {'step':6,'title':'Compile and upload','detail':'Open firmware.ino, select exact board/port, compile, inspect warnings and upload. This server has not compiled or run the firmware on hardware.'},
         {'step':7,'title':'Configure and calibrate','detail':'Replace dry/wet and ADC threshold PLACEHOLDERS with measured reference values. Review graph hash, driver assumptions and fail-safe behavior.'},
         {'step':8,'title':'Observe output','detail':'Open serial at 115200 baud. Expect raw sensor values, or explicit sensor read errors. Readings are not validated physical measurements until checked against a reference.'},
         {'step':9,'title':'Functional tests','detail':'Exercise the documented input range and output hysteresis; test maximum run time and sensor disconnect without leaving loads unattended. Gas prototype: use safe electrical input simulation, NOT released flammable gas.'},
         {'step':10,'title':'Troubleshoot','detail':'No output: check power, port and baud. Invalid values: check exact wiring, bus address, pull-ups and calibration. Resets: inspect inrush, brownout, decoupling and supply rating.'},
         {'step':11,'title':'Security and reliability','detail':'Do not embed real credentials. Add authenticated encrypted transport if networking is added, watchdog/recovery and independent hardware interlocks where required.'},
         {'step':12,'title':'Record evidence and iterate','detail':'Save test method, expected/observed results, current draw and limitations. Physical tests and simulations remain not-run until actual evidence is recorded. Review improvements without overwriting unrelated code.'}
      ],
      'testing':{'static':'Graph rules and source structure only; use Run static checks for a dated result.','compilation':'not_run_no_toolchain','simulation':'not_run_no_simulator','physical':'not_run_hardware_required',
                 'plan':['Continuity/polarity/voltage check','Known-reference sensor comparison','Fail-safe disconnect and reset test','Actuator dwell/cooldown and thermal test','Serial telemetry and calibration verification']},
      'limitations':['Connection-level design, not a PCB layout or electrical simulator.','Breakout clones, power tolerances, sensor accuracy and physical packaging require verification.',*fw.get('warnings',[])],
      'improvements':req.get('improvements') or ['Measure real power and latency','Add calibrated reference measurements','Add protected enclosure and strain relief','Add a secure dashboard / connectivity after validating local behavior'],
      'references':list(dict.fromkeys(cat[n['model']]['reference'] for n in g['components']))}


def make_spec(name,req,g,conn=None):
    fw=circuits.firmware(g,conn)
    return {'schema':'nexus.project/1','name':name,'requirements':req,'circuit':g,'firmware':fw,
            'guide':guide(req,g,fw,conn),'assumptions':req.get('assumptions',[]),
            'testing':[],'research':[],'debugging':[], 'concept_images':[],
            'quality':{'physical_tested':False,'simulation_run':False,'status':'incomplete_unsupported_components' if req.get('unsupported_components') else 'draft_rule_checked'}}


def create(conn,ent,name,req,g):
    entitlements.require_feature(ent,'workspace.basic');circuits.check(g,conn)
    entitlements.consume(conn,ent,'project_created',meta={'kind':'engineering_design'})
    name=str(name).strip()[:120] or 'Untitled engineering design';spec=make_spec(name,req,g,conn);pid=jobs.uid();now=time.time()
    conn.execute('INSERT INTO engineering_projects VALUES (?,?,?,?,1,?,?)',(pid,ent['user_id'],name,json.dumps(spec),now,now))
    conn.execute('INSERT INTO engineering_versions(project_id,revision,spec_json,summary,created_at) VALUES (?,1,?,?,?)', (pid,json.dumps(spec),'Initial design',now))
    db.audit(conn,ent['user_id'],'design.create',pid,{'components':len(g['components'])})
    return view(owned(conn,ent,pid),conn)


def save(conn,ent,pid,revision,patch,summary='Saved design'):
    owned(conn,ent,pid)
    conn.execute('BEGIN IMMEDIATE')
    try:
        r=owned(conn,ent,pid)
        if revision!=r['revision']:raise ApiError(409,'A newer revision exists. Reload before saving to avoid overwriting changes.','revision_conflict',{'revision':r['revision']})
        spec=json.loads(r['spec_json']);sync={'changed':False}
        if 'circuit' in patch:
            entitlements.require_feature(ent,'tools.circuit_designer');g=copy.deepcopy(patch['circuit']);circuits.check(g,conn)
            spec['firmware'],sync=circuits.sync(spec['firmware'],g,conn);spec['circuit']=g
        if 'firmware' in patch:
            entitlements.require_feature(ent,'tools.code_engineer')
            f=patch['firmware']
            if not isinstance(f,dict) or not isinstance(f.get('code'),str) or len(f['code'])>120000:raise ApiError(400,'Firmware must be a code string up to 120,000 characters.','invalid_input')
            spec['firmware']['code']=f['code'];spec['firmware']['user_edited']=True
            if isinstance(f.get('libraries'),list): spec['firmware']['libraries']=[str(x)[:150] for x in f['libraries'][:40]]
            # Saving user/AI source cannot certify graph synchronization.
            if circuits.managed(spec['circuit'],conn) not in f['code']: spec['firmware']['mismatch']=True
            if f.get('accept_generated'):
                proposed=circuits.firmware(spec['circuit'],conn)
                if f['code']!=proposed['code']:raise ApiError(400,'Generated source changed; preview again.','invalid_input')
                spec['firmware']=proposed
        for k in ('requirements','research','debugging','testing'):
            if k in patch:
                if len(json.dumps(patch[k]))>100000:raise ApiError(400,'Project section too large.','too_large')
                if k=='requirements' and not isinstance(patch[k],dict):raise ApiError(400,'requirements must be an object.','invalid_input')
                if k in ('research','debugging','testing') and not isinstance(patch[k],list):raise ApiError(400,k+' must be a list.','invalid_input')
                spec[k]=patch[k]
        name=str(patch.get('name',r['name']))[:120];spec['name']=name
        spec['guide']=guide(spec['requirements'],spec['circuit'],spec['firmware'],conn)
        spec['guide']['references']=list(dict.fromkeys(spec['guide']['references']+[r['url'] for r in spec['research'] if isinstance(r,dict) and str(r.get('url','')).startswith(('https://','http://'))]))
        rev=r['revision']+1;now=time.time();raw=json.dumps(spec)
        conn.execute('UPDATE engineering_projects SET name=?,spec_json=?,revision=?,updated_at=? WHERE id=? AND user_id=?',(name,raw,rev,now,pid,ent['user_id']))
        conn.execute('INSERT INTO engineering_versions(project_id,revision,spec_json,summary,created_at) VALUES (?,?,?,?,?)',(pid,rev,raw,str(summary)[:200],now))
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK');raise
    return {**view(owned(conn,ent,pid),conn),'sync':sync}


def restore(conn,ent,pid,version,revision):
    entitlements.require_feature(ent,'workspace.full');owned(conn,ent,pid)
    r=conn.execute('SELECT * FROM engineering_versions WHERE project_id=? AND revision=?',(pid,version)).fetchone()
    if not r:raise ApiError(404,'Version not found.','not_found')
    previous=json.loads(r['spec_json'])
    result=save(conn,ent,pid,revision,{k:previous[k] for k in ('circuit','firmware','requirements','research','debugging','testing')} ,'Restore revision '+str(version))
    return result


def code_preview(conn,ent,pid):
    entitlements.require_feature(ent,'tools.code_engineer');p=owned(conn,ent,pid);s=json.loads(p['spec_json']);fw=circuits.firmware(s['circuit'],conn)
    diff='\n'.join(difflib.unified_diff(s['firmware']['code'].splitlines(),fw['code'].splitlines(),fromfile='saved/firmware.ino',tofile='proposed/firmware.ino',lineterm=''))
    return {'firmware':fw,'diff':diff,'revision':p['revision'],'warning':'Explicit confirmation replaces the source. Copy/back up custom changes; saved versions remain available.'}


def static_checks(spec,conn=None):
    validation=circuits.validate(spec['circuit'],conn);code=spec['firmware']['code'];findings=[]
    defines=circuits.managed(spec['circuit'],conn)
    if defines not in code:findings.append('Managed pin definitions differ from the circuit or have been removed.')
    if spec['firmware'].get('mismatch'):findings.append('Driver topology is stale after component changes; review/regenerate drivers.')
    # Do not execute uploaded/generated code. Only deterministic syntax/structure checks.
    if spec['firmware'].get('language')=='python':
        try:ast.parse(code)
        except SyntaxError as e:findings.append('Python parse error on line '+str(e.lineno))
    else:
        if code.count('{')!=code.count('}'):findings.append('C++ brace balance differs (not a compiler check).')
        if not all(x in code for x in ('void setup(', 'void loop(')):findings.append('Arduino setup()/loop() entry points missing.')
    if spec['firmware'].get('status')=='incomplete':findings.append('Firmware has unassigned or unsupported driver sections.')
    return {'kind':'static','at':time.time(),'passed':validation['passed'] and not findings,
            'code_findings':findings,'circuit':validation,'compiler':{'status':'not_run','reason':'No Arduino toolchain installed; arbitrary user code is never executed on this server.'},
            'simulation':{'status':'not_run','reason':'No electrical simulator configured.'},
            'physical':{'status':'not_run','reason':'Requires real hardware and measured evidence.'}}


def report(row,conn=None):
    s=json.loads(row['spec_json']);g=s['circuit'];fw=s['firmware'];guide=s['guide']
    out=['# '+row['name'],'Project ID: '+row['id']+' · Revision '+str(row['revision']),'\nDRAFT — NOT hardware tested. Concept visuals are not electrical diagrams.',
         '## Objective',guide['objective'],'## Requirements',json.dumps(s['requirements'],indent=2),'## Architecture',guide['architecture'],
         '## Bill of materials','| Instance | Component | Supply V | Assumed mA |','|---|---|---|---|']
    out += ['|'+b['instance']+'|'+b['name']+'|'+str(b['supply_v'])+'|'+str(b['current_ma_assumed'])+'|' for b in guide['bom']]
    out+=['## Circuit','Exact-pin circuit graph is in the companion JSON/SVG export.','## Wiring','| From | To | Signal |','|---|---|---|']
    out+=['|'+w['from']+'|'+w['to']+'|'+w['signal']+'|' for w in circuits.wiring(g,conn)]
    out+=['## Build guide']+['### '+str(x['step'])+'. '+x['title']+'\n'+x['detail'] for x in guide['assembly']]
    out+=['## Firmware','```cpp',fw['code'],'```','## Dependencies']+fw.get('libraries',[])
    out+=['## Testing',json.dumps(s['testing'] or guide['testing'],indent=2),'## Limitations']+guide['limitations']+['## Future iterations']+guide['improvements']+['## References']+guide['references']
    return '\n\n'.join(str(x) for x in out)
