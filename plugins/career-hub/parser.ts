import {Worker} from "node:worker_threads";
import {fileURLToPath} from "node:url";
import {existsSync} from "node:fs";
export class ImportParser{
 private workers=new Set<Worker>();
 async exportPdf(text:string,style:"classic"|"compact"="classic"):Promise<Buffer>{
  if(text.length>40000)throw new Error("Shorten the CV before PDF export (40,000 characters maximum).");
  if(this.workers.size>=2)throw new Error("Two document operations are running. Try again shortly.");
  const direct=new URL("./import-worker.cjs",import.meta.url),filename=existsSync(direct)?direct:new URL("../import-worker.cjs",import.meta.url);
  const directFont=new URL("./assets/NotoSans-Regular.ttf",import.meta.url),font=existsSync(directFont)?directFont:new URL("../assets/NotoSans-Regular.ttf",import.meta.url);
  const worker=new Worker(filename,{workerData:{ext:"export-pdf",text,style,font:fileURLToPath(font)},resourceLimits:{maxOldGenerationSizeMb:160,maxYoungGenerationSizeMb:16}});
  this.workers.add(worker);
  try{return await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>{void worker.terminate();reject(new Error("PDF export timed out."))},20000);
   worker.once("message",message=>{clearTimeout(timer);if(message.ok)resolve(Buffer.from(message.data,"base64"));else reject(new Error(message.error))});
   worker.once("error",error=>{clearTimeout(timer);reject(error)});worker.once("exit",code=>{clearTimeout(timer);if(code!==0)reject(new Error("PDF export stopped."))});
  })}finally{this.workers.delete(worker);await worker.terminate()}
 }
 async extract(bytes:Buffer,extension:string):Promise<{text:string;pages:number}>{
  if(this.workers.size>=2)throw new Error("Two imports are running. Try again shortly.");
  const direct=new URL("./import-worker.cjs",import.meta.url);
  const filename=existsSync(direct)?direct:new URL("../import-worker.cjs",import.meta.url);
  const worker=new Worker(filename,{workerData:{data:bytes,ext:extension},
   resourceLimits:{maxOldGenerationSizeMb:160,maxYoungGenerationSizeMb:16}});
  this.workers.add(worker);
  try{return await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>{void worker.terminate();reject(new Error("Import exceeded 20 seconds. Try a text copy."))},20000);
   worker.once("message",message=>{clearTimeout(timer);if(message.ok)resolve({text:message.text,pages:message.pages});else reject(new Error(message.error))});
   worker.once("error",error=>{clearTimeout(timer);reject(error)});
   worker.once("exit",code=>{clearTimeout(timer);if(code!==0)reject(new Error("Import worker stopped. Try a text copy."))});
  })}finally{this.workers.delete(worker);await worker.terminate()}
 }
 dispose(){for(const worker of this.workers)void worker.terminate();this.workers.clear()}
}
