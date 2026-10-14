"""Export original SQL teaching content, database and Python outcome fixtures."""
import sys,json,itertools
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'native'))
from capture import load,State,flat
from gem_city_sql_investigation import case_data as c,engine as e,progress as p
from tests.test_engine import ACCOUNTING_SQL,AUDIT_SQL
rec,ns=load(ROOT);rec.column_config=SimpleNamespace(NumberColumn=lambda *a,**k:None,TextColumn=lambda *a,**k:None)
specs=[('reading','r',[(i,a,options) for i,_,options,a,_ in c.READ_QUESTIONS]),('missing','m',[('repair',c.MISSING_REPAIR_CORRECT,c.MISSING_REPAIR_OPTIONS),('cause',c.MISSING_CAUSE_CORRECT,c.MISSING_CAUSE_OPTIONS)]),('amount','a',[('field',c.AMOUNT_FIELD_CORRECT,c.AMOUNT_FIELD_OPTIONS),('cause',c.AMOUNT_CAUSE_CORRECT,c.AMOUNT_CAUSE_OPTIONS)])]
good={g:{i:a for i,a,_ in fields} for g,key,fields in specs};renderers=['render_schema_stage','render_reading','render_missing','render_amount','render_custom','render_debrief']
def state(stage,status):
 s=State(p.activity_defaults());s.si_shuffle_seed=0;s.si_stage=stage
 for index,(g,k,fields) in enumerate(specs,1):
  answers=good[g].copy() if index<stage or index==stage and status!='unanswered' else {}
  if index==stage and status=='wrong':i,a,options=fields[0];answers[i]=next(v for v in options if v!=a)
  s['si_'+g]=answers;s.si_drafts[g]=answers.copy()
  if answers:s.si_attempts[g]=1
 if stage==5:
  s.si_custom={'Accounting report':{'draft':ACCOUNTING_SQL,'submitted':ACCOUNTING_SQL,'passed':True},'Audit exception report':{'draft':AUDIT_SQL,'submitted':AUDIT_SQL,'passed':True}};s.si_attempts.update(accounting=1,audit=1)
 return s
screens=[]
for stage,renderer in enumerate(renderers):
 variants={}
 for status in ['unanswered','wrong','correct']:
  rec.session_state=state(stage,status)
  with rec.capture() as items:ns[renderer]()
  variants[status]=flat(items)
 screens.append(variants)
rec.session_state=state(0,'unanswered')
with rec.capture() as hero:ns['render_hero']()
groups=[]
for stage,(group,key,fields) in enumerate(specs,1):
 screen=screens[stage]['unanswered'];widgets=[n for n in screen if n['kind']=='radio'];first=next(i for i,n in enumerate(screen) if n['kind']=='radio');fs=[]
 for identifier,answer,options in fields:
  widget=next(n for n in widgets if n['key']=='widget_si_'+('read_' if group=='reading' else group+'_')+identifier);feedback={}
  for value in options:
   answers=good[group].copy();answers[identifier]=value;_,details=getattr(e,'evaluate_'+group)(answers);d=next(x for x in details if x['id']==identifier)
   feedback[value]={'correct':d['correct'],'message':d['explanation'] if d['correct'] else 'Hint: '+d['hint'],'label':d.get('prompt',d.get('label'))}
  fs.append({'id':identifier,'answer':answer,'options':list(options),'widget':widget,'feedback':feedback})
 correct=screens[stage]['correct'];last=max(i for i,n in enumerate(correct) if n['kind']=='html' and '<div class="feedback' in n['text']);groups.append({'stage':stage,'id':group,'key':key,'fields':fs,'prefix':screen[:first],'tail':correct[last+1:],'check':next(n['label'] for n in screen if n['kind']=='button')})
connection=e.build_connection();schema='\n'.join(connection.iterdump());connection.close()
prefix=screens[4]['unanswered'];first=next(i for i,n in enumerate(prefix) if n.get('text')=='1. Accounting report');customprefix=prefix[:first]
data={'hero':hero,'stages':list(ns['STAGE_LABELS']),'screens':screens,'groups':groups,'routes':list(c.ROUTES),'prompts':c.ROUTE_PROMPTS,'schemaSQL':schema,'customPrefix':customprefix,'expectedAccounting':c.EXPECTED_ACCOUNTING,'expectedAudit':c.EXPECTED_AUDIT}
(ROOT/'native/content.js').write_text('export const DATA = '+json.dumps(data,ensure_ascii=False,separators=(',',':'))+';\n');(ROOT/'native/original.css').write_text(ns['APP_CSS'].strip().removeprefix('<style>').removesuffix('</style>'))
legacy=[]
for stage in range(6):
 s=state(stage,'correct' if stage else 'unanswered');s.si_shuffle_seed=9223372036854775807;legacy.append({'stage':stage,'token':p.encode_state(s)})
queries=[c.READ_QUERY,c.MISSING_REPAIRED_QUERY,c.AMOUNT_QUERY,ACCOUNTING_SQL,AUDIT_SQL,'SELECT COUNT(*) AS n FROM OrderLines','WITH x AS (SELECT OrderID FROM Orders) SELECT * FROM x ORDER BY OrderID','SELECT lower(CustomerName) AS Name FROM Customers ORDER BY Name','SELECT OrderID,ROW_NUMBER() OVER (ORDER BY OrderID) AS N FROM Orders','SELECT 2.675 AS Value, NULL AS Empty']
outcomes=[]
for q in queries:
 result=e.execute_read_only(q);outcomes.append({'sql':q,'columns':result.columns,'rows':result.rows})
(ROOT/'native/tests/python-oracles.json').write_text(json.dumps({'legacy':legacy,'queries':outcomes,'accountingSQL':ACCOUNTING_SQL,'auditSQL':AUDIT_SQL,'rounding':[{'value':v,'digits':d,'expected':round(v,d)} for v in [2.675,1.005,-.125,.005,1695.001] for d in [0,1,2]]},indent=2)+'\n');print('Exported six original SQL stages, all choice feedback, exact database and query fixtures')
