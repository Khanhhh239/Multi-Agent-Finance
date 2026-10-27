"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const {environment}=require('./review_evidence_ui.test.js');
const base={job_id:'SIM_JOB',company_id:'C001',channel:'email',kind:'review_submitted',event_label:'Có kết quả chờ kiểm tra',
 status:'simulated',created_at:'2026-10-27T10:00:00+07:00',body:'MÔ PHỎNG hồ sơ http://127.0.0.1:8795/#scenario=003&case=RC_1',
 case_links:[{url:'http://127.0.0.1:8795/#scenario=003&case=RC_1'}],recipient:'chief@example.invalid',attempts:1,
 recipient_users:[{display_name:'MÔ PHỎNG Bình',role:'chief_accountant'}],history_complete:true,
 history:[{kind:'queued',event_at:'2026-10-27T10:00:00+07:00',data:{payload:{body:'Nội dung khi xếp lịch'}}},
 {kind:'attempt_started',event_at:'2026-10-27T10:01:00+07:00',data:{attempt:1}},
 {kind:'simulated',event_at:'2026-10-27T10:01:00+07:00',data:{attempt:1,provider_id:'simulation:SIM_JOB'}}]};
function render(changes={}){const e=environment(path.resolve('review_ui/app.js'));e.context.job={...base,...changes};return e.eval('notificationJob(job)');}
test('event, company, actual configured role/name and destination are visible',()=>{
 const html=render();for(const value of ['Có kết quả chờ kiểm tra','C001','MÔ PHỎNG Bình','Kế toán trưởng','chief@example.invalid'])assert.ok(html.includes(value));
 assert.doesNotMatch(html,/Ưu tiên cao<\/strong>/);
});
test('history shows queue, attempt, simulation and original body',()=>{
 const html=render();for(const value of ['Lịch sử gửi · 3 mốc','Đã xếp lịch','Bắt đầu lần gửi','Đã giả lập','Nội dung khi xếp lịch','giờ Việt Nam','lần 1'])assert.ok(html.includes(value));
});
test('provider acceptance is distinct from receipt/read acknowledgement',()=>{
 const html=render({status:'sent',history:[{kind:'user_received_message',event_at:base.created_at,data:{}},{kind:'user_seen_message',event_at:base.created_at,data:{}}]});
 assert.match(html,/Dịch vụ đã chấp nhận/);assert.match(html,/chưa xác nhận người nhận đã nhận\/đọc/);assert.match(html,/Zalo xác nhận đã nhận/);assert.match(html,/Zalo xác nhận đã xem/);
});
test('uncertain outcome has no implicit resend button',()=>{
 const html=render({status:'uncertain'});assert.match(html,/không tự gửi lại/);assert.doesNotMatch(html,/<button/);
});
test('retry history exposes next attempt time and sanitized code',()=>{
 const html=render({history:[{kind:'retry_scheduled',event_at:base.created_at,data:{attempt:2,error_code:'rate_limit',next_at:'2026-10-27T11:00:00+07:00'}}]});
 assert.match(html,/Hẹn thử lại/);assert.match(html,/Thử lại từ/);assert.match(html,/rate_limit/);assert.match(html,/lần 2/);
});
test('all stored recipient/content/provider fields are escaped',()=>{
 const html=render({event_label:'<img>',recipient:'<img>',recipient_users:[{display_name:'<script>',role:'director'}],
 history:[{kind:'sent',event_at:base.created_at,data:{provider_id:'<img src=x>',error_code:'<script>'}}]});
 assert.doesNotMatch(html,/<img|<script/);assert.match(html,/&lt;script&gt;/);assert.match(html,/&lt;img/);
});
test('old outbox explicitly discloses missing pre-migration history',()=>assert.match(render({history:[],history_complete:false}),/không suy lại các lần gửi cũ/));
const response=()=>({mode:'dry_run',daily_case_limit:10,weekly_weekday:0,weekly_hour:8,counts:{simulated:1},used_by_company:{C001:1},items:[base],
 role_policy:{enabled:true,events:{review_submitted:'Có kết quả chờ kiểm tra'},reminders:{review_due_hours:48,rework_due_hours:48,repeat_hours:24,escalate_after_hours:48}},
 routing_gaps:[{company_id:'C001',case_id:'RC_2',kind:'review_submitted',reason:'recipient_unassigned'}]});
async function modal(changes){const e=environment(path.resolve('review_ui/app.js'));e.context.result={...response(),...changes};e.eval('api=async()=>result;showModal=(title,html)=>{document.getElementById("modal-body").innerHTML=html;};');await e.eval('notificationsModal()');return e.nodes['modal-body'].innerHTML;}
test('accountant can see history but cannot run preview',async()=>{const html=await modal({can_preview:false});assert.doesNotMatch(html,/id="notification-preview"/);assert.match(html,/Lịch sử gửi/);});
test('chief can run dry preview and see policy/default deadlines',async()=>{const html=await modal({can_preview:true});assert.match(html,/id="notification-preview"/);assert.match(html,/Sự kiện và người nhận/);assert.match(html,/48 giờ/);assert.match(html,/24 giờ/);});
test('live page cannot trigger transport from UI',async()=>assert.doesNotMatch(await modal({mode:'live',can_preview:true}),/id="notification-preview"/));
test('missing recipient is surfaced without creating accounts',async()=>{const html=await modal({});assert.match(html,/RC_2/);assert.match(html,/chưa có người nhận phù hợp/);assert.match(html,/không tự gán tài khoản/);});
test('budget gap and unverified real delivery are explicit',async()=>{const html=await modal({routing_gaps:[{company_id:'C001',case_id:'RC_4',kind:'review_submitted',reason:'daily_budget'}]});assert.match(html,/chờ ngân sách ngày/);assert.match(html,/chưa có biên bản xác nhận gửi–nhận thực tế/);});
