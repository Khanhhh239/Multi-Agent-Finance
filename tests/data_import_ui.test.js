"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const context=vm.createContext({});new vm.Script(fs.readFileSync('review_ui/data_import.js','utf8')).runInContext(context);
test('upload error table escapes untrusted headers, values and repair text',()=>{
  const html=context.DataImportUI.errorsTable({error_count:1,errors:[{row:2,column:'<script>x</script>',message:'<img src=x onerror=x>',fix:'" onclick="bad'}]});
  assert.doesNotMatch(html,/<script|<img|" onclick="/);assert.match(html,/&lt;script&gt;/);assert.match(html,/Cách sửa/);
});
test('normalized preview keeps identifier zeros and escapes transaction text',()=>{
  const html=context.DataImportUI.rowsTable([{transaction_id:'00001',company_id:'<svg/onload=x>',amount_vnd:'100'}]);
  assert.match(html,/00001/);assert.doesNotMatch(html,/<svg/);assert.match(html,/&lt;svg/);
});
