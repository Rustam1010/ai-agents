// Runs inside the isolated Career Hub panel, never in the chat document.
let hydrated=false,workspaceKey="personal",revision=0,committed="",pendingCalls=new Map(),requestSerial=0,persistQueue=Promise.resolve(),saveFailure="",importing=false,serverMutation=false;
state.selections={};state.prepJobId="";state.prepStoryId="";
function hostCall(method,input){
 const id="career-"+(++requestSerial);
 return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{pendingCalls.delete(id);reject(new Error("BB did not respond. Keep this panel open and retry."))},45000);
  pendingCalls.set(id,{resolve,reject,timer});parent.postMessage({channel:"career-hub",type:"request",id,method,input},"*");
 });
}
function documentValue(){
 if(state.target)state.selections[state.target]=Array.from(state.selected);
 return {schemaVersion:1,profile,stories,targets,sources:state.sources,jobs:state.jobs,versions:state.versions,caseLinks:state.caseLinks,cvWording:state.cvWording,savedNotes:state.savedNotes,selections:state.selections,cvTemplate:state.cvTemplate||null};
}
function saveStatus(text,failed=false){
 const el=document.getElementById("save-status");if(el){el.textContent=text;el.style.color=failed?"var(--warning-text,#a76a24)":""}
}
async function persistNow(){
 if(!hydrated)return;
 const value=JSON.stringify(documentValue());if(value===committed)return;
 saveStatus("Saving…");
 const run=persistQueue.catch(()=>{}).then(async()=>{
  if(value===committed)return;
  const result=await hostCall("save",{key:workspaceKey,revision,document:JSON.parse(value)});
  revision=result.revision;committed=value;saveFailure="";saveStatus(workspaceKey==="demo"?"Demo workspace · saved":"Saved in BB");
 });
 persistQueue=run;
 try{await run}catch(error){saveFailure=String(error.message||error);saveStatus("Unsaved changes · "+saveFailure,true);throw error}
}
function hydrate(result,key,keepView=false){
 const previous={view:state.view,tab:state.experienceTab,target:state.target};
 workspaceKey=key;revision=result.revision;const doc=result.document;
 Object.assign(profile,doc.profile);stories.splice(0,stories.length,...doc.stories);
 Object.keys(targets).forEach(k=>delete targets[k]);Object.assign(targets,doc.targets);
 for(const key of ["jobs","sources","versions","caseLinks","cvWording","savedNotes","selections"])state[key]=doc[key];
 state.cvTemplate=doc.cvTemplate||null;
 state.target=Object.keys(targets)[0]||"";state.selected=new Set(state.selections[state.target]||[]);
 state.prepJobId=state.jobs[0]?.id||"";state.prepStoryId=stories.find(s=>s.approved)?.id||"";
 if(keepView&&targets[previous.target]){state.target=previous.target;state.selected=new Set(state.selections[state.target]||[])}
 hydrated=true;committed=JSON.stringify(documentValue());state.view=keepView?previous.view:"stories";state.experienceTab=keepView?previous.tab:"master";render();
 $("#workspace-mode").textContent=key==="demo"?"Use personal workspace":"Open demo";
 saveStatus(key==="demo"?"Demo workspace · separate from your personal data":"Saved in BB · personal workspace");
}
window.addEventListener("message",e=>{
 if(e.source!==parent||e.data?.channel!=="career-hub")return;const message=e.data;
 if(message.type==="response"){const call=pendingCalls.get(message.id);if(!call)return;clearTimeout(call.timer);pendingCalls.delete(message.id);message.error?call.reject(new Error(message.error)):call.resolve(message.result)}
 if(message.type==="init")hydrate(message.result,message.key);
 if(message.type==="external-update"&&message.revision>revision)void refreshFromHost();
 if(message.type==="refresh")void refreshFromHost();
 if(message.type==="flush-request")void flushForChat(message.id);
 if(message.type==="theme"){for(const [key,value]of Object.entries(message.variables))document.documentElement.style.setProperty(key,value);document.documentElement.style.colorScheme=message.dark?"dark":"light"}
});
window.addEventListener("beforeunload",e=>{if(importing||(hydrated&&JSON.stringify(documentValue())!==committed)){e.preventDefault();e.returnValue=""}});
async function flushForChat(id){try{if(importing)throw new Error("Wait for the current file import to finish.");if($("#modal").open)throw new Error("Save or close the open dialog before starting a conversation.");await persistNow();parent.postMessage({channel:"career-hub",type:"flush-result",id},"*")}catch(error){parent.postMessage({channel:"career-hub",type:"flush-result",id,error:String(error.message||error)},"*")}}
async function refreshFromHost(){
 if(!hydrated||importing||serverMutation)return;
 if($("#modal").open||JSON.stringify(documentValue())!==committed){saveStatus("Assistant or another window updated your data · close your edits, then reload",true);return}
 const requestedKey=workspaceKey;
 try{const result=await hostCall("get",{key:requestedKey});if(requestedKey===workspaceKey&&!importing&&!serverMutation&&!$("#modal").open&&JSON.stringify(documentValue())===committed)hydrate(result,requestedKey,true)}catch(error){saveStatus(String(error.message||error),true)}
}
function notifyView(){parent.postMessage({channel:"career-hub",type:"workspace-view",key:workspaceKey,view:state.view,target:state.target||""},"*")}
const baseRender=render;
render=function(){baseRender();const name=document.querySelector(".master-header h2");if(name&&!profile.name)name.textContent="Your profile";document.querySelectorAll(".requirements-fold .requirement").forEach((element,index)=>element.insertAdjacentHTML("beforeend",btn("Link evidence","edit-evidence","tiny mt",'data-id="'+index+'"')));document.querySelectorAll(".version [data-action=open-version]").forEach(button=>button.parentElement.insertAdjacentHTML("beforeend",btn("PDF","export-cv","tiny",'data-id="'+button.dataset.id+'"')));const sources=document.querySelector("#cv-dropzone");if(sources)sources.insertAdjacentHTML("beforebegin",'<div class="row mb">'+btn("Ask assistant to merge sources","ask-agent")+'</div>');notifyView()};
function prepJob(){return state.jobs.find(job=>job.id===state.prepJobId)||state.jobs[0]}
function prepSourceName(){const job=prepJob();return job?"Interview prep · "+job.company+" · "+job.role:"Interview prep · personal case"}
const practiceQuestions=[
 "Which achievement best demonstrates your fit for this role?",
 "What was your personal contribution, and how was the result measured?",
 "What trade-offs did you make, and what would you do differently?"
];
renderPrep=function(){
 const job=prepJob(),s=stories.find(story=>story.id===state.prepStoryId&&story.approved)||stories.find(story=>story.approved);
 const choices=state.jobs.map(j=>'<option value="'+j.id+'" '+(job?.id===j.id?"selected":"")+'>'+esc(j.company+" · "+j.role)+'</option>').join("");
 return heading("Interview prep",job?esc(job.company+" · "+job.role):"Build and refine your interview cases.",btn(icon("plus")+" Add interview case","new-case"))+
 (choices?'<label class="field mb">Application<select id="prep-job-select">'+choices+'</select></label>':"")+
 '<section class="feature">'+chip("Practice question","green")+'<h2 style="font-size:21px">'+practiceQuestions[state.prepQuestion%practiceQuestions.length]+'</h2>'+btn("Next question","next-question")+'</section>'+
 '<div class="two mt"><section class="surface"><h3>A story for your answer</h3>'+
 (s?'<label class="field mt">Experience<select id="prep-story-select">'+stories.filter(story=>story.approved).map(story=>'<option value="'+story.id+'" '+(story.id===s.id?"selected":"")+'>'+esc(story.title)+'</option>').join("")+'</select></label>'+[["S","Situation",s.context],["T","Task",s.task],["A","Action",s.action],["R","Result",s.result]].map(([letter,label,text])=>'<div class="star"><span class="letter">'+letter+'</span><div><p class="eyebrow">'+label+'</p><p>'+esc(text)+'</p></div></div>').join("")+btn("Edit case & add to your profile","case-to-experience","mt",'data-id="'+s.id+'"'):'<p class="hint mt">Add a case here or confirm a story in Profile &amp; Experience.</p>')+
 '</section><section class="surface"><h3>My notes</h3><label class="field mt">Interview prep note<textarea id="prep-note">'+esc(state.prepNote)+'</textarea></label>'+btn("Save note","save-prep","mt")+(state.savedNotes.length?'<h3 class="mt">Saved notes</h3>'+state.savedNotes.slice(-10).reverse().map(note=>'<p class="small mt" style="white-space:pre-wrap">'+esc(note)+'</p>').join(""):"")+'</section></div>';
};
const baseBuilder=renderBuilder;
renderBuilder=function(){
 if(!state.jobs.length)return heading("CV Builder","Start with a reference CV or paste a job to tailor your experience.")+renderReferenceTemplate()+'<div class="surface mt">'+btn("Add job","new-job","primary")+'</div>';
 if(!targets[state.target])state.target=state.jobs[0].id;
 const body=baseBuilder().replace('<div class="toolbar resume-tools">',renderReferenceTemplate()+'<div class="toolbar resume-tools mt">');
 return body.replace('<div class="resume-layout mt">','<div class="row wrap gap6 mt">'+btn("Edit requirements","edit-requirements")+btn("Ask assistant","ask-agent","",'data-id="'+state.target+'"')+'</div><div class="resume-layout mt">');
};
const baseReviewSource=reviewSource;
reviewSource=function(source){
 if(source.fileId&&!source.text){
  openModal(source.name,'<p class="small">'+esc(source.status)+'</p><p class="hint mt">'+esc(source.note||"No extracted text is available. Upload an OCR or text copy to review the facts.")+'</p>'+btn("Download original","download-source","mt",'data-id="'+source.fileId+'"'));return;
 }
 if(source.proposal){
  openModal("Review proposal · "+source.name,'<p class="hint mb">An agent suggested these changes. Compare them with the source, then review the fields before saving.</p><pre class="proposal-json">'+esc(JSON.stringify(source.proposal.payload,null,2))+'</pre>'+btn("Review suggested fields","review-proposal","primary mt",'data-id="'+source.id+'"'));return;
 }
 baseReviewSource(source);
 if(source.fileId)$("#modal").insertAdjacentHTML("beforeend",'<div class="mt">'+btn("Download original","download-source","",'data-id="'+source.fileId+'"')+'</div>');
};
function setRequirementLines(must,nice){
 const old=target().requirements||[];
 target().requirements=[...[...must.split("\n")].filter(line=>line.trim()).map(line=>({title:line.trim(),quote:line.trim(),story:null,level:"Must-have"})),...[...nice.split("\n")].filter(line=>line.trim()).map(line=>({title:line.trim(),quote:line.trim(),story:null,level:"Nice-to-have"}))].map(row=>({...row,...old.find(prev=>prev.quote===row.quote)}));
}
function openRequirements(payload,sourceId){
 const req=target().requirements||[],must=payload?.mustHave||req.filter(r=>r.level==="Must-have").map(r=>r.quote),nice=payload?.niceToHave||req.filter(r=>r.level==="Nice-to-have").map(r=>r.quote);
 openModal("Job requirements · "+target().company,'<form id="requirements-form" data-source="'+esc(sourceId||"")+'">'+textField("Must-have · one requirement per line","must",must.join("\n"))+textField("Nice-to-have · one requirement per line","nice",nice.join("\n"))+'<button class="btn primary" type="submit">Save requirements</button></form>');
}
function download(name,bytes,type){const url=URL.createObjectURL(new Blob([bytes],{type})),a=document.createElement("a");a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000)}
function encode64(bytes){let value="";for(let i=0;i<bytes.length;i+=32768)value+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(value)}
importCVs=async function(files){
 if(importing){toast("Wait for the current import to finish.");return}
 importing=true;
 try{
 let added=0;
 for(const file of Array.from(files).slice(0,10)){
  try{
   saveStatus("Importing "+file.name+"…");
   const {uploadId}=await hostCall("import_start",{key:workspaceKey,name:file.name,size:file.size});
   const bytes=new Uint8Array(await file.arrayBuffer());
   for(let start=0,index=0;start<bytes.length;start+=262144,index++)await hostCall("import_part",{uploadId,index,data:encode64(bytes.subarray(start,start+262144))});
   const source=await hostCall("import_finish",{uploadId});if(!state.sources.some(row=>row.id===source.id)){state.sources.push(source);added++}
  }catch(error){toast(file.name+": "+String(error.message||error))}
 }
 state.view="stories";state.experienceTab="sources";await persistNow();render();toast(added+" source files added. Review their information before merging.");
 }finally{importing=false}
};
document.addEventListener("click",async e=>{
 const button=e.target.closest("[data-action]");if(!button)return;const action=button.dataset.action,id=button.dataset.id;
 const handled=["workspace-mode","export-data","reload-data","ask-agent","edit-requirements","review-proposal","download-source","edit-evidence","export-cv"];
 if(!handled.includes(action))return;e.stopImmediatePropagation();
 try{
  if(action==="workspace-mode"){if(importing)throw new Error("Wait for the current import to finish before switching workspaces.");await persistNow();const key=workspaceKey==="personal"?"demo":"personal";const result=await hostCall("get",{key});const seed=key==="demo"&&result.revision===0&&!result.document.jobs.length;if(seed)result.document=JSON.parse(JSON.stringify(DEMO_DOCUMENT));hydrate(result,key);if(seed){committed="";await persistNow()}return}
  if(action==="reload-data"){if(JSON.stringify(documentValue())!==committed&&!confirm("Reloading discards unsaved edits. Export your profile first if you need to keep them."))return;hydrate(await hostCall("get",{key:workspaceKey}),workspaceKey);return}
  if(action==="export-data"){download("career-hub-"+workspaceKey+".json",JSON.stringify({exportedAt:new Date().toISOString(),document:documentValue()},null,2),"application/json");return}
  if(action==="export-cv"){saveStatus("Preparing PDF…");const result=await hostCall("cv_pdf",{key:workspaceKey,versionId:id});download(result.name,Uint8Array.from(atob(result.data),c=>c.charCodeAt(0)),"application/pdf");saveStatus("PDF ready · saved version preserved");return}
  if(action==="ask-agent"){parent.postMessage({channel:"career-hub",type:"open-chat"},"*");return}
  if(action==="edit-requirements"){openRequirements();return}
  if(action==="edit-evidence"){const index=Number(id),r=target().requirements[index];openModal("Link experience",'<form id="evidence-form" data-index="'+index+'"><p class="small">'+esc(r.quote)+'</p><label class="field">Supporting story<select name="story"><option value="">No confirmed evidence</option>'+stories.filter(s=>s.approved).map(s=>'<option value="'+s.id+'" '+(r.story===s.id?"selected":"")+'>'+esc(s.title)+'</option>').join("")+'</select></label><label class="row small"><input name="partial" type="checkbox" '+(r.partial?"checked":"")+'> Evidence is partial</label><button class="btn primary" type="submit">Save evidence link</button></form>');return}
  if(action==="review-proposal"){
   const source=state.sources.find(s=>s.id===id),proposal=source.proposal,p=proposal.payload;
   if(proposal.kind==="profile"){openMasterEditor();const form=$("#profile-form");form.dataset.proposalSource=source.id;for(const [key,value]of Object.entries(p)){const input=form.elements.namedItem(key);if(input&&typeof value==="string")input.value=value}}
   if(proposal.kind==="story"){const {id,approved,...candidate}=p;openStoryForm({...candidate,approved:false,source:source.name,sourceIds:[source.id]},{sourceId:source.id})}
   if(proposal.kind==="requirements"){state.target=proposal.jobId;openRequirements(p,source.id)}
   return;
  }
  if(action==="download-source"){
   let offset=0,total=1,name="source",parts=[];
   while(offset<total){const result=await hostCall("file_part",{id,offset});name=result.name;total=result.total;const bytes=Uint8Array.from(atob(result.data),c=>c.charCodeAt(0));if(!bytes.length)throw new Error("Incomplete file download.");parts.push(bytes);offset+=bytes.length}
   download(name,new Blob(parts),"application/octet-stream");return;
  }
 }catch(error){toast(String(error.message||error))}
},true);
document.addEventListener("submit",async e=>{
 if(!["requirements-form","evidence-form"].includes(e.target.id))return;e.preventDefault();e.stopImmediatePropagation();
 const form=e.target,data=new FormData(form);
 if(form.id==="requirements-form"){setRequirementLines(String(data.get("must")||""),String(data.get("nice")||""));if(form.dataset.source){const source=state.sources.find(s=>s.id===form.dataset.source);delete source.proposal;source.status="Reviewed"}}
 if(form.id==="evidence-form"){const r=target().requirements[Number(form.dataset.index)];r.story=String(data.get("story")||"")||null;r.partial=data.has("partial");r.note=r.partial?"Partial evidence; review the source story.":""}
 try{await persistNow();$("#modal").close();render()}catch(error){toast(String(error.message||error))}
},true);
document.addEventListener("change",e=>{
 if(e.target.id==="prep-job-select")state.prepJobId=e.target.value;
 if(e.target.id==="prep-story-select")state.prepStoryId=e.target.value;
 if(["prep-job-select","prep-story-select"].includes(e.target.id))render();
},true);
parent.postMessage({channel:"career-hub",type:"ready"},"*");

