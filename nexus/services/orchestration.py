"""Conservative action routing: ordinary questions remain conversational.

Explicit UI tools always win. Automatic routing only recognizes an unambiguous
request to generate an image or perform a supported saved-project operation.
It never manufactures a successful tool result or forces every engineering
question into a workflow.
"""
import json
import re
from .. import entitlements
from ..errors import ApiError

ACTIONS={'auto','chat','invention','validate','report','code'}


def choose_action(text,requested='auto'):
    if requested not in ACTIONS:raise ApiError(400,'Unsupported assistant action.','invalid_input')
    if requested!='auto':return requested
    if re.match(r'\s*(validate|check) (my|the|this) (saved )?circuit\b',text,re.I):return 'validate'
    if re.match(r'\s*(create|generate|design) (a )?new (iot )?(invention|prototype project)\b',text,re.I):return 'invention'
    return 'chat'


def execute(conn,ent,action,text,project_id,cid,mid,opts):
    from . import invention,designs,circuits
    if action=='invention':
        r=invention.plan(conn,ent,text,project_id=project_id,do_research=bool(opts.get('research')))
        return {'text':json.dumps(r['proposal'],indent=2),'project_id':r['project_id'],'tool_result':'invention','proposal':r}
    if action in ('validate','report','code'):
        if not project_id:raise ApiError(400,'Select a saved project for this action, or use ordinary chat.','project_required')
        p=designs.owned(conn,ent,project_id);spec=json.loads(p['spec_json'])
        if action=='validate':
            entitlements.require_feature(ent,'tools.circuit_designer');r=circuits.validate(spec['circuit'],conn)
            return {'text':json.dumps(r,indent=2),'project_id':project_id,'tool_result':'rule_validation'}
        if action=='report':
            entitlements.require_feature(ent,'exports');return {'text':designs.report(p,conn),'project_id':project_id,'tool_result':'saved_state_report'}
        r=designs.code_preview(conn,ent,project_id)
        return {'text':'Proposed driver rebuild (not applied). Review in Code Engineer.\n```diff\n'+r['diff']+'\n```','project_id':project_id,'tool_result':'code_preview'}
    raise ApiError(400,'Action not supported.','invalid_input')
