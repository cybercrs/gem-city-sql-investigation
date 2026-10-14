/** Worker lifetime owns cancellation. No learner query blocks the main thread. */
export class SQLClient{
 constructor(schema){this.schema=schema;this.pending=null;this.counter=0;}
 cancel(){if(!this.pending)return false;const p=this.pending;this.pending=null;clearTimeout(p.timer);p.worker.terminate();p.reject(Error('Query cancelled.'));return true;}
 execute(sql){this.cancel();return new Promise((resolve,reject)=>{const worker=new Worker(new URL('./sql-worker.js',import.meta.url),{type:'module'}),id=++this.counter;const finish=()=>{clearTimeout(p.timer);worker.terminate();if(this.pending===p)this.pending=null;};const p={worker,reject,timer:setTimeout(()=>{finish();reject(Error('Query stopped after the activity execution limit.'));},4000)};this.pending=p;worker.onmessage=event=>{if(event.data.id!==id)return;finish();if(event.data.error)reject(Error(event.data.error));else resolve(event.data.result);};worker.onerror=()=>{finish();reject(Error('SQLite could not initialize. Reload the page and try again.'));};worker.postMessage({id,sql,schema:this.schema});});}
}