const SECTION_NAMES={profile:"Profile",experience:"Experience",skills:"Skills",education:"Education",certifications:"Certifications",languages:"Languages",additional:"Additional details"};
function renderReferenceTemplate(){
 const reference=state.cvTemplate;
 return '<section class="surface soft dropzone mb" id="template-dropzone" aria-label="Reference CV template"><div class="row spread wrap"><div><p class="sectionlabel">Reference CV</p><h3>'+esc(reference?reference.name:"Drop a CV you want to use as a template")+'</h3><p class="hint mt">Use its section order and choose the spacing. Your own profile supplies the facts.</p></div>'+btn(reference?"Replace reference":"Choose a CV","upload-template")+'</div><input class="visually-hidden" id="template-file" aria-label="Upload reference CV template" type="file" accept=".pdf,.docx,.txt,.md">'+(reference?'<div class="row wrap gap6 mt">'+reference.sectionOrder.map(section=>chip(SECTION_NAMES[section])).join("")+chip(reference.style==="compact"?"Compact spacing":"Classic spacing")+'</div><div class="row wrap gap6 mt">'+btn("Layout preferences","template-preferences","tiny")+btn("Download reference","download-source","tiny",'data-id="'+reference.sourceId+'"')+'</div>':"")+'<p class="hint mt">PDF or DOCX preferred · one-column, text-based output for ATS readability.</p></section>';
}
async function uploadOriginal(file,purpose){
 const {uploadId}=await hostCall("import_start",{key:workspaceKey,name:file.name,size:file.size,purpose});
 const bytes=new Uint8Array(await file.arrayBuffer());
 for(let start=0,index=0;start<bytes.length;start+=262144,index++)await hostCall("import_part",{uploadId,index,data:encode64(bytes.subarray(start,start+262144))});
 return await hostCall("import_finish",{uploadId});
}
async function importReference(file){
 if(!file)return;if(importing){toast("Wait for the current import to finish.");return}
 importing=true;
 try{
  await persistNow();saveStatus("Importing reference CV…");const source=await uploadOriginal(file,"template");
  if(!state.sources.some(s=>s.id===source.id))state.sources.push(source);
  await persistNow();const result=await hostCall("template_set",{key:workspaceKey,revision,sourceId:source.id});hydrate(result,workspaceKey,true);toast("Reference CV saved. Section order is ready to use.");
 }catch(error){render();saveStatus(String(error.message||error),true);toast(String(error.message||error))}finally{importing=false}
}
function openJobPaste(){
 openModal("Add job",'<p class="hint mb">Paste a vacancy or a message from your chat. Company, role and stated requirements will be picked out for you.</p><form id="job-intake-form"><label class="field">Job text<textarea name="text" aria-label="Paste a job from chat" required minlength="8" maxlength="100000" style="min-height:220px" placeholder="Paste the message here…"></textarea></label><button type="submit" class="btn primary">Add to Jobs</button></form>');
}
const originalHistory=showHistory;
showHistory=function(job){originalHistory(job);$("#modal").insertAdjacentHTML("beforeend",'<div class="mt">'+btn("Edit vacancy details","edit-job-details","tiny",'data-id="'+job.id+'"')+'</div>')};
document.addEventListener("click",e=>{
 const button=e.target.closest("[data-action]");if(!button)return;const action=button.dataset.action;
 if(!["upload-template","template-preferences","edit-job-details"].includes(action))return;e.stopImmediatePropagation();
 if(action==="upload-template"){$("#template-file").click();return}
 if(action==="template-preferences"){
  const t=state.cvTemplate;openModal("Reference layout",'<form id="template-preferences-form"><label class="field">Spacing<select name="style"><option value="classic" '+(t.style==="classic"?"selected":"")+'>Classic · generous spacing</option><option value="compact" '+(t.style==="compact"?"selected":"")+'>Compact · more content per page</option></select></label>'+textField("Section order · one per line","sections",t.sectionOrder.join("\n"))+textField("What do you like about this reference?","notes",t.notes)+'<p class="hint">Available sections: profile, experience, skills, education, certifications, languages, additional. The assistant can help refine the order and wording.</p><button type="submit" class="btn primary">Save preferences</button></form>');return;
 }
 if(action==="edit-job-details"){
  const job=state.jobs.find(job=>job.id===button.dataset.id);openModal("Edit vacancy details",'<form id="job-details-form" data-job="'+job.id+'">'+inputField("Company","company",job.company,true)+inputField("Role","role",job.role,true)+inputField("Location","location",job.location)+textField("Original vacancy text","description",job.description||"")+'<button type="submit" class="btn primary">Save details</button></form>');
 }
},true);
document.addEventListener("submit",async e=>{
 if(!["job-intake-form","template-preferences-form","job-details-form"].includes(e.target.id))return;e.preventDefault();e.stopImmediatePropagation();
 const form=e.target,data=new FormData(form),read=k=>String(data.get(k)||"").trim(),submit=form.querySelector('[type="submit"]');submit.disabled=true;
 try{
  if(form.id==="job-intake-form"){
   await persistNow();serverMutation=true;
   const result=await hostCall("job_create",{key:workspaceKey,revision,text:read("text")});hydrate(result,workspaceKey,true);state.view="jobs";state.jobQuery="";state.target=result.jobId;state.selected=new Set();$("#modal").close();render();toast("Job added from your message.");return;
  }
  if(form.id==="template-preferences-form"){
   const sections=read("sections").split(/\n/).map(x=>x.trim().toLowerCase()).filter(Boolean);
   if(sections.length<2||sections.some(x=>!SECTION_NAMES[x])||new Set(sections).size!==sections.length)throw new Error("Choose at least two different section names from the list.");
   state.cvTemplate={...state.cvTemplate,style:read("style"),sectionOrder:sections,notes:read("notes")};
  }
  if(form.id==="job-details-form"){
   const job=state.jobs.find(job=>job.id===form.dataset.job);Object.assign(job,{company:read("company"),role:read("role"),location:read("location"),description:read("description"),intakeNeedsReview:false});Object.assign(targets[job.id],{company:job.company,role:job.role});const source=state.sources.find(s=>s.id===job.sourceId);if(source){source.text=job.description;source.name=job.company+" · job description"}event(job,"Vacancy details updated.");
  }
  await persistNow();$("#modal").close();render();toast("Saved in BB.");
 }catch(error){toast(String(error.message||error))}finally{serverMutation=false;submit.disabled=false}
},true);
document.addEventListener("change",e=>{if(e.target.id==="template-file")void importReference(e.target.files[0])});
document.addEventListener("dragover",e=>{if(e.target.closest("#template-dropzone"))e.preventDefault()});
document.addEventListener("drop",e=>{if(e.target.closest("#template-dropzone")){e.preventDefault();void importReference(e.dataTransfer.files[0])}});

