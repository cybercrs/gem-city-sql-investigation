/** Dedicated worker: real SQLite parser, query-only database and C authorizer. */
import sqlite3InitModule from './vendor/sqlite3.mjs';
let sqlite;const initialization=sqlite3InitModule().then(s=>sqlite=s);
export async function execute(sql,schema){await initialization;if(typeof sql!=='string'||!sql.trim())throw Error('Write a query before running it.');if(sql.length>8000)throw Error('The query is too long for this activity.');if(sql.includes('\0'))throw Error('The query contains an invalid character.');const {capi:c,wasm:w}=sqlite,db=new sqlite.oo1.DB(':memory:','c');let statement=0;const scope=w.scopedAllocPush();try{
 db.exec(schema);db.exec('PRAGMA query_only=ON');c.sqlite3_limit(db.pointer,c.SQLITE_LIMIT_LENGTH,1048576);c.sqlite3_limit(db.pointer,c.SQLITE_LIMIT_SQL_LENGTH,32000);
 const allowed=new Set([c.SQLITE_SELECT,c.SQLITE_READ,c.SQLITE_FUNCTION,c.SQLITE_RECURSIVE]);let selected=false;
 const auth=c.sqlite3_set_authorizer(db.pointer,(_context,op,_arg1,arg2)=>{if(op===c.SQLITE_SELECT)selected=true;if(op===c.SQLITE_FUNCTION&&['load_extension','readfile','writefile'].includes(String(arg2).toLowerCase()))return c.SQLITE_DENY;return allowed.has(op)?c.SQLITE_OK:c.SQLITE_DENY;},0);if(auth!==c.SQLITE_OK)throw Error('SQLite readonly enforcement could not initialize.');
 const deadline=performance.now()+1500;c.sqlite3_progress_handler(db.pointer,1000,()=>performance.now()>deadline?1:0,0);
 const sqlPtr=w.scopedAllocCString(sql),end=sqlPtr+w.jstrlen(sql),pp=w.scopedAlloc(2*w.ptrSizeof),tail=pp+w.ptrSizeof;let position=sqlPtr,count=0;
 // Parse every statement without stepping any. Semicolons inside strings/comments
 // remain valid; multiple actual statements are rejected before execution.
 while(position<end){w.pokePtr([pp,tail],0);const rc=c.sqlite3_prepare_v3(db.pointer,position,end-position,0,pp,tail);const ptr=w.peekPtr(pp);if(rc!==c.SQLITE_OK){if(ptr)c.sqlite3_finalize(ptr);throw Error('SQLite could not run the query: '+c.sqlite3_errmsg(db.pointer));}const next=w.peekPtr(tail);if(ptr){count++;if(count>1){c.sqlite3_finalize(ptr);throw Error('Run one query at a time.');}statement=ptr;}if(!next||next<=position)break;position=next;}
 if(!statement||!selected||!c.sqlite3_stmt_readonly(statement)||c.sqlite3_column_count(statement)===0)throw Error('This lab accepts only readonly SELECT queries, including WITH queries.');
 const columns=Array.from({length:c.sqlite3_column_count(statement)},(_,i)=>c.sqlite3_column_name(statement,i));const rows=[];let rc,bytes=0;
 while((rc=c.sqlite3_step(statement))===c.SQLITE_ROW){if(rows.length>=100)throw Error('Limit the result to 100 rows or fewer.');const row=columns.map((_,i)=>{const value=c.sqlite3_column_js(statement,i);return typeof value==='bigint'?value.toString():value instanceof Uint8Array?Array.from(value):value;});bytes+=new TextEncoder().encode(JSON.stringify(row)).length;if(bytes>1048576)throw Error('The query output is too large for this activity.');rows.push(row);}
 if(rc!==c.SQLITE_DONE)throw Error(rc===c.SQLITE_INTERRUPT?'Query stopped after the activity execution limit.':'SQLite could not run the query: '+c.sqlite3_errmsg(db.pointer));return {columns,rows,sqliteVersion:c.sqlite3_libversion()};
 }finally{if(statement)c.sqlite3_finalize(statement);w.scopedAllocPop(scope);db.close();}}
self.onmessage=async event=>{const {id,sql,schema}=event.data;try{const result=await execute(sql,schema);self.postMessage({id,result});}catch(error){self.postMessage({id,error:error.message});}};
