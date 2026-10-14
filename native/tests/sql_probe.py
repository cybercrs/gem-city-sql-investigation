from browser_base import Handler,ROOT
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright
import threading,json
server=ThreadingHTTPServer(('127.0.0.1',0),lambda *a,**kw:Handler(*a,directory=str(ROOT/'dist'),**kw));threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True);page=b.new_page();page.on('console',lambda m:print(m.type,m.text) if m.type=='error' else None);page.on('pageerror',lambda e:print('PAGEERROR',e));page.goto(f'http://127.0.0.1:{server.server_port}/js/');page.wait_for_function("document.documentElement.dataset.ready==='true'")
 result=page.evaluate('''async()=>{const {SQLClient}=await import('./sql-client.js');const {DATA}=await import('./content.js');const c=new SQLClient(DATA.schemaSQL);const out=[];for(const sql of ['SELECT COUNT(*) AS n FROM OrderLines',"SELECT 'update; drop' AS value",'PRAGMA table_info(Orders)','DELETE FROM Orders','WITH x AS (SELECT 1) DELETE FROM Orders','SELECT 1; SELECT 2']){try{out.push({sql,result:await c.execute(sql)});}catch(e){out.push({sql,error:e.message});}}return out;}''');print(json.dumps(result,indent=2));b.close()
server.shutdown()
