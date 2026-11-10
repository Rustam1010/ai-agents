import {documentSchema,type CareerDocument} from "./contract";
export function emptyDocument():CareerDocument{
 return {schemaVersion:1,profile:{name:"",headline:"",location:"",email:"",linkedin:"",meridianPeriod:"",
  summary:"",skills:"",education:"",certifications:"",languages:"",additional:"",sections:[]},
  stories:[],sources:[],jobs:[],targets:{},versions:[],caseLinks:{},cvWording:{},savedNotes:[],selections:{},cvTemplate:null};
}
export function validateDocument(value:unknown):CareerDocument{
 const doc=documentSchema.parse(value);
 if(Buffer.byteLength(JSON.stringify(doc))>8*1024*1024)throw new Error("Workspace exceeds the 8 MB text limit. Export a profile backup first.");
 for(const field of ["stories","sources","jobs","versions"] as const){
  const ids=doc[field].map(row=>row.id);if(new Set(ids).size!==ids.length)throw new Error("Duplicate "+field+" ids.");
 }
 const jobIds=new Set(doc.jobs.map(job=>job.id)),storyIds=new Set(doc.stories.map(story=>story.id)),sourceIds=new Set(doc.sources.map(source=>source.id));
 if(doc.cvTemplate){if(!doc.sources.some(s=>s.id===doc.cvTemplate!.sourceId&&s.type==="template"))throw new Error("CV template references an unknown template source.");if(new Set(doc.cvTemplate.sectionOrder).size!==doc.cvTemplate.sectionOrder.length)throw new Error("CV template sections must be unique.");}
 for(const story of doc.stories)if(story.sourceIds.some(id=>!sourceIds.has(id)))throw new Error("Experience references an unknown source.");
 for(const [jobId,target]of Object.entries(doc.targets)){
  if(!jobIds.has(jobId)||typeof target.company!=="string"||typeof target.role!=="string"||!Array.isArray(target.requirements))throw new Error("Invalid target job.");
  for(const requirement of target.requirements){if(!requirement||typeof requirement!=="object"||Array.isArray(requirement))throw new Error("Invalid requirement.");const r=requirement as Record<string,unknown>;if(typeof r.title!=="string"||typeof r.quote!=="string"||!["Must-have","Nice-to-have"].includes(String(r.level)))throw new Error("Invalid requirement.");if(r.story!=null&&!storyIds.has(String(r.story)))throw new Error("Requirement references an unknown story.")}
 }
 for(const version of doc.versions)if(!jobIds.has(version.target))throw new Error("CV version references an unknown job.");
 return doc;
}
export function validateSavedVersions(before:CareerDocument,after:CareerDocument){
 for(const old of before.versions){
  const next=after.versions.find(row=>row.id===old.id);
  if(!next)throw new Error("Saved CV versions cannot be deleted by an ordinary save.");
  const {sent:oldSent,...oldContent}=old,{sent:nextSent,...nextContent}=next;
  if(JSON.stringify(oldContent)!==JSON.stringify(nextContent)||(oldSent&&!nextSent))
   throw new Error("A saved CV is immutable. Create a new version instead.");
 }
 for(const old of before.jobs){
  const next=after.jobs.find(job=>job.id===old.id);if(!next)throw new Error("Archive a job instead of deleting its application history.");
  if(old.events.some((event,index)=>JSON.stringify(event)!==JSON.stringify(next.events[index])))throw new Error("Application history is append-only. Add a correction event instead.");
 }
}
