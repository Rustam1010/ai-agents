const {parentPort,workerData}=require("node:worker_threads");
(async()=>{
 if(workerData.ext==="export-pdf"){
  const PDFDocument=require("pdfkit"),chunks=[],compact=workerData.style==="compact",margin=compact?36:48;
  const doc=new PDFDocument({size:"A4",margins:{top:margin,bottom:margin,left:margin,right:margin},font:workerData.font,info:{Title:"Curriculum Vitae",Creator:"Career Hub"}});
  const done=new Promise((resolve,reject)=>{doc.on("data",chunk=>chunks.push(chunk));doc.on("end",()=>resolve(Buffer.concat(chunks)));doc.on("error",reject)});
  for(const [index,line]of workerData.text.split("\n").entries()){
   if(!line.trim()){doc.moveDown(0.5);continue}
   const section=/^(PROFILE|EXPERIENCE|EDUCATION|SKILLS|CERTIFICATIONS|LANGUAGES|ADDITIONAL DETAILS)$/.test(line.trim());
   doc.fontSize(index===0?20:section?12:compact?9:10).fillColor("#17251f").text(line,{lineGap:compact?1.5:3});
  }
  doc.end();const bytes=await done;if(bytes.length>5000000)throw new Error("Generated PDF is too large.");
  parentPort.postMessage({ok:true,data:bytes.toString("base64")});return;
 }
 const data=new Uint8Array(workerData.data);let text="",pages=0;
 if(workerData.ext==="pdf"){
  const {getDocumentProxy,extractText}=await import("unpdf");
  const pdf=await getDocumentProxy(data,{isEvalSupported:false,maxImageSize:1000000,disableFontFace:true,isOffscreenCanvasSupported:false,isImageDecoderSupported:false});
  try{if(pdf.numPages>60)throw new Error("CV exceeds the 60-page limit.");const result=await extractText(pdf,{mergePages:false});text=result.text.join("\n\n");pages=result.totalPages}finally{await pdf.destroy()}
 }else if(workerData.ext==="docx"){
  const {unzipSync,strFromU8}=await import("fflate");let expanded=0;
  const files=unzipSync(data,{filter(file){
   if(!/^word\/(document|header\d+|footer\d+|footnotes|endnotes)\.xml$/.test(file.name))return false;
   expanded+=file.originalSize;if(file.originalSize>5000000||expanded>12000000)throw new Error("DOCX text is too large.");return true;
  }});
  if(!files["word/document.xml"])throw new Error("No DOCX document found.");
  const decode=s=>s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi,(_,code)=>{
   const entities={amp:"&",lt:"<",gt:">",quot:'"',apos:"'"};
   if(entities[code])return entities[code];
   const n=code.startsWith("#x")?parseInt(code.slice(2),16):parseInt(code.slice(1),10);
   return Number.isFinite(n)&&n>0&&n<=0x10ffff?String.fromCodePoint(n):"";
  });
  text=Object.values(files).map(bytes=>{
   const xml=strFromU8(bytes);if(/<!DOCTYPE|<!ENTITY/i.test(xml))throw new Error("Unsupported XML declarations.");
   return decode(xml.replace(/<\/w:p>/g,"\n").replace(/<w:(tab|br)\b[^>]*\/>/g," ").replace(/<[^>]+>/g,""));
  }).join("\n");
 }else{text=new TextDecoder("utf-8",{fatal:true}).decode(data)}
 text=text.replace(/\u0000/g,"").replace(/\n{4,}/g,"\n\n").trim();
 if(text.length>200000)throw new Error("Text exceeds 200,000 characters.");
 parentPort.postMessage({ok:true,text,pages});
})().catch(error=>parentPort.postMessage({ok:false,error:String(error.message||error)}));
