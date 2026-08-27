/* 打工人·上班族物语 WebUI v1.0.0 */
"use strict";
var curKind="wealth",allStk=[];
function $(s){return document.querySelector(s)}
function $$(s){return Array.from(document.querySelectorAll(s))}
function esc(s){return String(s??"").replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
function fmtT(ts){var d=new Date(ts*1e3),p=function(n){return String(n).padStart(2,"0")};return p(d.getMonth()+1)+"/"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes())}
function toast(msg,cls){var b=document.getElementById("toastBox");if(!b)return;
  var t=document.createElement("div");t.className="toast-msg "+(cls||"");t.textContent=msg;
  b.appendChild(t);setTimeout(function(){t.classList.add("toast-hide");setTimeout(function(){t.remove()},380)},2600)}

async function api(url,opt){opt=opt||{};var r=await fetch(url,opt);
  if(r.status===401){showLogin();throw new Error("unauthorized")}
  if(!r.ok){var b=await r.json().catch(function(){return{}});throw new Error(b.error||String(r.status))}
  return r.headers.get("content-type")?.includes("json")?r.json():r.text()}
function jget(u){return api(u)}
async function jpost(u,body){return api(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})})}

/* ===== 登录 ===== */
function showLogin(){document.getElementById("loginOverlay").classList.add("show")}
function hideLogin(){document.getElementById("loginOverlay").classList.remove("show")}
function playEnterFx(){var b=document.body;
  b.classList.remove("authed");void b.offsetWidth;b.classList.add("authed")}
/* ===== 自定义确认弹窗 ===== */
var _askResolve=null,_askKeys=null;
function closeAsk(v){
  var mask=document.getElementById("askMask");
  if(!mask||!mask.classList.contains("show"))return;
  mask.classList.remove("show");
  document.removeEventListener("keydown",_askKeys);
  if(_askResolve){var r=_askResolve;_askResolve=null;r(v)}
}
function askConfirm(msg,opt){
  opt=opt||{};
  var mask=document.getElementById("askMask");
  if(!mask)return Promise.resolve(window.confirm(msg));
  document.getElementById("askIco").textContent=opt.icon||"⚠️";
  document.getElementById("askTitle").textContent=opt.title||"确认操作";
  document.getElementById("askMsg").innerHTML=msg;
  var yes=document.getElementById("askYes"),no=document.getElementById("askNo");
  yes.textContent=opt.yes||"确定";
  no.textContent=opt.no||"取消";
  yes.className="btn "+(opt.danger===false?"":"btn-red");
  no.className="btn btn-ghost";
  mask.classList.add("show");
  setTimeout(function(){yes.focus()},140);
  return new Promise(function(res){
    _askResolve=res;
    _askKeys=function(e){
      if(e.key==="Escape")closeAsk(false);
      else if(e.key==="Enter")closeAsk(true)};
    document.addEventListener("keydown",_askKeys);
  });
}

async function doLogin(){
  var btn=document.querySelector("#loginCard .btn");
  var card=document.getElementById("loginCard");
  var pwd=document.getElementById("loginPwd");
  btn.disabled=true;btn.textContent="验证中…";
  try{
    await jpost("/api/auth/login",{password:pwd.value});
    card.classList.add("out");
    setTimeout(function(){
      hideLogin();card.classList.remove("out");pwd.value="";
      playEnterFx();toast("解锁成功","ok");loadAll();
    },430);
  }catch(e){
    document.getElementById("loginErr").textContent="密码错误";
    card.classList.remove("shake","err");void card.offsetWidth;
    card.classList.add("shake","err");
    setTimeout(function(){card.classList.remove("err")},650);
  }finally{btn.disabled=false;btn.textContent="解 锁"}
}
jget("/api/auth/check").then(function(r){
  if(r.required&&!r.ok)showLogin()}).catch(function(){});

/* ===== 星尘 ===== */
(function(){var box=document.getElementById("starField");if(!box)return;
  for(var i=0;i<42;i++){var s=document.createElement("i");s.className="star";
    s.style.left=Math.random()*100+"vw";s.style.top=Math.random()*100+"vh";
    s.style.animationDelay=(Math.random()*4).toFixed(1)+"s";
    s.style.animationDuration=(2+Math.random()*3).toFixed(1)+"s";
    s.style.width=s.style.height=(Math.random()*2+1).toFixed(1)+"px";
    box.appendChild(s)}})();

/* ===== 滚动进度条 ===== */
(function(){var bar=document.getElementById("scrollProgress");if(!bar)return;
  var ticking=false;
  function upd(){
    var h=document.documentElement;
    var max=h.scrollHeight-h.clientHeight;
    var p=max>0?Math.min(1,(h.scrollTop||document.body.scrollTop)/max):0;
    bar.style.transform="scaleX("+p+")";
    bar.classList.toggle("on",p>0.002);
    ticking=false}
  window.addEventListener("scroll",function(){if(!ticking){requestAnimationFrame(upd);ticking=true}},{passive:true});
  window.addEventListener("resize",upd);upd()})();

/* ===== 时钟 ===== */
setInterval(function(){var d=new Date(),p=function(n){return String(n).padStart(2,"0")};
  var el=document.getElementById("liveClock");
  if(el)el.textContent="🕐 "+p(d.getHours())+":"+p(d.getMinutes())+":"+p(d.getSeconds())},1000);

/* ===== 实时动态：面板激活时每 10 秒自动刷新 ===== */
setInterval(function(){
  var p=document.getElementById("p-feed");
  if(p&&p.classList.contains("on"))loadOverview()},10000);

/* ===== 通用空状态 ===== */
function emptyState(icon,text){return '<div class="empty-state"><div style="font-size:26px;margin-bottom:6px">'+icon+'</div><div>'+esc(text)+'</div></div>'}
function skeletonRow(){return '<tr><td colspan="5"><div class="skeleton"></div></td></tr>'}

/* ===== 元数据 ===== */
async function loadMeta(){try{var m=await jget("/api/meta");
  document.getElementById("metaVer").textContent=m.version||"v1.0.0";
  document.getElementById("metaPort").textContent="端口 "+(m.port||17817);
  var fv=document.getElementById("footerVer");
  if(fv)fv.textContent="astrbot_plugin_shangbanzu "+(m.version||"v1.0.0");
  var lock=document.getElementById("lockBadge");
  if(lock)lock.style.display=m.auth_required?"inline-flex":"none";
}catch(e){console.warn(e)}}

