from browser_base import run
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1];DATA=json.loads((ROOT/'content.js').read_text().removeprefix('export const DATA = ').removesuffix(';\n'));ORACLE=json.loads((Path(__file__).parent/'python-oracles.json').read_text())
def walk(page,origin,ready,click,passed,out):
 actual=page.evaluate(r'''async queries=>{const {SQLClient}=await import('./sql-client.js');const {DATA}=await import('./content.js');const client=new SQLClient(DATA.schemaSQL);const results=[];for(const q of queries)results.push(await client.execute(q));return results;}''',[q['sql'] for q in ORACLE['queries']])
 for a,o in zip(actual,ORACLE['queries']):assert a['columns']==o['columns'] and a['rows']==o['rows'],(a,o)
 passed('Real SQLite 3.50.4 worker results match ten original Python queries, joins, CTEs, functions, window functions and NULLs')
 enforcement=page.evaluate(r'''async()=>{const {SQLClient}=await import('./sql-client.js');const {DATA}=await import('./content.js');const c=new SQLClient(DATA.schemaSQL),rejected=[];for(const q of ['DELETE FROM Orders',"INSERT INTO Orders VALUES ('X','X','X','X')",'UPDATE Orders SET OrderStatus=\'X\'','DROP TABLE Orders','CREATE TABLE X(Y)','ALTER TABLE Orders ADD X','ATTACH DATABASE \'x\' AS x','PRAGMA table_info(Orders)','BEGIN','COMMIT','WITH x AS (SELECT 1) DELETE FROM Orders','SELECT load_extension(\'x\')','SELECT 1; SELECT 2']){try{await c.execute(q);rejected.push(false);}catch{rejected.push(true);}}const strings=await c.execute("SELECT 'update; drop' AS Text /* DELETE FROM Orders */");let rowLimit=false;try{await c.execute('WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x WHERE n<101) SELECT n FROM x');}catch(e){rowLimit=e.message.includes('100 rows');}let timeout=false;const start=performance.now();try{await c.execute('WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT sum(n) FROM x');}catch(e){timeout=/execution limit/.test(e.message);}return {rejected,strings,rowLimit,timeout,elapsed:performance.now()-start,recovered:await c.execute('SELECT COUNT(*) AS n FROM OrderLines')};}''')
 assert all(enforcement['rejected']);assert enforcement['strings']['rows']==[['update; drop']];assert enforcement['rowLimit'] and enforcement['timeout'];assert enforcement['recovered']['rows']==[[6]];passed('Engine authorizer/query-only enforcement rejects mutations, PRAGMA, attachments, transactions, extensions and multiple statements; literals/comments remain valid; row/time limits recover')
 click(page,'Begin reading SQL')
 for g in DATA['groups']:
  def choose(f,value):page.locator('input').evaluate_all('(nodes,p)=>nodes.find(x=>x.name===p[0]&&x.value===p[1]).click()',[f['widget']['key'],value]);ready(page)
  click(page,g['check'])
  for f in g['fields']:choose(f,next(x for x in f['options'] if x!=f['answer']))
  click(page,g['check']);assert page.get_by_role('button',name='Forward',exact=True).is_disabled()
  choose(g['fields'][0],g['fields'][0]['answer']);page.reload();ready(page);assert page.locator('input:checked').evaluate_all('(nodes,p)=>nodes.some(x=>x.name===p[0]&&x.value===p[1])',[g['fields'][0]['widget']['key'],g['fields'][0]['answer']]);click(page,'Back');click(page,'Forward')
  for f in g['fields']:choose(f,f['answer'])
  click(page,'Check revised answers');click(page,next(n['label'] for n in g['tail'] if n['kind']=='button'));passed(g['id']+': wrong choices, independent feedback, revised drafts across refresh, validated advance')
 def check_sql(route,sql):
  key='accounting' if route=='Accounting report' else 'audit';page.locator('#'+key+'-sql').fill(sql);ready(page);click(page,'Check '+route.lower());page.wait_for_function("!document.querySelector('button') || !Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Cancel query')");ready(page)
 check_sql('Accounting report','SELECT 1 AS X, 2 AS X, NULL AS Missing');cells=page.locator('#accounting-output tbody td').all_text_contents();assert cells==['1','2','NULL'],cells
 with page.expect_download() as download:page.locator('#accounting-output').get_by_role('button',name='Download table as CSV').click()
 downloaded=download.value;downloaded.save_as(out/'duplicate-columns.csv');assert '"1","2",""' in (out/'duplicate-columns.csv').read_text();passed('Real query output preserves duplicate columns and NULL display; CSV download preserves raw data')
 check_sql('Accounting report','DELETE FROM Orders');assert page.get_by_text('SQLite could not run the query: not authorized',exact=True).is_visible();assert page.get_by_role('button',name='Complete the SQL investigation',exact=True).count()==0
 long='WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT sum(n) FROM x';page.locator('#accounting-sql').fill(long);ready(page);before=page.url;click(page,'Check accounting report');page.get_by_role('button',name='Cancel query',exact=True).click();ready(page);assert page.locator('#accounting-sql').input_value()==long;assert page.url==before;passed('Main-thread cancellation retains SQL draft and earned/attempt state')
 page.locator('#accounting-sql').fill(ORACLE['accountingSQL']);ready(page);page.locator('#audit-sql').fill(ORACLE['auditSQL'][:80]);ready(page);before=page.url;click(page,'Back');click(page,'Forward');assert page.locator('#audit-sql').input_value()==ORACLE['auditSQL'][:80];page.reload();ready(page);assert page.locator('#accounting-sql').input_value()==ORACLE['accountingSQL'];assert page.locator('#audit-sql').input_value()==ORACLE['auditSQL'][:80]
 check_sql('Accounting report',ORACLE['accountingSQL']);assert page.get_by_role('button',name='Complete the SQL investigation',exact=True).count()==0
 # Rechecking a correct report retains the original repeat/attempt behavior.
 click(page,'Check accounting report');page.wait_for_function("!Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Cancel query')");ready(page)
 check_sql('Audit exception report',ORACLE['auditSQL']);assert page.get_by_text('17.6%',exact=True).is_visible();page.screenshot(path=str(out/'reports-desktop.png'),full_page=True)
 with page.expect_download() as download:page.locator('#audit-output').get_by_role('button',name='Download table as CSV').click()
 download.value.save_as(out/'audit-report.csv');csv=(out/'audit-report.csv').read_text();assert 'OL04' in csv and 'OL06' in csv and 'DiscountPct' in csv;click(page,'Complete the SQL investigation');saved=page.url;passed('Both original reports complete, repeated checks, raw CSV, currency/percentage display and independently restored editor drafts')
 for fixture in ORACLE['legacy']:
  page.goto(origin+'?progress='+fixture['token']+'&view=999');ready(page);assert page.locator('html').get_attribute('data-reached')==str(fixture['stage'])
 page.goto(saved);ready(page);passed('All six original Python links import with real saved-query revalidation; future views rejected')
run(walk)
