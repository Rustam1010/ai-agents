import { defineRpcContract } from "@get-bb/plugin-sdk";
import { z } from "zod";
const text=z.string().max(200_000),id=z.string().min(1).max(180);
const jsonRecord=z.record(z.string(),z.json());
export const profileSchema=z.object({
 name:z.string().max(500),headline:z.string().max(500),location:z.string().max(500),
 email:z.string().max(500),linkedin:z.string().max(2000),meridianPeriod:z.string().max(100),
 summary:text,skills:text,education:text,certifications:text,languages:text,additional:text,
 sections:z.array(z.object({id,title:z.string().max(500),body:text})).max(100),
});
export const storySchema=z.object({
 id,title:z.string().max(500),company:z.string().max(500),role:z.string().max(500),
 period:z.string().max(500),context:text,task:text,action:text,result:text,bullet:text,
 focus:z.string().max(1000),tags:z.array(z.string().max(500)).max(100),
 approved:z.boolean(),source:text,sourceIds:z.array(id).max(100),
}).passthrough();
export const sourceSchema=z.object({
 id,type:z.string().max(40),name:z.string().max(500),status:z.string().max(80),
 note:text.optional(),text:text.optional(),storyIds:z.array(id).max(500).optional(),fileId:id.optional(),
}).passthrough();
export const jobSchema=z.object({
 id,company:z.string().min(1).max(500),role:z.string().min(1).max(500),location:z.string().max(1000),
 description:text.optional(),status:z.enum(["saved","prep","applied","screen","interview","offer","closed"]),
 next:z.string().max(2000),applied:z.boolean(),outcome:z.string().max(1000),
 events:z.array(z.object({at:z.string().max(100),text})).max(10_000),
}).passthrough();
export const sectionSchema=z.enum(["profile","experience","skills","education","certifications","languages","additional"]);
export const templateSchema=z.object({sourceId:id,name:z.string().max(500),sectionOrder:z.array(sectionSchema).min(2).max(7),style:z.enum(["classic","compact"]),notes:z.string().max(4000)});
export const editSchema=z.discriminatedUnion("type",[
 z.object({type:z.literal("profile"),fields:profileSchema.partial()}),
 z.object({type:z.literal("story"),id:id.optional(),fields:storySchema.omit({id:true}).partial().strip()}),
 z.object({type:z.literal("story_remove"),id}),
 z.object({type:z.literal("cv_wording"),jobId:id,storyId:id,wording:z.string().min(1).max(4000)}),
 z.object({type:z.literal("cv_selection"),jobId:id,storyIds:z.array(id).max(100)}),
 z.object({type:z.literal("prep_note"),text:z.string().min(1).max(20000)}),
 z.object({type:z.literal("template"),sectionOrder:z.array(sectionSchema).min(2).max(7).optional(),style:z.enum(["classic","compact"]).optional(),notes:z.string().max(4000).optional()}),
]);
export const documentSchema=z.object({
 schemaVersion:z.literal(1),profile:profileSchema,stories:z.array(storySchema).max(3000),cvTemplate:templateSchema.nullable().default(null),
 sources:z.array(sourceSchema).max(2000),jobs:z.array(jobSchema).max(2000),
 targets:z.record(z.string(),jsonRecord),
 versions:z.array(z.object({id,number:z.number().int().positive(),target:id,label:z.string().max(500),
  text,stories:z.array(storySchema).max(500),sent:z.boolean()}).passthrough()).max(3000),
 caseLinks:z.record(z.string(),z.string()),cvWording:z.record(z.string(),z.record(z.string(),z.string().max(4000))),
 savedNotes:z.array(text).max(5000),selections:z.record(z.string(),z.array(id).max(3000)),
}).strict();
export type CareerDocument=z.infer<typeof documentSchema>;
const key=z.enum(["personal","demo"]);
const view=z.enum(["jobs","stories","resume","prep"]);
const stateOutput=z.object({revision:z.number().int(),document:documentSchema});
const composerRequest=z.object({projectId:id,providerId:id,model:z.string().min(1).max(500),reasoningLevel:z.string().max(100),permissionMode:z.enum(["auto","accept-edits","full"]),serviceTier:z.string().max(100).optional(),sessionOptions:z.record(z.string(),z.union([z.string(),z.boolean()])).optional(),executionInputSources:jsonRecord,environment:jsonRecord,input:z.array(z.json()).min(1).max(100),sendAt:z.number().optional()});
export const rpcContract=defineRpcContract({
 get:{input:z.object({key}),output:z.object({revision:z.number().int(),document:documentSchema})},
 save:{input:z.object({key,revision:z.number().int().nonnegative(),document:documentSchema,clientId:z.string().max(180).optional()}),output:z.object({revision:z.number().int()})},
 import_start:{input:z.object({key,name:z.string().min(1).max(500),size:z.number().int().min(1).max(10*1024*1024),purpose:z.enum(["cv","template"]).default("cv")}),output:z.object({uploadId:id})},
 import_part:{input:z.object({uploadId:id,index:z.number().int().min(0).max(80),data:z.string().max(400_000)}),output:z.object({received:z.number().int()})},
 import_finish:{input:z.object({uploadId:id}),output:sourceSchema},
 file_part:{input:z.object({id,offset:z.number().int().nonnegative()}),output:z.object({name:z.string(),data:z.string(),total:z.number().int()})},
 cv_pdf:{input:z.object({key,versionId:id}),output:z.object({name:z.string(),data:z.string().max(8_000_000),hash:z.string()})},
 proposal:{input:z.object({revision:z.number().int(),sourceId:id,kind:z.enum(["profile","story","requirements"]),payload:jsonRecord,jobId:id.optional()}),output:z.object({revision:z.number().int()})},
 job_create:{input:z.object({key,revision:z.number().int().nonnegative(),text:z.string().min(8).max(100000)}),output:stateOutput.extend({jobId:id})},
 template_set:{input:z.object({key,revision:z.number().int().nonnegative(),sourceId:id}),output:stateOutput},
 chat_get:{input:z.object({key}),output:z.object({threadId:id.nullable()})},
 chat_start:{input:z.object({key,view:z.enum(["stories","resume","prep"]),target:z.string().max(180),request:composerRequest}),output:z.object({threadId:id})},
 chat_context:{input:z.object({key,view,target:z.string().max(180)}),output:z.object({ok:z.boolean()})},
});