/* ===== 总览 ===== */
/* ===== 总览 ===== */
function countUp(el,target){
  var start=null,dur=900;
  function step(ts){
    if(!start)start=ts;
    var p=Math.min(1,(ts-start)/dur),e=1-Math.pow(1-p,3);
    el.textContent=Math.round(target*e).toLocaleString();
    if(p<1)requestAnimationFrame(step)}
  requestAnimationFrame(step)}
async function loadOverview(){try{
  var o=await jget("/api/overview"),s=o.stats||{};
  document.getElementById("newsText").textContent=o.news||"今日无事发生";
  var cards=[[s.players??0,"注册玩家"],[s.groups??0,"游戏群数"],
    [s.events_today??0,"今日动态"],[(s.richest&&s.richest.nickname)||"虚位以待","全服首富"]];
  document.getElementById("statCards").innerHTML=cards.map(function(c,i){
    return '<div class="stat-card" style="animation-delay:'+(i*70)+'ms">'
      +'<div class="num">'+esc(typeof c[0]==="number"?"0":String(c[0]).slice(0,14))+'</div>'
      +'<div class="lab">'+esc(c[1])+'</div></div>'}).join("");
  var nums=document.querySelectorAll("#statCards .num");
  cards.forEach(function(c,i){if(typeof c[0]==="number"&&nums[i])countUp(nums[i],c[0])});
  var hot=["裁员","住院","买房"];
  var feed=document.getElementById("feedList");feed.innerHTML="";
  if(o.events&&o.events.length){
    o.events.forEach(function(ev,i){
      var d=document.createElement("div");
      d.className="feed-item"+(hot.indexOf(ev.kind)>=0?" hot":"");
      d.style.animationDelay=(i*45)+"ms";
      d.innerHTML='<span class="feed-time">'+fmtT(ev.time)+'</span>'
        +'<span class="feed-tag">'+esc(ev.kind)+'</span>'
        +'<span>'+esc(ev.summary)+' <span class="muted">（群 '+esc(ev.gid)+'）</span></span>';
      feed.appendChild(d)});
  }else{feed.innerHTML=emptyState("💬","暂无动态，快去群里玩起来")}
}catch(e){
  document.getElementById("newsText").textContent="暂无早报";
  document.getElementById("feedList").innerHTML=emptyState("⚠️","数据加载失败，请刷新重试");
}}

async function loadGroups(){try{var g=await jget("/api/groups");
  var opts=(g.groups||[]).map(function(x){
    return '<option value="'+esc(x.gid)+'">'+esc(x.name||("群 "+x.gid))+'（'+x.count+'人）</option>'}).join("");;
  ["groupSel","groupSel2","admGroupSel","playerGroupSel"].forEach(function(id){
    var el=document.getElementById(id);if(el)el.innerHTML=opts||'<option value="">暂无群数据</option>'});
}catch(e){}}

async function loadRank(){
  var gid=document.getElementById("groupSel")?.value||"";
  var b=document.getElementById("rankBody");if(!b)return;
  if(!gid){b.innerHTML='<tr><td colspan="4">'+emptyState("📊","暂无群数据，先在群里触发游戏指令")+'</td></tr>';return}
  b.innerHTML='<tr><td colspan="4"><div class="skeleton"></div></td></tr>';
  try{var r=await jget("/api/ranking?gid="+encodeURIComponent(gid)+"&kind="+curKind);
    var rows=r.rows||[];
    b.innerHTML=rows.length?rows.map(function(row,i){
      var medal=row.rank===1?"🥇":row.rank===2?"🥈":row.rank===3?"🥉":row.rank;
      return '<tr><td class="'+(row.rank===1?"rank-gold":"")+'">'+medal+'</td>'
        +'<td>'+esc(row.nickname)+'<br><span class="muted" style="font-size:11px">'+esc(row.uid)+'</span></td>'
        +'<td>'+esc(row.company)+' · '+esc(row.position)+'</td>'
        +'<td style="text-align:right;color:var(--gold);font-weight:bold">'+esc(row.score)+'</td></tr>';
    }).join(""):'<tr><td colspan="4">'+emptyState("📊","该群还没有排行数据")+'</td></tr>';
  }catch(e){b.innerHTML='<tr><td colspan="4">'+emptyState("⚠️","加载失败")+'</td></tr>'}}

function kvItem(l,v){return '<div class="kv-item">'+l+'<b>'+v+'</b></div>'}
function barHtml(l,v,c){var w=Math.max(0,Math.min(100,v));
  setTimeout(function(){document.querySelectorAll(".bar-fill[data-w='"+w+"']").forEach(function(b){b.style.width=w+"%"})},80);
  return '<div class="kv-item">'+l+'<div class="bar-track"><i class="bar-fill" data-w="'+w+'" style="background:'+c+'"></i></div></div>'}
function profileCardHtml(p){
  return '<div class="profile-card"><div class="profile-head">'
    +(p.avatar?'<img class="avatar-lg" src="'+p.avatar+'" onerror="this.style.display=\'none\'">':"")
    +'<div><div style="font-size:18px;font-weight:bold">'+esc(p.nickname)+'</div>'
    +'<div class="muted" style="font-size:12px">'+esc(p.uid)+' · 更新于 '+fmtT(p.updated)+'</div></div></div>'
    +'<div class="info-grid">'
    +kvItem("公司",esc(p.company)+(p.tag?" · "+esc(p.tag):""))
    +kvItem("职位",esc(p.position))
    +kvItem("月薪",p.salary+" 元")
    +kvItem("总资产",p.total+" 元")
    +kvItem("公积金",p.fund_savings+" 元")
    +kvItem("身价",p.value+" 元")
    +kvItem("通勤方式",esc(p.commute))
    +kvItem("调休券",p.comp_leave+" 张")
    +barHtml("❤️ 健康",p.health,"linear-gradient(90deg,#6fe08c,#2fbf71)")
    +barHtml("🧠 精神",p.mind,"linear-gradient(90deg,#7fd1ff,#5b8fd6)")
    +kvItem("卷王段位",esc(p.tier))
    +kvItem("对线战绩",esc(p.duel))
    +'</div></div>'}

