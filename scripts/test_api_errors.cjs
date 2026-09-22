const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../frontend/node_modules/typescript');
const source = fs.readFileSync(path.join(__dirname,'../frontend/src/lib/api.ts'),'utf8');
const compiled = ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const api={};new Function('exports',compiled)(api);
const json=(data,status)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
(async()=>{
 await assert.rejects(api.readApiResponse(json({detail:'Method Not Allowed'},405)),/HTTP 405:.*Method Not Allowed.*khởi động lại/);
 await assert.rejects(api.readApiResponse(json({detail:[{loc:['body','revision'],msg:'Field required'}]},422)),/HTTP 422:.*body.revision: Field required/);
 await assert.rejects(api.readApiResponse(json({error:'Báo cáo vừa được thay đổi'},409)),/HTTP 409: Báo cáo vừa được thay đổi/);
 await assert.rejects(api.readApiResponse(new Response('Internal Server Error',{status:500})),/HTTP 500:.*run_local.py/);
 await assert.rejects(api.readApiResponse(new Response('<html>Proxy page</html>',{status:200})),/HTTP 200: Server không trả JSON/);
 assert.deepEqual(await api.readApiResponse(json({deleted:true},200)),{deleted:true});
 console.log('PASS API error detail, 405, 422, 409, plain-text 500, invalid 200 and delete success.');
})().catch(error=>{console.error(error);process.exit(1)});