function cvSections(selection,t){
 const focus=Array.from(new Set(selection.map(s=>s.focus).filter(Boolean))),summary=profile.summary||profile.headline+(focus.length?" with experience in "+focus.join(", ")+".":"");
 const experience=groupsFor(selection).map(([key,items])=>({text:key+"\n"+items.map(s=>"• "+compact(s)).join("\n"),html:'<div class="employment">'+esc(items[0].company)+' · '+esc(items[0].role)+'</div><div class="period">'+esc(items[0].period)+'</div><ul>'+items.map(s=>'<li>'+esc(compact(s))+'<button class="source-link" data-action="source" data-id="'+s.id+'" aria-label="Source for '+esc(s.title)+'">['+(stories.indexOf(s)+1)+']</button></li>').join("")+'</ul>'}));
 const text={profile:summary,experience:experience.map(x=>x.text).join("\n\n"),skills:profile.skills,education:profile.education,certifications:profile.certifications,languages:profile.languages,additional:[profile.additional,...(profile.sections||[]).map(s=>s.title+"\n"+s.body)].filter(Boolean).join("\n\n")};
 const order=state.cvTemplate?.sectionOrder||["profile","experience","skills","education","certifications","languages","additional"];
 return order.filter(section=>text[section]||section==="experience").map(section=>({name:SECTION_NAMES[section],text:text[section],html:section==="experience"?experience.map(x=>x.html).join("")||'<p class="muted">Select confirmed stories to build your CV.</p>':'<p style="white-space:pre-wrap">'+esc(text[section])+'</p>'}));
}
cvText=function(selection=picked(),t=target()){
 const contact=[profile.location,profile.email,profile.linkedin].filter(Boolean).join(" · ");
 return [profile.name.toUpperCase(),"Target role: "+t.role,contact,"",...cvSections(selection,t).map(section=>section.name.toUpperCase()+"\n"+section.text+"\n")].join("\n").trim();
};
renderPaper=function(selection,t){
 return '<article class="paper '+(state.cvTemplate?.style==="compact"?"compact-paper":"")+'" aria-label="CV preview"><div class="resume-name">'+esc(profile.name)+'</div><div class="resume-title">Target role: '+esc(t.role)+'</div><div class="resume-contact">'+esc([profile.location,profile.email,profile.linkedin].filter(Boolean).join(" · "))+'</div>'+cvSections(selection,t).map(section=>'<h3>'+esc(section.name)+'</h3>'+section.html).join("")+'</article>';
};