async function doSearch(){
  var gid=document.getElementById("groupSel2")?.value||"";
  var kw=document.getElementById("kwInput")?.value?.trim()||"";
  var box=document.getElementById("searchResult");
  if(!gid||!kw){box.innerHTML=emptyState("🔍","请选择群组并输入关键字");return}
  box.innerHTML='<div class="skeleton" style="height:90px"></div>';
  try{var r=await jget("/api/search?gid="+encodeURIComponent(gid)+"&kw="+encodeURIComponent(kw));
    box.innerHTML=(r.results&&r.results.length)?r.results.map(profileCardHtml).join("")
      :emptyState("🔍","未找到该玩家");
  }catch(e){box.innerHTML=emptyState("⚠️","查询失败")}}

/* ===== 股市 ===== */
var stkEdits={};
async function loadStocks(){try{var r=await jget("/api/stocks");allStk=r.stocks||[];renderStk(allStk)}catch(e){
  document.getElementById("stkBody").innerHTML='<tr><td colspan="4">'+emptyState("⚠️","加载失败")+'</td></tr>'}}
function renderStk(list){var b=document.getElementById("stkBody");if(!b)return;
  b.innerHTML=(list&&list.length)?list.map(function(s,i){
    return '<tr><td class="muted" style="font-size:12px">'+esc(s.code)+'</td>'
      +'<td>'+esc(s.name)+'</td>'
      +'<td><div class="stepper">'
      +'<button type="button" class="st-btn" data-step="-1" tabindex="-1" aria-label="减少">−</button>'
      +'<input type="number" step="0.01" min="0.5" class="tx-f stk-price'
      +(stkEdits[s.code]!==undefined?' stk-dirty':'')
      +'" data-code="'+esc(s.code)+'" value="'+(stkEdits[s.code]!==undefined?stkEdits[s.code]:s.price)+'">'
      +'<button type="button" class="st-btn" data-step="1" tabindex="-1" aria-label="增加">+</button></div></td>'
      +'<td style="color:'+(s.chg>=0?"var(--green)":"var(--red)")+';text-align:right">'
      +(s.chg>=0?"+":"")+s.chg+'%</td></tr>';
  }).join(""):'<tr><td colspan="4">'+emptyState("📈","暂无股票数据")+'</td></tr>';
  b.querySelectorAll(".st-btn").forEach(bindStepper)}
document.addEventListener("DOMContentLoaded",function(){
  var b=document.getElementById("stkBody");
  if(b)b.addEventListener("input",function(e){
    var t=e.target;if(!t.classList||!t.classList.contains("stk-price"))return;
    stkEdits[t.dataset.code]=t.value;
    t.classList.add("stk-dirty");
  });
});
async function saveStkEdits(btn){
  var codes=Object.keys(stkEdits).filter(function(c){return parseFloat(stkEdits[c])>0});
  if(!codes.length)return toast("没有改动的价格","warn");
  if(btn){btn.disabled=true;btn.textContent="保存中…"}
  var ok=0;
  try{
    for(var i=0;i<codes.length;i++){
      await jpost("/api/stocks/edit",{code:codes[i],price:parseFloat(stkEdits[codes[i]])});
      ok++}
    document.querySelectorAll(".stk-price").forEach(function(inp){
      if(stkEdits[inp.dataset.code]!==undefined){
        inp.classList.remove("stk-dirty");inp.classList.add("stk-saved")}});
    toast("已更新 "+ok+" 支股票价格","ok");
    setTimeout(function(){stkEdits={};loadStocks()},620);
  }catch(e){toast("保存失败："+e.message,"error")}
  finally{if(btn){btn.disabled=false;btn.textContent="💾 保存改价"}}
}
function filterStk(){var kw=(document.getElementById("stkSearch").value||"").toLowerCase();
  renderStk(allStk.filter(function(s){return !kw||s.code.indexOf(kw)>=0||s.name.toLowerCase().indexOf(kw)>=0}))}
async function fluctuateAll(){try{var r=await api("/api/stocks/fluctuate",{method:"POST"});
  toast("已对 "+r.fluctuated+" 支股票执行波动","ok");loadStocks()}catch(e){toast("操作失败","error")}}
async function randomizeAll(){try{await api("/api/stocks/randomize",{method:"POST"});
  toast("已重置全部股价","ok");loadStocks()}catch(e){toast("操作失败","error")}}

/* ===== 备份 ===== */
async function loadBackups(){try{var r=await jget("/api/backups");var items=r.backups||[];
  var b=document.getElementById("bkBody");if(!b)return;
  b.innerHTML=items.length?items.map(function(bk,i){
    return '<tr><td>'+(i+1)+'</td><td>'+esc(bk.name)+'</td>'
      +'<td>'+bk.size_kb+' KB</td><td class="muted">'+esc(bk.time)+'</td>'
      +'<td style="text-align:right;white-space:nowrap">'
      +'<button class="btn-ghost btn" style="padding:4px 12px;margin-right:6px" onclick="bkRestore(\''+esc(bk.name)+'\')">恢复</button> '
      +'<button class="btn-ghost btn" style="padding:4px 12px;color:var(--red)" onclick="bkDelete(\''+esc(bk.name)+'\')">删除</button></td></tr>';
  }).join(""):'<tr><td colspan="5">' + emptyState("🗄️","暂无备份") + '</td></tr>';
}catch(e){}}
async function bkCreate(){var label=document.getElementById("bkLabel")?.value?.trim()||"";
  try{await jpost("/api/backups/create",{label:label});toast("备份创建成功","ok");loadBackups()}catch(e){toast("备份失败","error")}}
async function bkRestore(name){if(!(await askConfirm("确定用「"+esc(name)+"」覆盖当前全部数据？此操作不可撤销！", {icon:"🗄️",title:"恢复备份",yes:"覆盖恢复"})))return;
  try{await jpost("/api/backups/restore",{name:name});toast("恢复成功","ok");loadBackups()}catch(e){toast("恢复失败","error")}}
