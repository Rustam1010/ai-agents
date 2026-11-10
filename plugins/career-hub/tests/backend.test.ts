import {test} from "node:test";
import assert from "node:assert/strict";
import {createFakePluginHost,makeThreadResponse,makePluginAgentConfigurationContext} from "@get-bb/plugin-sdk/testing";
import plugin from "../server";

const request={projectId:"project-test",providerId:"test",model:"test-model",reasoningLevel:"medium",permissionMode:"auto",executionInputSources:{},environment:{type:"project-default"},input:[{type:"text",text:"Change my demo profile."}]};
async function setup(){const value=createFakePluginHost({pluginId:"career-hub",agentSkillIds:["career-hub"],sdk:{threads:{spawn:async()=>makeThreadResponse({id:"thread-demo"}),get:async()=>makeThreadResponse({id:"thread-demo"}),getPluginMetadata:async()=>({})}}});plugin(value.bb);return value}
const textResult=(value:unknown)=>JSON.parse(typeof value==="string"?value:(value as {content:{text:string}[]}).content[0].text);

test("embedded assistant is created only on explicit send, keeps workspace identity, and applies idempotent edits",async()=>{
 const {harness}=await setup();try{
  assert.deepEqual(await harness.behavior.callRpc("chat_get",{key:"demo"}),{threadId:null});assert.equal(harness.inspection.sdk.callsTo("threads.spawn").length,0);
  await harness.behavior.callRpc("chat_start",{key:"demo",view:"stories",target:"",request});
  assert.equal(harness.inspection.sdk.callsTo("threads.spawn").length,1);assert.deepEqual(await harness.behavior.callRpc("chat_get",{key:"demo"}),{threadId:"thread-demo"});
  const ctx={threadId:"thread-demo",projectId:"project-test"};
  const input={revision:0,operationId:"edit-1",edits:[{type:"profile",fields:{name:"Demo Example",languages:"English"}},{type:"prep_note",text:"Practice a measured result."}]};
  assert.equal(textResult(await harness.behavior.callAgentTool("career_hub_edit",input,ctx)).revision,1);
  assert.equal(textResult(await harness.behavior.callAgentTool("career_hub_edit",input,ctx)).alreadyApplied,true);
  const demo=await harness.behavior.callRpc("get",{key:"demo"}) as any,personal=await harness.behavior.callRpc("get",{key:"personal"}) as any;
  assert.equal(demo.document.savedNotes.length,1);assert.equal(personal.document.profile.name,"");
  await assert.rejects(harness.behavior.callAgentTool("career_hub_edit",{...input,edits:[{type:"prep_note",text:"Different"}]},ctx),/different changes/);
  await assert.rejects(harness.behavior.callAgentTool("career_hub_edit",{...input,operationId:"edit-2"},ctx),/Conflict/);
  await assert.rejects(harness.behavior.callAgentTool("career_hub_edit",{...input,revision:1,operationId:"outside"},{threadId:"unrelated-thread"}),/Open the Career Hub/);
  await harness.behavior.callRpc("chat_context",{key:"demo",view:"resume",target:""});
  const status=textResult(await harness.behavior.callAgentTool("career_hub_read",{area:"status"},ctx));assert.equal(status.result.activeTab,"resume");assert.equal(status.result.workspace,"demo");
  const config=await harness.behavior.resolveAgentConfiguration(makePluginAgentConfigurationContext({pluginMetadata:{purpose:"career-assistant",workspace:"demo"}}));assert.ok(JSON.stringify(config).includes("career_hub_edit"));
 }finally{await harness.lifecycle.dispose()}
});
test("pasted intake and reference template preserve facts and immutable versions across reload",async()=>{
 const {harness}=await setup();let active=harness;try{
  const job=await harness.behavior.callRpc("job_create",{key:"demo",revision:0,text:"Company: Example\nRole: Head of Data\nMust-have:\nAnalytics leadership"}) as any;
  assert.equal(job.document.jobs[0].company,"Example");assert.equal(job.document.targets[job.jobId].requirements[0].quote,"Analytics leadership");
  const bytes=Buffer.from("Someone else's CV\nSKILLS\nUnrelated skill\nEXPERIENCE\nEDUCATION\nPROFILE");
  const upload=await harness.behavior.callRpc("import_start",{key:"demo",name:"reference.txt",size:bytes.length,purpose:"template"}) as any;
  await harness.behavior.callRpc("import_part",{uploadId:upload.uploadId,index:0,data:bytes.toString("base64")});
  const source=await harness.behavior.callRpc("import_finish",{uploadId:upload.uploadId}) as any;assert.equal(source.type,"template");assert.equal(source.hidden,true);
  const template=await harness.behavior.callRpc("template_set",{key:"demo",revision:1,sourceId:source.id}) as any;
  assert.deepEqual(template.document.cvTemplate.sectionOrder,["skills","experience","education","profile"]);assert.equal(template.document.profile.name,"");
  const duplicate=await harness.behavior.callRpc("template_set",{key:"demo",revision:2,sourceId:source.id}) as any;assert.equal(duplicate.revision,2);assert.deepEqual(duplicate.document.cvTemplate,template.document.cvTemplate);
  template.document.versions.push({id:"v1",number:1,target:job.jobId,label:"v1",text:"Original CV",stories:[],sent:false,layout:template.document.cvTemplate});
  await harness.behavior.callRpc("save",{key:"demo",revision:2,document:template.document});
  active=(await harness.lifecycle.reload(plugin)).harness;
  const restored=await active.behavior.callRpc("get",{key:"demo"}) as any;assert.equal(restored.document.cvTemplate.sourceId,source.id);assert.equal(restored.document.versions[0].text,"Original CV");
  restored.document.versions[0].layout.style="compact";
  await assert.rejects(active.behavior.callRpc("save",{key:"demo",revision:3,document:restored.document}),/immutable/);
 }finally{await active.lifecycle.dispose()}
});
