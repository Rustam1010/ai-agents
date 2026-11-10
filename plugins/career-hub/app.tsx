import {useCallback,useEffect,useRef,useState} from "react";
import {definePluginApp,ThreadChat,experimental_NewThreadComposer as NewThreadComposer,experimental_PluginIcon as PluginIcon,useBbContext,useRealtime,useRealtimeConnectionState,useRpc,type NewThreadRequest} from "@get-bb/plugin-sdk/app";
import type {rpcContract} from "./contract";
import {frameHtml} from "./frame.generated";
type Panel={key:"personal"|"demo";view:"jobs"|"stories"|"resume"|"prep";target:string};
const LABELS={jobs:"Jobs",stories:"Profile & Experience",resume:"CV Builder",prep:"Interview prep"};
const COLORS=["--background","--foreground","--muted-foreground","--border","--card","--surface-recessed","--surface-raised","--brand","--primary-foreground","--warning-text","--warning","--font-sans","--font-mono","--radius"];
function CareerPage(){
 const rpc=useRpc<typeof rpcContract>(),context=useBbContext(),connection=useRealtimeConnectionState();
 const frame=useRef<HTMLIFrameElement>(null),started=useRef(false),revision=useRef(0),key=useRef("personal"),client=useRef(crypto.randomUUID()),wasConnected=useRef(false);
 const flushes=useRef(new Map<string,{resolve:()=>void;reject:(error:Error)=>void;timer:ReturnType<typeof setTimeout>}>());
 const [error,setError]=useState<string|null>(null),[panel,setPanel]=useState<Panel>({key:"personal",view:"stories",target:""});
 const [chatFocus,setChatFocus]=useState<number>(),[threadId,setThreadId]=useState<string|null>(null),[chatLoading,setChatLoading]=useState(true);
 const post=useCallback((value:unknown)=>frame.current?.contentWindow?.postMessage(value,"*"),[]);
 const theme=useCallback(()=>{
  const style=getComputedStyle(document.documentElement),variables=Object.fromEntries(COLORS.map(k=>[k,style.getPropertyValue(k)]).filter(([,v])=>v.trim()));
  post({channel:"career-hub",type:"theme",variables,dark:document.documentElement.classList.contains("dark")||style.colorScheme==="dark"});
 },[post]);
 const initialize=useCallback(async()=>{
  if(started.current)return;started.current=true;
  try{const result=await rpc.call("get",{key:"personal"});revision.current=result.revision;post({channel:"career-hub",type:"init",key:"personal",result});theme();setError(null)}
  catch(error){started.current=false;setError(error instanceof Error?error.message:String(error))}
 },[rpc,post,theme]);
 useEffect(()=>{
  let live=true;setChatLoading(true);setThreadId(null);
  void rpc.call("chat_get",{key:panel.key}).then(result=>{if(live){setThreadId(result.threadId);setChatLoading(false)}}).catch(error=>{if(live){setError(String(error));setChatLoading(false)}});
  return()=>{live=false};
 },[panel.key,rpc]);
 useEffect(()=>{void rpc.call("chat_context",panel).catch(error=>setError(String(error)))},[panel,rpc]);
 useEffect(()=>{
  const receive=async(event:MessageEvent)=>{
   if(event.source!==frame.current?.contentWindow||event.data?.channel!=="career-hub")return;
   const message=event.data;
   if(message.type==="workspace-view"){
    if(!["personal","demo"].includes(message.key)||!["jobs","stories","resume","prep"].includes(message.view)||typeof message.target!=="string")return;
    const next:Panel={key:message.key,view:message.view,target:message.target.slice(0,180)};
    setPanel(current=>current.key===next.key&&current.view===next.view&&current.target===next.target?current:next);key.current=next.key;return;
   }
   if(message.type==="flush-result"){
    const pending=flushes.current.get(message.id);if(!pending)return;flushes.current.delete(message.id);clearTimeout(pending.timer);message.error?pending.reject(new Error(message.error)):pending.resolve();return;
   }
   if(message.type==="open-chat"){setChatFocus(Date.now());return}
   if(message.type==="ready"){await initialize();return}
   if(message.type!=="request")return;
   try{
    if(!["get","save","import_start","import_part","import_finish","file_part","cv_pdf","job_create","template_set"].includes(message.method))throw new Error("Unknown Career Hub operation.");
    const input=message.method==="save"?{...(message.input as Record<string,unknown>),clientId:client.current}:message.input;
    const call=rpc.call as unknown as (name:string,input:unknown)=>Promise<unknown>,result=await call(message.method,input);
    if(message.method==="get"){key.current=message.input.key;revision.current=(result as {revision:number}).revision}
    if(["save","job_create","template_set"].includes(message.method))revision.current=(result as {revision:number}).revision;
    post({channel:"career-hub",type:"response",id:message.id,result});setError(null);
   }catch(error){const text=error instanceof Error?error.message:String(error);post({channel:"career-hub",type:"response",id:message.id,error:text});setError(text)}
  };
  window.addEventListener("message",receive);
  const observer=new MutationObserver(theme);observer.observe(document.documentElement,{attributes:true,attributeFilter:["class","style"]});
  return()=>{observer.disconnect();window.removeEventListener("message",receive)};
 },[initialize,post,rpc,theme]);
 useEffect(()=>()=>{for(const pending of flushes.current.values()){clearTimeout(pending.timer);pending.reject(new Error("Career Hub closed before the chat was opened."))}flushes.current.clear()},[]);
 useEffect(()=>{if(connection==="connected"){if(wasConnected.current)post({channel:"career-hub",type:"refresh"});wasConnected.current=true}},[connection,post]);
 useRealtime("career-changed",(value:unknown)=>{
  const event=value as {key?:string;revision?:number;clientId?:string};
  if(event.key===key.current&&event.clientId!==client.current&&(event.revision??0)>revision.current)post({channel:"career-hub",type:"external-update",revision:event.revision});
 });
 const startChat=async(request:NewThreadRequest)=>{
  if(panel.view==="jobs")throw new Error("The assistant is available in Profile & Experience, CV Builder and Interview prep.");
  const id=crypto.randomUUID();await new Promise<void>((resolve,reject)=>{const timer=setTimeout(()=>{flushes.current.delete(id);reject(new Error("Save your current edits, then try again."))},12000);flushes.current.set(id,{resolve,reject,timer});post({channel:"career-hub",type:"flush-request",id})});
  try{const result=await rpc.call("chat_start",{...panel,view:panel.view,request:request as unknown as Parameters<typeof rpc.call<"chat_start">>[1]["request"]});setThreadId(result.threadId);setError(null)}catch(error){setError(String(error));throw error}
 };
 return <div style={{height:"100%",minHeight:0,display:"flex",flexDirection:"column",overflow:"hidden"}}>
  {error?<div role="alert" style={{padding:"8px 14px",fontSize:12,color:"var(--warning-text)",borderBottom:"1px solid var(--border)"}}>{error}</div>:null}
  <div style={{flex:"1 1 0",minHeight:0}}><iframe ref={frame} title="Career Hub workspace" srcDoc={frameHtml} onLoad={()=>void initialize()} sandbox="allow-scripts allow-forms allow-downloads allow-modals" style={{width:"100%",height:"100%",border:0}}/></div>
  {panel.view!=="jobs"?<section aria-label="Career Hub assistant" style={{flex:"0 0 auto",height:threadId?"clamp(240px,40%,360px)":"clamp(210px,28%,250px)",minHeight:0,maxHeight:"65%",display:"flex",flexDirection:"column",borderTop:"1px solid var(--border)",background:"var(--background)",overflow:"hidden"}}>
   <div style={{display:"flex",alignItems:"center",flexWrap:"wrap",gap:"4px 10px",width:"100%",padding:"8px 16px",fontSize:12,color:"var(--foreground)",flexShrink:0}}>
    <PluginIcon pluginId="career-hub" icon="Briefcase" className="size-4"/><h2 style={{fontSize:12,fontWeight:600,margin:0}}>Career assistant</h2><span style={{color:"var(--muted-foreground)",flex:1}}>{LABELS[panel.view]} · ask for changes</span>
   </div>
   <div style={{flex:"1 1 0",minHeight:0,overflow:"hidden"}}>
    {chatLoading?<p style={{padding:16,fontSize:12}}>Loading your conversation…</p>:threadId?<ThreadChat key={threadId} threadId={threadId} variant="compact" layout="contained" permissionPolicy="inherit" focusRequest={chatFocus}/>:<NewThreadComposer key={panel.key} defaultProjectId={context.projectId??undefined} initialPrompt="" placeholder={panel.view==="stories"?"Ask to add experience, update your profile, or merge CV sources…":panel.view==="resume"?"Ask to tailor your CV, select stories, or refine your reference layout…":"Practice an answer, develop a case, or save preparation notes…"} onSubmit={startChat} draftKey={"career-hub-"+panel.key} layout="contained" focusRequest={chatFocus}/>}
   </div>
  </section>:null}
 </div>;
}
export default definePluginApp(app=>{app.slots.navPanel({id:"career",title:"Career Hub",icon:"Briefcase",path:"career",component:CareerPage})});