async function bkDelete(name){if(!(await askConfirm("确定删除备份「"+esc(name)+"」？删除后无法找回。", {icon:"🗑️",title:"删除备份",yes:"确认删除"})))return;
  try{await jpost("/api/backups/delete",{name:name});toast("已删除","ok");loadBackups()}catch(e){}}

/* ===== 管理 ===== */
async function admSearch(){
  var gid=document.getElementById("admGroupSel")?.value||"";
  var uid=document.getElementById("admUid")?.value?.trim()||"";
  if(!gid||!uid){document.getElementById("admResult").innerHTML=emptyState("🔍","请选择群组并输入关键字");return}
  try{var r=await jget("/api/admin/player?gid="+encodeURIComponent(gid)+"&uid="+encodeURIComponent(uid));
    if(r.error){document.getElementById("admResult").innerHTML=emptyState("🔍",r.error);return}
    document.getElementById("admResult").innerHTML=profileCardHtml(r.profile||r);
  }catch(e){document.getElementById("admResult").innerHTML=emptyState("⚠️","查询失败")}}

/* ===== Tab 切换 ===== */
document.addEventListener("DOMContentLoaded",function(){
  var nav=document.getElementById("mainNav");if(!nav)return;
  var ink=nav.querySelector(".nav-ink");
  function moveInk(btn){if(!ink||!btn)return;ink.style.left=btn.offsetLeft+"px";ink.style.width=btn.offsetWidth+"px"}
  nav.querySelectorAll(".nav-btn[data-p]").forEach(function(btn){
    btn.addEventListener("click",function(){
      nav.querySelectorAll(".nav-btn").forEach(function(b){b.classList.remove("on")});
      btn.classList.add("on");moveInk(btn);
      document.querySelectorAll(".panel").forEach(function(p){p.classList.remove("on")});
      var t=document.getElementById("p-"+btn.dataset.p);
      if(t)t.classList.add("on");
      if(btn.dataset.p==="feed")loadOverview();
      if(btn.dataset.p==="rank"){if(!document.getElementById("groupSel").value)loadGroups();loadRank()}
      if(btn.dataset.p==="backup")loadBackups();
      if(btn.dataset.p==="stocks"){loadGroups().then(loadStocks)}
      if(btn.dataset.p==="company"){ensureCats();loadCompanies()}
      if(btn.dataset.p==="cfg")loadCfg();
      if(btn.dataset.p==="players"){loadGroups().then(function(){loadPlayerList(1)})}
    });
  });
  document.querySelectorAll(".sub-tabs button").forEach(function(btn){
    btn.addEventListener("click",function(){
      document.querySelectorAll(".sub-tabs button").forEach(function(b){b.classList.remove("on")});
      btn.classList.add("on");curKind=btn.dataset.k;loadRank();
    });
  });
  var kw=document.getElementById("kwInput");
  if(kw)kw.addEventListener("keydown",function(e){if(e.key==="Enter")doSearch()});
  var stk=document.getElementById("stkSearch");
  if(stk)stk.addEventListener("input",filterStk);
  initCustomSelects();
  playEnterFx();
  var first=nav.querySelector(".nav-btn.on");
  if(first)setTimeout(function(){moveInk(first)},100);
});

function loadAll(){loadMeta();loadOverview();loadGroups();loadStocks()}

/* ===== 插件配置 ===== */
var cfgSchema={},cfgData={},cfgHidden=[];
async function loadCfg(){
  try{
    var r=await jget("/api/admin/config");
    cfgSchema=r.schema||{};cfgData=r.config||{};cfgHidden=r.hidden_keys||[];
    renderCfg();
  }catch(e){
    var box=document.getElementById("cfgForm");
    if(box)box.innerHTML=emptyState("⚠️","配置加载失败");
  }
}
function renderCfg(){
  var box=document.getElementById("cfgForm");if(!box)return;
  var keys=Object.keys(cfgSchema);
  var meta=document.getElementById("cfgMeta");
  if(meta)meta.textContent="共 "+keys.length+" 项";
  box.innerHTML=keys.length?keys.map(function(k,i){
    var m=cfgSchema[k]||{},v=cfgData[k],tp=m.type||"string",ctrl;
    if(tp==="bool"){
      ctrl='<input type="checkbox" class="sw cfg-in" data-k="'+k+'"'+(v?" checked":"")+'>';
    }else if(tp==="int"||tp==="float"){
      ctrl='<div class="stepper">'
        +'<button type="button" class="st-btn" data-step="-1" tabindex="-1" aria-label="减少">−</button>'
        +'<input type="number" '+(tp==="float"?'step="any"':'step="1"')+' min="0"'
        +' class="cfg-in" data-k="'+k+'" data-tp="'+tp+'" value="'+esc(String(v==null?(m.default==null?0:m.default):v))+'">'
        +'<button type="button" class="st-btn" data-step="1" tabindex="-1" aria-label="增加">+</button></div>';
    }else if(tp==="list"){
      ctrl='<textarea class="cfg-in" data-k="'+k+'" data-tp="list" rows="2" placeholder="每行一个，逗号分隔亦可">'+esc(Array.isArray(v)?v.join("\n"):String(v==null?"":v))+'</textarea>';
    }else{
      var hid=cfgHidden.indexOf(k)>=0;
      ctrl='<input type="'+(hid?"password":"text")+'" class="cfg-in" data-k="'+k+'" data-tp="string"'
        +(hid?' placeholder="已设置 · 输入新值修改，留空不变" autocomplete="new-password"':'')
        +' value="'+esc(hid?"":String(v==null?(m.default==null?"":m.default):v))+'">';
    }
    return '<div class="cfg-row" style="animation-delay:'+(i*35)+'ms"><div class="cfg-info">'
      +'<span class="cfg-name">'+esc(m.description||k)+'</span><span class="cfg-key">'+esc(k)+' · '+esc(tp)+'</span>'
      +(m.hint?'<div class="cfg-hint">'+esc(m.hint)+'</div>':"")
      +'</div><div class="cfg-ctrl">'+ctrl+'</div></div>';
  }).join(""):'<tr>'+emptyState("🧩","暂无配置项")+'</tr>';
  box.querySelectorAll(".st-btn").forEach(bindStepper);
}
function bindStepper(btn){
  var inp=btn.parentNode.querySelector("input");
  if(!inp)return;
  var t=null,r=null;
  function stop(){clearTimeout(t);clearInterval(r);t=r=null;
    document.removeEventListener("mouseup",stop);
    document.removeEventListener("mouseleave",stop)}
  function bump(){
    var v=parseFloat(inp.value);if(isNaN(v))v=0;
    var fine=(inp.step&&inp.step!=="any")
      ?(parseFloat(inp.step)||1)
      :(inp.dataset.tp==="float"?0.1:1);
    var min=(inp.min!==""&&inp.min!=null)?parseFloat(inp.min):0;
    v=Math.max(min,Math.round((v+parseFloat(btn.dataset.step)*fine)*10000)/10000);
    inp.value=v;
    inp.dispatchEvent(new Event("input",{bubbles:true}));
    inp.classList.remove("st-flash");void inp.offsetWidth;inp.classList.add("st-flash");
  }
  btn.addEventListener("mousedown",function(e){
    e.preventDefault();bump();
    document.addEventListener("mouseup",stop);
    t=setTimeout(function(){r=setInterval(bump,55)},400);
  });
  btn.addEventListener("click",function(e){e.preventDefault()});
  btn.addEventListener("blur",stop);
}
async function saveCfg(btn){
  if(btn){btn.disabled=true;btn.textContent="保存中…"}
  var values={};
  document.querySelectorAll("#cfgForm .cfg-in").forEach(function(el){
    var k=el.dataset.k,tp=el.dataset.tp||"string";
    if(el.type==="checkbox"){values[k]=el.checked;return}
    if(cfgHidden.indexOf(k)>=0&&el.value==="")return;
    values[k]=el.value;
  });
  try{
    var r=await jpost("/api/admin/config/save",{values:values});
    toast(r.persisted===false?"已应用但未能持久化":"已保存 "+r.applied+" 项配置","ok");
    loadCfg();
  }catch(e){toast("保存失败："+e.message,"error")}
  finally{if(btn){btn.disabled=false;btn.textContent="💾 保存配置"}}
}

