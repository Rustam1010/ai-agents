import {test} from "node:test";
import assert from "node:assert/strict";
import {zipSync,strToU8} from "fflate";
import {emptyDocument,validateDocument,validateSavedVersions} from "../model";
import {ImportParser} from "../parser";
import {inferTemplate} from "../career-actions";

function workspace(){
 const doc=emptyDocument();
 doc.jobs.push({id:"job-1",company:"Example",role:"Data lead",location:"Remote",status:"saved",next:"Prepare",applied:false,outcome:"",events:[]});
 doc.targets["job-1"]={company:"Example",role:"Data lead",requirements:[]};return doc;
}
test("new personal workspace has no fictional profile or jobs",()=>{const doc=emptyDocument();assert.equal(doc.profile.name,"");assert.deepEqual(doc.jobs,[]);validateDocument(doc)});
test("saved CVs cannot be rewritten but can be recorded as sent",()=>{
 const before=workspace();before.versions.push({id:"v1",number:1,target:"job-1",label:"v1",text:"Original",stories:[],sent:false});
 const after=structuredClone(before);after.versions[0].sent=true;validateSavedVersions(before,after);
 after.versions[0].text="Rewritten";assert.throws(()=>validateSavedVersions(before,after),/immutable/);
});
test("application history cannot be truncated",()=>{
 const before=workspace();before.jobs[0].events.push({at:"2026-11-10",text:"Applied"});const after=structuredClone(before);after.jobs[0].events=[];
 assert.throws(()=>validateSavedVersions(before,after),/append-only/);
 after.jobs[0].events=[...before.jobs[0].events,{at:"2026-11-11",text:"Correction"}];validateSavedVersions(before,after);
});
test("dangling CV targets are rejected",()=>{const doc=emptyDocument();doc.versions.push({id:"v1",number:1,target:"missing",label:"v1",text:"CV",stories:[],sent:false});assert.throws(()=>validateDocument(doc),/unknown job/)});
test("UTF-8 source extraction preserves details",async()=>{const parser=new ImportParser();try{const result=await parser.extract(Buffer.from("Alex Example\nAnalytics leader\nПример"),"txt");assert.match(result.text,/Пример/)}finally{parser.dispose()}});
test("DOCX extraction reads text without executing markup",async()=>{
 const parser=new ImportParser(),xml='<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Alex &amp; Team</w:t></w:r></w:p><w:p><w:r><w:t>Led analytics</w:t></w:r></w:p></w:body></w:document>';
 try{const result=await parser.extract(Buffer.from(zipSync({"word/document.xml":strToU8(xml)})),"docx");assert.equal(result.text,"Alex & Team\nLed analytics")}finally{parser.dispose()}
});
test("invalid DOCX is a bounded failure",async()=>{const parser=new ImportParser();try{await assert.rejects(parser.extract(Buffer.from("not a zip"),"docx"))}finally{parser.dispose()}});
test("PDF text is actually extracted",async()=>{
 const objects=['1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n','2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n','3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n','4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n'];
 const stream="BT /F1 14 Tf 50 740 Td (Alex Example - Data Analytics) Tj ET";
 objects.push("5 0 obj\n<< /Length "+stream.length+" >>\nstream\n"+stream+"\nendstream\nendobj\n");
 let pdf="%PDF-1.4\n",offsets=[0];for(const object of objects){offsets.push(Buffer.byteLength(pdf));pdf+=object}const xref=Buffer.byteLength(pdf);
 pdf+="xref\n0 6\n0000000000 65535 f \n"+offsets.slice(1).map(n=>String(n).padStart(10,"0")+" 00000 n \n").join("")+"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"+xref+"\n%%EOF";
 const parser=new ImportParser();try{const result=await parser.extract(Buffer.from(pdf),"pdf");assert.equal(result.pages,1);assert.match(result.text,/Alex Example/)}finally{parser.dispose()}
});
test("exported CV PDF preserves English and Cyrillic text",async()=>{const parser=new ImportParser();try{const bytes=await parser.exportPdf("ALEX EXAMPLE\nPROFILE\nАналитика и ML\nEXPERIENCE\nLed three data teams.");assert.equal(bytes.subarray(0,4).toString(),"%PDF");const result=await parser.extract(bytes,"pdf");assert.match(result.text,/Аналитика и ML/);assert.match(result.text,/Led three data teams/)}finally{parser.dispose()}});
test("PDF imports preserve headings for reference section order",async()=>{const parser=new ImportParser();try{const bytes=await parser.exportPdf("EXAMPLE PERSON\nSKILLS\nPython and analytics\nEXPERIENCE\nLed data teams.\nEDUCATION\nExample university\nPROFILE\nA concise profile.");const result=await parser.extract(bytes,"pdf");assert.match(result.text,/SKILLS\n/);assert.deepEqual(inferTemplate("source","CV.pdf",result.text).sectionOrder,["skills","experience","education","profile"])}finally{parser.dispose()}});
