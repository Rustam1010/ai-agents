import {test} from "node:test";
import assert from "node:assert/strict";
import {parseJobPaste,inferTemplate,applyCareerEdits} from "../career-actions";
import {emptyDocument} from "../model";

test("pasted chat message extracts labelled fields and exact requirement text",()=>{
 const text="Here is the vacancy we discussed:\n**Company:** Example Labs\n**Role:** Head of Analytics\n**Location:** Berlin · Hybrid\nhttps://example.com/job/42\nMust-have:\n- Lead analytics teams\n- Experimentation\nNice-to-have:\n- ML delivery\nBenefits:\n- Learning budget";
 const job=parseJobPaste(text);assert.equal(job.company,"Example Labs");assert.equal(job.role,"Head of Analytics");assert.equal(job.location,"Berlin · Hybrid");assert.equal(job.description,text);assert.equal(job.requirements.length,3);assert.equal(job.requirements[2].level,"Nice-to-have");assert.equal(job.needsReview,false);
});
test("job intake accepts plain headings, role at company, and Russian chat labels",()=>{
 assert.equal(parseJobPaste("Example Labs\nSenior Data Scientist\nRemote · Europe").company,"Example Labs");
 assert.equal(parseJobPaste("Director of Data at Example\nLead analytics").company,"Example");
 const job=parseJobPaste("Компания: Пример\nДолжность: Руководитель аналитики\nЛокация: Берлин\nТребования:\nЭксперименты и управление командой");assert.equal(job.company,"Пример");assert.equal(job.requirements[0].quote,"Эксперименты и управление командой");
});
test("unlabelled unknown vacancy is preserved without invented facts",()=>{const job=parseJobPaste("We are hiring. Read the details in the attached message.");assert.equal(job.needsReview,true);assert.equal(job.company,"Company to review");assert.deepEqual(job.requirements,[])});
test("reference template infers section order without importing another person's facts",()=>{
 const doc=emptyDocument(),t=inferTemplate("template-1","Example CV.pdf","Other Person\nSKILLS\nPython\nWORK EXPERIENCE\nCompany A\nEDUCATION\nDegree\nPROFILE\nSummary");
 assert.deepEqual(t.sectionOrder,["skills","experience","education","profile"]);assert.equal(doc.profile.name,"");assert.equal(t.style,"classic");
});
test("chat edits apply profile, confirmed experience, CV wording and prep atomically",()=>{
 const before=emptyDocument();before.jobs.push({id:"j1",company:"Example",role:"Lead",location:"Remote",status:"saved",next:"Prepare",applied:false,outcome:"",events:[]});before.targets.j1={company:"Example",role:"Lead",requirements:[]};
 const after=applyCareerEdits(before,[{type:"profile",fields:{languages:"English, Русский"}},{type:"story",fields:{title:"Aligned teams",bullet:"Aligned three teams through shared planning.",approved:true}},{type:"prep_note",text:"Prepare evidence of personal contribution."}]);
 const final=applyCareerEdits(after,[{type:"cv_wording",jobId:"j1",storyId:after.stories[0].id,wording:"Aligned three analytics teams through shared planning."},{type:"cv_selection",jobId:"j1",storyIds:[after.stories[0].id]}]);
 assert.equal(final.profile.languages,"English, Русский");assert.equal(final.savedNotes.length,1);assert.equal(final.selections.j1.length,1);assert.deepEqual(final.jobs,before.jobs);assert.deepEqual(final.versions,before.versions);assert.equal(before.profile.languages,"");
});
test("chat enforces compact bullets, confirmed selection and existing template",()=>{
 const doc=emptyDocument();assert.throws(()=>applyCareerEdits(doc,[{type:"story",fields:{approved:true,bullet:"First. Second. Third."}}]),/two sentences/);assert.throws(()=>applyCareerEdits(doc,[{type:"template",style:"compact"}]),/Upload a reference/);
});