/* ===== 公司管理 ===== */
var companyData=[],coFilter="";
async function loadCompanies(){
  try{
    var r=await jget("/api/admin/companies");
    companyData=(r.companies||[]).slice().sort(function(a,b){return a.id-b.id});
    renderCompanies();
    renderCats();
  }catch(e){console.warn(e)}
}
function coInput(c,f,kind){
  var v=c[f]==null?"":c[f];
  if(kind==="pct")v=(Number(v)*100).toFixed(1);
  return '<input type="text" class="co-edit" data-id="'+c.id+'" data-f="'+f+'"'
    +(kind?' data-k="'+kind+'"':'')
    +' value="'+esc(String(v))+'" placeholder="-">';
}
function renderCompanies(){
  var b=document.getElementById("companyBody");if(!b)return;
  var kw=coFilter.toLowerCase();
  var list=companyData.filter(function(c){
    return !kw||String(c.name).toLowerCase().indexOf(kw)>=0||String(c.tag||"").toLowerCase().indexOf(kw)>=0});
  var cnt=document.getElementById("coCount");
  if(cnt)cnt.textContent="共 "+companyData.length+" 家 · 显示 "+list.length+" 家";
  b.innerHTML=list.length?list.map(function(c){
    return '<tr>'
      +'<td class="co-id">#'+String(c.id).padStart(3,"0")+'</td>'
      +'<td style="min-width:150px">'+coInput(c,"name")+'</td>'
      +'<td style="min-width:76px">'+coInput(c,"tag")+'</td>'
      +'<td style="min-width:86px">'+coInput(c,"salary","num")+'</td>'
      +'<td style="min-width:64px">'+coInput(c,"intensity","num")+'</td>'
      +'<td style="min-width:70px">'+coInput(c,"min_exp","num")+'</td>'
      +'<td style="min-width:80px">'+coInput(c,"risk","pct")+'</td>'
      +'<td style="min-width:220px">'+coInput(c,"desc")+'</td>'
      +'<td style="text-align:right;white-space:nowrap">'
      +'<button class="btn btn-red" style="padding:4px 12px;min-height:32px" onclick="coDel('+c.id+')">删除</button></td>'
      +'</tr>';
  }).join(""):'<tr><td colspan="9">'+emptyState("🏢",kw?"没有匹配的公司":"暂无公司数据")+'</td></tr>';
}
document.addEventListener("DOMContentLoaded",function(){
  var body=document.getElementById("companyBody");
  if(body)body.addEventListener("input",function(e){
    var t=e.target;if(!t.classList||!t.classList.contains("co-edit"))return;
    var id=parseInt(t.dataset.id,10),f=t.dataset.f,k=t.dataset.k;
    var c=companyData.find(function(x){return x.id===id});if(!c)return;
    if(k==="num"){var n=parseFloat(t.value);c[f]=isNaN(n)?0:n}
    else if(k==="pct"){var p=parseFloat(t.value);c.risk=isNaN(p)?0:p/100}
    else c[f]=t.value;
  });
  var search=document.getElementById("coSearch");
  if(search)search.addEventListener("input",function(){coFilter=search.value.trim();renderCompanies()});
  var tb=document.getElementById("txBody");
  if(tb){
    tb.addEventListener("input",function(e){
      var t=e.target;if(!t.classList)return;
      if(t.classList.contains("ta1")&&t.dataset.arr!==undefined&&t.dataset.arr!==""){
        var lines=t.value.split("\n");
        txSetP(txData,t.dataset.arr,lines);txDirty=true;
      }else if(t.classList.contains("tx-f")&&t.dataset.path){
        var v=t.type==="number"?(parseFloat(t.value)||0):t.value;
        txSetP(txData,t.dataset.path,v);txDirty=true;
      }
    });
    tb.addEventListener("change",function(e){
      var t=e.target;
      if(t.dataset&&t.dataset.chk){txSetP(txData,t.dataset.chk,t.checked);txDirty=true}
    });
  }
  var m=document.getElementById("askMask");
  if(m){
    m.addEventListener("click",function(e){if(e.target===m)closeAsk(false)});
    document.getElementById("askYes").addEventListener("click",function(){closeAsk(true)});
    document.getElementById("askNo").addEventListener("click",function(){closeAsk(false)});
  }
});
function coAdd(){
  var max=companyData.reduce(function(m,c){return Math.max(m,c.id)},0);
  companyData.push({id:max+1,name:"新公司"+(max+1),tag:"综合",salary:3500,
    intensity:5,risk:0.01,min_exp:0,desc:"",perks:[]});
  coFilter="";var s=document.getElementById("coSearch");if(s)s.value="";
  renderCompanies();toast("已添加草稿行，点击「保存全部」生效","warn");
}
async function coDel(id){
  var c=companyData.find(function(x){return x.id===id});
  if(!c)return;
  if(!(await askConfirm("确定删除「"+esc(c.name)+"」？保存后其员工将变为失业状态。", {icon:"🏢",title:"删除公司",yes:"确认删除"})))return;
  companyData=companyData.filter(function(x){return x.id!==id});
  renderCompanies();toast("已移除，点击「保存全部」生效","warn");
}
async function saveCompanies(btn){
  if(btn){btn.disabled=true;btn.textContent="保存中…"}
  try{
    var r=await jpost("/api/admin/companies/save",{companies:companyData});
    toast("保存成功：已按薪资重排 "+(r.count||0)+" 家公司（ID 1..N）","ok");
    loadCompanies();
  }catch(e){toast("保存失败："+e.message,"error")}
  finally{if(btn){btn.disabled=false;btn.textContent="💾 保存全部"}}
}

