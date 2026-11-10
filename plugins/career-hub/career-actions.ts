import {randomUUID} from "node:crypto";
import {z} from "zod";
import {editSchema,templateSchema,type CareerDocument} from "./contract";
import {validateDocument,validateSavedVersions} from "./model";

const clean=(value:string)=>value.replace(/^[\s>#*•–-]+/u,"").replace(/[*`]+/g,"").trim();
export function parseJobPaste(raw:string){
 const lines=raw.split(/\r?\n/).map(clean).filter(Boolean),fields:Record<string,string>={};
 const labels:Record<string,RegExp>={company:/^(?:company|employer|компания|работодатель)\s*[:：]\s*(.+)$/iu,role:/^(?:job title|title|role|position|должность|позиция|вакансия)\s*[:：]\s*(.+)$/iu,location:/^(?:location|workplace|локация|место работы|местоположение)\s*[:：]\s*(.+)$/iu};
 for(const line of lines)for(const [field,re]of Object.entries(labels)){const m=line.match(re);if(m&&!fields[field])fields[field]=m[1].trim().slice(0,field==="location"?1000:500)}
 const roleLike=/(?:engineer|analyst|analytics|scientist|designer|manager|director|head|lead|developer|product|marketing|sales|researcher|инженер|аналитик|разработчик|руководитель|директор|дизайнер|менеджер)/iu;
 const candidates=lines.filter(line=>line.length<160&&!/^https?:|^(?:here\b|sure\b|вот\b|конечно\b)|[:：]/iu.test(line));
 if(!fields.role||!fields.company){
  for(const line of candidates.slice(0,5)){
   const at=line.match(/^(.{2,100}?)\s+(?:at|@|в компании)\s+(.{2,100})$/iu);
   if(at&&roleLike.test(at[1])){fields.role??=at[1];fields.company??=at[2];break}
   const parts=line.split(/\s+[—–|]\s+|\s+-\s+/u);
   if(parts.length===2){if(roleLike.test(parts[0])){fields.role??=parts[0];fields.company??=parts[1];break}if(roleLike.test(parts[1])){fields.company??=parts[0];fields.role??=parts[1];break}}
  }
 }
 if(!fields.role){const index=candidates.findIndex(line=>roleLike.test(line));if(index>=0){fields.role=candidates[index];if(index>0&&!roleLike.test(candidates[index-1]))fields.company??=candidates[index-1]}}
 const needsReview=!fields.company||!fields.role;
 const url=raw.match(/https?:\/\/[^\s<>\]\)]+/iu)?.[0]??"";
 if(!fields.location){const place=lines.find(line=>line.length<130&&/\b(?:remote|hybrid|on-site)\b|удалён|удален|гибрид/iu.test(line));if(place)fields.location=place}
 const requirements:{title:string;quote:string;story:null;level:"Must-have"|"Nice-to-have"}[]=[];
 let level:"Must-have"|"Nice-to-have"|null=null;
 for(const line of lines){
  if(/^(?:must[- ]haves?|requirements|what you bring|qualifications|required skills|требования|обязательные требования)\s*[:：]?$/iu.test(line)){level="Must-have";continue}
  if(/^(?:nice[- ]to[- ]haves?|preferred(?: qualifications)?|bonus|будет плюсом|желательные требования)\s*[:：]?$/iu.test(line)){level="Nice-to-have";continue}
  if(/^(?:benefits|responsibilities|about us|what we offer|обязанности|условия|о компании)\s*[:：]?$/iu.test(line)){level=null;continue}
  if(level&&requirements.length<80&&line.length<2000)requirements.push({title:line.slice(0,160),quote:line,story:null,level});
 }
 return {company:fields.company||"Company to review",role:fields.role||"Role to review",location:fields.location||"Working arrangements not specified",url,description:raw,needsReview,requirements};
}

