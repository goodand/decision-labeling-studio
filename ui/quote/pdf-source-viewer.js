// Author: chatgpt_gpt6. PDF.js renderer; shared HWP search controls.
const $=id=>document.getElementById(id);
const show=(id,on)=>$(id).hidden=!on;
export const pdfViewer={
  active:false,version:0,renderVersion:0,searchVersion:0,page:0,hits:[],matches:[],matchIndex:-1,
  clear(){
    this.active=false;this.version++;this.renderVersion++;this.searchVersion++;
    this.abort?.abort();this.renderTask?.cancel();this.textLayer?.cancel();
    this.loadingTask?.destroy().catch(()=>{});this.loadingTask=null;this.document=null;
    this.matches=[];this.matchIndex=-1;this.query='';this.selecting=false;this.wheelBusy=false;
  },
  async open(row,name,isCurrent){
    const version=++this.version;this.row=row;this.abort=new AbortController();
    const alive=()=>version===this.version&&isCurrent();
    let metadata;
    while(alive()){
      const response=await fetch(`/api/source-preview?row=${encodeURIComponent(row)}`,{signal:this.abort.signal});
      metadata=await response.json();
      if(!response.ok||metadata.status==='error')throw Error(metadata.error||metadata.message||'PDF를 열지 못했습니다');
      if(metadata.status==='ready')break;
      $('preview-message').textContent='PDF 원문을 준비하는 중…';
      await new Promise(resolve=>setTimeout(resolve,1500));
    }
    if(!alive())return;
    const pdfjs=await import('/pdfjs/build/pdf.mjs');
    if(!alive())return;
    pdfjs.GlobalWorkerOptions.workerSrc='/pdfjs/build/pdf.worker.mjs';
    this.pdfjs=pdfjs;
    this.loadingTask=pdfjs.getDocument({url:`/api/source-pdf?row=${encodeURIComponent(row)}`,
      cMapUrl:'/pdfjs/cmaps/',cMapPacked:true,standardFontDataUrl:'/pdfjs/standard_fonts/',wasmUrl:'/pdfjs/wasm/'});
    const document=await this.loadingTask.promise;
    if(!alive())return;
    this.document=document;this.active=true;this.page=(metadata.suggested_page||1)-1;
    this.hits=(metadata.hits||[]).map(p=>p-1);this.matches=[];this.query='';this.matchIndex=-1;
    show('native-page',true);show('source-image',false);show('native-controls',true);show('pdf-controls',false);
    show('native-search',true);show('viewer-error',false);show('object-panel',false);
    $('viewer-mode').textContent='PDF 원본 직접 표시';
    documentQueryViewport().classList.add('native-scroll');
    await this.render();
  },
  async render(){
    if(!this.active)return;
    const version=++this.renderVersion,document=this.document;
    this.renderTask?.cancel();this.textLayer?.cancel();
    this.page=Math.max(0,Math.min(this.page,document.numPages-1));
    $('native-page-label').textContent=`${this.page+1} / ${document.numPages}쪽`;
    $('native-prev-hit').disabled=!this.hits.some(p=>p<this.page);
    $('native-next-hit').disabled=!this.hits.some(p=>p>this.page);
    const page=await document.getPage(this.page+1);
    if(version!==this.renderVersion||!this.active)return;
    const holder=$('native-page'),base=page.getViewport({scale:1});
    const viewport=page.getViewport({scale:(holder.clientWidth||800)/base.width});
    holder.replaceChildren();holder.style.height=`${viewport.height}px`;
    holder.style.setProperty('--total-scale-factor',String(viewport.scale*page.userUnit));
    const canvas=window.document.createElement('canvas');canvas.className='pdf-source-canvas';
    canvas.setAttribute('aria-label',`PDF 원본 ${this.page+1}쪽`);
    const ratio=Math.min(window.devicePixelRatio||1,2);
    canvas.width=Math.ceil(viewport.width*ratio);canvas.height=Math.ceil(viewport.height*ratio);
    canvas.style.width=`${viewport.width}px`;canvas.style.height=`${viewport.height}px`;
    const text=window.document.createElement('div');text.className='textLayer';
    holder.append(canvas,text);
    this.renderTask=page.render({canvasContext:canvas.getContext('2d'),viewport,transform:ratio===1?null:[ratio,0,0,ratio,0,0]});
    try{
      await this.renderTask.promise;
      if(version!==this.renderVersion||!this.active)return;
      const content=await page.getTextContent();
      if(version!==this.renderVersion||!this.active)return;
      this.textLayer=new this.pdfjs.TextLayer({textContentSource:content,container:text,viewport});
      await this.textLayer.render();
      if(version!==this.renderVersion||!this.active)return;
      this.highlights();
      $('preview-message').textContent=content.items.some(x=>x.str?.trim())?
        '글자 드래그 → Ctrl+C 복사 · Ctrl+F 검색 · 스크롤: 앞뒤 쪽 이동':
        '이 쪽에는 추출 가능한 텍스트가 없어. 스캔 이미지의 글자는 검색·복사할 수 없어.';
    }catch(error){
      if(version!==this.renderVersion||error.name==='RenderingCancelledException'||error.name==='AbortException')return;
      $('preview-message').textContent=`PDF 표시 오류: ${error.message}`;
    }
  },
  highlights(){
    const holder=$('native-page');holder.querySelectorAll('.pdf-search-highlight').forEach(x=>x.remove());
    for(const [index,match] of this.matches.entries()){
      if(match.page!==this.page)continue;
      const [x0,y0,x1,y1]=match.bbox,mark=document.createElement('span');
      mark.className='pdf-search-highlight'+(index===this.matchIndex?' current':'');
      Object.assign(mark.style,{left:`${100*x0/match.width}%`,top:`${100*y0/match.height}%`,
        width:`${100*(x1-x0)/match.width}%`,height:`${100*(y1-y0)/match.height}%`});holder.append(mark);
    }
  },
  count(){
    $('native-search-count').textContent=this.matches.length?`${this.matchIndex+1} / ${this.matches.length}${this.truncated?'+':''}건`:this.query?'결과 없음':'Ctrl+F로 검색';
    $('native-search-prev').disabled=!this.matches.length;$('native-search-next').disabled=!this.matches.length;
  },
  async search(query){
    const version=++this.searchVersion;this.query=query.trim();this.matches=[];this.matchIndex=-1;this.truncated=false;
    this.count();this.highlights();
    if(!this.query)return;
    $('native-search-count').textContent='검색 중…';
    try{
      const response=await fetch(`/api/source-search?row=${encodeURIComponent(this.row)}&q=${encodeURIComponent(this.query)}`,{signal:this.abort.signal});
      const result=await response.json();
      if(version!==this.searchVersion||!this.active)return;
      if(!response.ok)throw Error(result.error||'검색 실패');
      this.matches=result.matches;this.truncated=result.truncated;
      if(this.matches.length){this.matchIndex=0;this.page=this.matches[0].page;await this.render();documentQueryViewport().scrollTop=0}
      if(version===this.searchVersion)this.count();
    }catch(error){if(version===this.searchVersion&&this.active)$('native-search-count').textContent=`검색 오류: ${error.message}`}
  },
  async moveSearch(step){
    if(!this.matches.length)return this.search($('native-search-input').value);
    this.matchIndex=(this.matchIndex+step+this.matches.length)%this.matches.length;
    this.page=this.matches[this.matchIndex].page;this.count();await this.render();
    const mark=$('native-page').querySelector('.pdf-search-highlight.current');
    if(mark)documentQueryViewport().scrollTop=Math.max(0,mark.offsetTop-80);
  },
  async moveBusiness(step){
    const next=step<0?this.hits.filter(p=>p<this.page).at(-1):this.hits.find(p=>p>this.page);
    if(next==null)return;this.page=next;await this.render();documentQueryViewport().scrollTop=0;
  }
};
function documentQueryViewport(){return document.querySelector('.preview-viewport')}
documentQueryViewport().addEventListener('wheel',async event=>{
  if(!pdfViewer.active||pdfViewer.wheelBusy||pdfViewer.selecting)return;
  const viewport=event.currentTarget,forward=event.deltaY>0&&viewport.scrollTop+viewport.clientHeight>=viewport.scrollHeight-3&&pdfViewer.page<pdfViewer.document.numPages-1;
  const backward=event.deltaY<0&&viewport.scrollTop<=3&&pdfViewer.page>0;
  if(!forward&&!backward)return;
  event.preventDefault();pdfViewer.wheelBusy=true;pdfViewer.page+=forward?1:-1;
  try{await pdfViewer.render();viewport.scrollTop=forward?0:viewport.scrollHeight-viewport.clientHeight}
  finally{setTimeout(()=>pdfViewer.wheelBusy=false,180)}
},{passive:false});
$('native-page').addEventListener('pointerdown',e=>{if(pdfViewer.active)pdfViewer.selecting=!!e.target.closest('.textLayer')});
document.addEventListener('pointerup',()=>pdfViewer.selecting=false);
document.addEventListener('pointercancel',()=>pdfViewer.selecting=false);
let resizeTimer;
new ResizeObserver(()=>{if(pdfViewer.active){clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>pdfViewer.render(),180)}}).observe(documentQueryViewport());