/* ===== 数据分类（公司 + 文案合并）===== */
var TX_LABELS={work:"💼 上班",news:"📰 早报",life:"🏠 生活",duel:"⚔️ 对线",
  company:"🎲 公司事件",extra:"🧩 扩展Ⅰ",extra2:"🧩 扩展Ⅱ",extra3:"🧩 扩展Ⅲ"};
var KEY_CN={
  checkin_events:"打卡事件",slack_ok:"摸鱼心得",slack_caught:"摸鱼被抓",
  overtime_events:"加班事件",hospital_texts:"住院文案",layoff_texts:"被裁员",
  layoff_safe:"裁员幸存",leave_texts:"请假留言",promote_ok:"晋升成功",
  promote_fail:"晋升失败",resign_texts:"辞职留言",job_offer:"应聘成功",
  job_fail:"应聘失败",hop_ok:"跳槽成功",hop_fail:"跳槽失败",
  weeklyreport_ok:"周报通过",weeklyreport_fail:"周报打回",commute_late:"通勤迟到",
  headlines:"每日早报",
  takeout:"点外卖",canteen:"食堂",feast:"大餐",gym:"健身",
  stall_income:"摆摊收入",stall_fail:"摆摊失败",house_move:"搬家",
  rent_paid:"交房租",rent_failed:"房租逾期",nap_ok:"午休",nap_caught:"午休被抓",
  shopping:"购物",teambuild:"团建事件",house_owned_texts:"已购房",
  actions:"对线招式",win_lines:"获胜台词",lose_lines:"战败台词",
  jinxiu_ok:"进修成功",jinxiu_fail:"进修失败",
  negotiation_ok:"加薪成功",negotiation_fail:"加薪失败",
  yearbonus_ok:"年终奖到手",yearbonus_bad:"年终奖缩水",
  skill_learn_ok:"学技能成功",skill_learn_fail:"学技能失败",
  social_ok:"社交成功",social_fail:"社交失败",gossip_texts:"职场八卦",
  side_hustle_up:"副业升级",annual_leave:"年假文案",
  party_prizes:"年会奖品",career_advice:"职场建议",
  lend_ok:"借出成功",lend_fail:"借出被拒",ot_meal:"加班餐",
  checkup_ok:"体检正常",checkup_bad:"体检异常",
  meeting:"开会",bring_food:"带饭",reply_msg:"回消息",
  meeting_room:"抢会议室",eat_with:"同事拼饭",
  boss_task_ok:"帮领导做事·成",boss_task_fail:"帮领导做事·砸",
  summit:"行业峰会",pet_interact:"宠物互动",
  cert_ok:"考证成功",cert_fail:"考证失败",travel:"旅游"};
var FIELD_CN={text:"文案内容",cash:"现金±",health:"健康±",mind:"精神±",
  exp:"经验±",cost:"花费",amount:"金额",rank:"奖项",type:"类型",
  icon:"图标",title:"标题",usage:"指令格式",desc:"说明",commands:"指令列表"};
var PH_CN={a:"自己（发起者）的昵称",b:"对方（被 @ 的人）的昵称"};
function kcn(k){return KEY_CN[k]||k}
function fcn(f){return FIELD_CN[f]||f}
var curCat="companies";
function ensureCats(){renderCats();return Promise.resolve()}
function renderCats(){
  var box=document.getElementById("catFiles");if(!box)return;
  var html='<button class="tx-file'+(curCat==="companies"?' on':'')
    +'" onclick="switchCat(\'companies\')">🏢 公司<i>'+companyData.length+'</i></button>';
  html+=Object.keys(TX_LABELS).map(function(f){
    return '<button class="tx-file'+(f===curCat?' on':'')
      +'" onclick="switchCat(\''+f+'\')">'+TX_LABELS[f]+'</button>';
  }).join("");
  box.innerHTML=html;
}
function switchCat(cat){
  if(cat===curCat)return;
  var go=function(){
    curCat=cat;
    document.getElementById("coEditor").style.display=cat==="companies"?"":"none";
    document.getElementById("txEditor").style.display=cat==="companies"?"none":"";
    renderCats();
    if(cat==="companies"){loadCompanies()}
    else{txName=cat;loadTxFile()}};
  if(curCat!=="companies"&&txDirty){
    askConfirm("当前文案有未保存修改，切换后将丢失。", {icon:"❓",title:"未保存修改",yes:"放弃并切换",danger:false}).then(go);
    return}
  go();
}