export function inferTemplate(sourceId:string,name:string,text:string):z.infer<typeof templateSchema>{
 const patterns:[z.infer<typeof templateSchema>["sectionOrder"][number],RegExp][]=[
  ["profile",/^(?:professional (?:profile|summary)|profile|summary|about me|профиль|о себе)$/iu],
  ["experience",/^(?:(?:professional|work|relevant|employment)\s+)?(?:experience|history)|^опыт(?: работы)?$/iu],
  ["skills",/^(?:(?:technical|key|core)\s+)?(?:skills|expertise)(?:\s*&\s*expertise)?$|^навыки$/iu],
  ["education",/^education(?:\s*&\s*qualifications)?$|^образование$/iu],
  ["certifications",/^certifications?|^сертификаты$/iu],
  ["languages",/^languages?$|^языки$/iu],
  ["additional",/^(?:additional (?:details|information)|interests|дополнительная информация)$/iu],
 ];
 const found:typeof patterns[number][0][]=[];
 for(const line of text.split(/\r?\n/).map(clean)){const section=patterns.find(([,re])=>re.test(line.replace(/:$/u,"")))?.[0];if(section&&!found.includes(section))found.push(section)}
 const order=found.length?found:["profile","experience","education","skills"] as const;
 const sectionOrder=[...order];if(!sectionOrder.includes("profile"))sectionOrder.unshift("profile");if(!sectionOrder.includes("experience"))sectionOrder.push("experience");
 return templateSchema.parse({sourceId,name,sectionOrder,style:"classic",notes:"Use this section order and a clear, text-based layout. Keep all personal facts from my own profile."});
}
function countSentences(text:string){const Segmenter=(Intl as unknown as {Segmenter:new (locale:string,options:{granularity:"sentence"})=>{segment(text:string):Iterable<{segment:string}>}}).Segmenter;return [...new Segmenter("en",{granularity:"sentence"}).segment(text)].filter(s=>s.segment.trim()).length}
export function applyCareerEdits(before:CareerDocument,edits:z.infer<typeof editSchema>[]):CareerDocument{
 const doc=structuredClone(before);
 const requireJob=(id:string)=>{if(!doc.jobs.some(job=>job.id===id))throw new Error("Unknown CV target job.")};
 for(const edit of edits){
  if(edit.type==="profile")Object.assign(doc.profile,edit.fields);
  if(edit.type==="story"){
   const existing=edit.id?doc.stories.find(s=>s.id===edit.id):undefined;
   if(edit.id&&!existing)throw new Error("Unknown experience story.");
   if(existing)Object.assign(existing,edit.fields);
   else{
    const id=randomUUID(),sourceId=randomUUID();
    doc.sources.push({id:sourceId,type:"manual",name:"Career assistant · user-provided experience",status:edit.fields.approved?"Reviewed":"Needs review",storyIds:[id]});
    doc.stories.push({id,title:"New experience",company:"",role:"",period:"",context:"",task:"",action:"",result:"",bullet:"",focus:"",tags:[],approved:false,source:"Entered through Career Hub chat",sourceIds:[sourceId],...edit.fields});
   }
  }
  if(edit.type==="story_remove"){
   if(!doc.stories.some(s=>s.id===edit.id))throw new Error("Unknown experience story.");
   doc.stories=doc.stories.filter(s=>s.id!==edit.id);
   for(const [job,ids]of Object.entries(doc.selections))doc.selections[job]=ids.filter(id=>id!==edit.id);
   for(const target of Object.values(doc.targets))for(const req of target.requirements as Record<string,unknown>[])if(req.story===edit.id)req.story=null;
   for(const source of doc.sources)if(source.storyIds)source.storyIds=source.storyIds.filter(id=>id!==edit.id);
   for(const [id,story]of Object.entries(doc.caseLinks))if(story===edit.id)delete doc.caseLinks[id];
  }
  if(edit.type==="cv_wording"){
   requireJob(edit.jobId);if(!doc.stories.some(story=>story.id===edit.storyId&&story.approved))throw new Error("Choose confirmed experience for CV wording.");
   if(countSentences(edit.wording)>2)throw new Error("Use at most two sentences for each CV story.");
   (doc.cvWording[edit.jobId]??={})[edit.storyId]=edit.wording;
  }
  if(edit.type==="cv_selection"){
   requireJob(edit.jobId);if(edit.storyIds.some(id=>!doc.stories.some(story=>story.id===id&&story.approved)))throw new Error("CV selections must use confirmed experience.");
   doc.selections[edit.jobId]=[...new Set(edit.storyIds)];
  }
  if(edit.type==="prep_note")doc.savedNotes.push(edit.text);
  if(edit.type==="template"){
   if(!doc.cvTemplate)throw new Error("Upload a reference CV before changing its layout preferences.");
   Object.assign(doc.cvTemplate,edit.sectionOrder?{sectionOrder:edit.sectionOrder}:{},edit.style?{style:edit.style}:{},edit.notes!==undefined?{notes:edit.notes}:{});
  }
 }
 for(const story of doc.stories)if(story.approved&&(!story.bullet.trim()||countSentences(story.bullet)>2))throw new Error("Confirmed experience needs a CV bullet of one or two sentences.");
 const result=validateDocument(doc);validateSavedVersions(before,result);return result;
}