/* ===== 文案编辑（公司管理同款表格行内编辑）===== */
var txName="work",txData={},curKey="",txDirty=false;
function txGetP(o,p){return p.split(".").reduce(function(a,x){return a==null?a:a[x]},o)}
function txSetP(o,p,v){var ps=p.split("."),t=o;
  for(var i=0;i<ps.length-1;i++){
    var kk=ps[i];
    if(t[kk]==null)t[kk]=/^\d+$/.test(ps[i+1])?[]:{};
    t=t[kk]}
  t[ps[ps.length-1]]=v}
function txBlank(v){
  if(typeof v==="string")return"";
  if(typeof v==="number")return 0;
  if(typeof v==="boolean")return false;
  if(Array.isArray(v))return v.map(txBlank);
  if(v&&typeof v==="object"){var o={};Object.keys(v).forEach(function(k){o[k]=txBlank(v[k])});return o}
  return null}
async function loadTxFile(){
  var body=document.getElementById("txBody");
  if(body)body.innerHTML='<tr><td colspan="9"><div class="skeleton"></div></td></tr>';
  try{
    var r=await jget("/api/admin/json/get?name="+encodeURIComponent(txName));
    txData=r.data||{};
    curKey=Object.keys(txData)[0]||"";
    renderTx();
  }catch(e){
    if(body)body.innerHTML='<tr><td colspan="9">'+emptyState("⚠️","加载失败："+esc(e.message)+"（重载插件后重试）")+'</td></tr>';
  }
}
function switchTxKey(k){if(k!==curKey){curKey=k;renderTx()}}
function txUnionFields(items){
  var fs=[];items.forEach(function(it){
    Object.keys(it).forEach(function(f){if(fs.indexOf(f)<0)fs.push(f)})});
  return fs}
function txCell(path,v){
  if(typeof v==="number")
    return '<input type="number" step="any" class="tx-f" data-path="'+path+'" value="'+v+'" title="'+esc(path)+'">';
  if(typeof v==="boolean")
    return '<input type="checkbox" class="sw" data-chk="'+path+'"'+(v?" checked":"")+'>';
  if(typeof v==="string"){
    if(v.length>80||v.indexOf("\n")>=0)
      return '<textarea class="tx-f ta1" data-path="'+path+'" rows="2">'+esc(v)+'</textarea>';
    return '<input type="text" class="tx-f" data-path="'+path+'" value="'+esc(v)+'">';
  }
  if(Array.isArray(v)){
    if(v.every(function(x){return typeof x==="string"}))
      return '<textarea class="tx-f ta1" data-arr="'+path+'" rows="'+Math.max(v.length,1)+'">'+esc(v.join("\n"))+'</textarea>';
    return '<div class="sub-list">'+v.map(function(it,i){
      return '<div class="sub-row">'
        +(it&&typeof it==="object"?Object.keys(it).map(function(f){
            return '<input type="text" class="tx-f" data-path="'+path+"."+i+"."+f+'" value="'+esc(String(it[f]))+'" placeholder="'+fcn(f)+'">';
          }).join(""):"")
        +'<button type="button" class="btn btn-red obj-del" onclick="delSub(\''+path+"."+i+'\')">✕</button></div>';
    }).join("")+'<button type="button" class="btn ghost btn-sm" onclick="addSub(\''+path+'\')">➕ 添加</button></div>';
  }
  if(v&&typeof v==="object")
    return '<div class="sub-list"><div class="sub-row">'+Object.keys(v).map(function(f){
      return '<input type="text" class="tx-f" data-path="'+path+"."+f+'" value="'+esc(String(v[f]))+'" placeholder="'+fcn(f)+'">';
    }).join("")+'</div></div>';
  return '<input type="text" class="tx-f" data-path="'+path+'" value="">';
}
function renderTx(){
  var body=document.getElementById("txBody");if(!body)return;
  var keys=Object.keys(txData);
  var kp=document.getElementById("txKeys");
  if(kp)kp.innerHTML=keys.length?keys.map(function(k){
    return '<button class="tx-file'+(k===curKey?' on':'')
      +'" title="'+esc(k)+'" onclick="switchTxKey(\''+k+'\')">'+esc(kcn(k))
      +'<i>'+(txData[k]||[]).length+'</i></button>';
  }).join(""):'<span class="muted" style="font-size:12px">暂无数据</span>';
  var cnt=document.getElementById("txCount");
  if(cnt)cnt.textContent="共 "+keys.length+" 组 · 当前 "+((txData[curKey]||[]).length)+" 条数据";
  var hd=document.getElementById("txHead");
  if(!keys.length||!(curKey in txData)){
    curKey=keys[0]||"";
    if(hd)hd.innerHTML="<th>#</th>";
    body.innerHTML='<tr><td>'+emptyState("📝","该分类暂无内容")+'</td></tr>';
    return;
  }
  var items=txData[curKey]||[];
  var allStr=items.every(function(x){return typeof x==="string"});
  var ph=document.getElementById("txPh");
  if(ph){
    var phs={};
    items.forEach(function(x){
      if(typeof x==="string")String(x).replace(/\{(\w+)\}/g,function(_,t){phs[t]=1})});
    var pk=Object.keys(phs);
    if(pk.length){
      ph.style.display="";
      ph.innerHTML='💡 本组文案支持占位符：'+pk.map(function(t){
        return '<b>{'+t+'}</b> = '+esc(PH_CN[t]||("变量 "+t))}).join('、')
        +' —— 发送时自动替换成玩家昵称，<b style="color:var(--red)">请勿删除花括号</b>';
    }else ph.style.display="none";
  }
  var allStr=items.every(function(x){return typeof x==="string"});
  var delBtn='<button class="btn btn-red" style="padding:4px 12px;min-height:32px" onclick="delTxRow(IDX)">删除</button>';
  if(allStr&&items.length){
    if(hd)hd.innerHTML='<th style="width:64px">#</th><th>内容（一行一条）</th><th style="text-align:right;width:76px">操作</th>';
    body.innerHTML=items.map(function(s,i){
      return '<tr><td class="co-id">'+String(i+1).padStart(3,"0")+'</td>'
        +'<td><input type="text" class="tx-f" data-path="'+curKey+"."+i+'" value="'+esc(s)+'"></td>'
        +'<td style="text-align:right">'+delBtn.replace("IDX",i)+'</td></tr>';
    }).join("");
    return;
  }
  var fs=txUnionFields(items);
  if(hd)hd.innerHTML='<th style="width:64px">#</th>'
    +fs.map(function(f){return '<th title="'+esc(f)+'">'+esc(fcn(f))+'</th>'}).join("")
    +'<th style="text-align:right;width:76px">操作</th>';
  body.innerHTML=items.length?items.map(function(it,i){
    return '<tr><td class="co-id">'+String(i+1).padStart(3,"0")+'</td>'
      +fs.map(function(f){return '<td>'+txCell(curKey+"."+i+"."+f,it[f])+'</td>'}).join("")
      +'<td style="text-align:right">'+delBtn.replace("IDX",i)+'</td></tr>';
  }).join(""):'<tr><td colspan="9">'+emptyState("📝","空数据，点「➕ 新增数据」")+'</td></tr>';
}
function addTxRow(){
  var arr=txData[curKey]||(txData[curKey]=[]);
  arr.push(txBlank(arr.length?arr[arr.length-1]:""));
  txDirty=true;renderTx();
}
async function delTxRow(i){
  if(!(await askConfirm("确定删除第 "+(i+1)+" 条数据？", {icon:"📝",title:"删除数据",yes:"确认删除"})))return;
  txData[curKey].splice(i,1);txDirty=true;renderTx();
}
async function saveTx(btn){
  if(btn){btn.disabled=true;btn.textContent="保存中…"}
  try{
    var r=await jpost("/api/admin/json/save",{name:txName,data:txData});
    txDirty=false;
    toast("保存成功：已热更新 "+(r.keys||0)+" 组文案","ok");
    loadTxFile();
  }catch(e){toast("保存失败："+e.message,"error")}
  finally{if(btn){btn.disabled=false;btn.textContent="💾 保存全部"}}
}
function addSub(path){
  var a=txGetP(txData,path);
  if(!Array.isArray(a))a=[];
  a.push(txBlank(a.length?a[a.length-1]:""));
  txSetP(txData,path,a);txDirty=true;renderTx();
}
function delSub(path){
  var i=path.lastIndexOf("."),idx=parseInt(path.slice(i+1),10);
  var arr=txGetP(txData,path.slice(0,i));
  if(!Array.isArray(arr)||!(idx in arr))return;
  arr.splice(idx,1);txDirty=true;renderTx();
}

/* ===== 玩家列表分页 ===== */
var plPage=1,plTotal=0;
async function loadPlayerList(page){
  plPage=page||1;
  var gid=document.getElementById("playerGroupSel")?.value||"";
  if(!gid)return;
  try{
    var r=await jget("/api/admin/players?gid="+encodeURIComponent(gid)+"&page="+plPage);
    plTotal=Math.ceil((r.total||0)/20);
    var info=document.getElementById("playerListInfo");
    if(info)info.textContent="共 "+(r.total||0)+" 位玩家";
    var pageInfo=document.getElementById("pageInfo");
    if(pageInfo)pageInfo.textContent="第 "+plPage+" / "+(plTotal||1)+" 页";
    var prev=document.getElementById("prevBtn");
    var next=document.getElementById("nextBtn");
    if(prev)prev.disabled=plPage<=1;
    if(next)next.disabled=plPage>=plTotal;
    var b=document.getElementById("playerListBody");if(!b)return;
    b.innerHTML=(r.players&&r.players.length)?r.players.map(function(p){
      return '<tr><td>'+esc(p.nickname)+'</td><td>'+esc(p.company)+' · '+esc(p.position)+'</td>'
        +'<td>'+p.salary+' 元</td><td>'+p.total+' 元</td>'
        +'<td>'+p.health+'</td><td>'+p.mind+'</td></tr>';
    }).join(""):'<tr><td colspan="6" class="empty-state">无数据</td></tr>';
  }catch(e){}
}
function nextPage(){if(plPage<plTotal)loadPlayerList(plPage+1)}
function prevPage(){if(plPage>1)loadPlayerList(plPage-1)}

loadAll();

/* ===== 自定义下拉组件 ===== */
function initCustomSelects(){
  document.querySelectorAll("select").forEach(function(sel){
    if(sel.closest(".sel-wrap"))return;
    var opts=Array.from(sel.options).map(function(o){
      return{value:o.value,text:o.textContent,selected:o.selected}});
    var wrap=document.createElement("div");
    wrap.className="sel-wrap";
    var label=opts.find(function(o){return o.selected});
    var labelTxt=label?label.text:(opts[0]?opts[0].text:"请选择");
    wrap.innerHTML='<div class="sel-trigger" tabindex="0" role="combobox">'
      +'<span class="sel-label">'+esc(labelTxt)+'</span>'
      +'<span class="sel-arrow"></span></div>'
      +'<div class="sel-list">'+opts.map(function(o){
        return '<div class="sel-opt'+(o.selected?' sel':'')+'" data-v="'+esc(o.value)+'">'
          +esc(o.text)+'</div>';
      }).join("")+'</div>';
    sel.style.display="none";
    sel.parentNode.insertBefore(wrap,sel);
    wrap.appendChild(sel);
    var trigger=wrap.querySelector(".sel-trigger");
    var list=wrap.querySelector(".sel-list");
    trigger.addEventListener("click",function(e){
      e.stopPropagation();
      closeAllDropdowns(wrap);
      wrap.classList.toggle("open");
    });
    list.querySelectorAll(".sel-opt").forEach(function(opt){
      opt.addEventListener("click",function(e){
        e.stopPropagation();
        sel.value=opt.dataset.v;
        sel.dispatchEvent(new Event("change",{bubbles:true}));
        list.querySelectorAll(".sel-opt").forEach(function(o){o.classList.remove("sel")});
        opt.classList.add("sel");
        trigger.querySelector(".sel-label").textContent=opt.textContent;
        closeAllDropdowns();
      });
    });
  });
  document.addEventListener("click",function(){closeAllDropdowns()});
}
function closeAllDropdowns(except){
  document.querySelectorAll(".sel-wrap.open").forEach(function(w){
    if(w!==except)w.classList.remove("open");
  });
}
