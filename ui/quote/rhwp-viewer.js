// Source viewer only. Human votes remain in the existing review API.
import init, {HwpDocument} from '/rhwp/rhwp.js';
import {pdfViewer} from '/pdf-source-viewer.js?v=1';
import {pickMatch,searchKey,pageOfMatch} from '/hwp_locate.js';

const $=id=>document.getElementById(id);
let engine=null,doc=null,row=null,page=0,hits=[],svgUrl=null,request=0;
let searchResults=[],searchIndex=-1,searchQuery='',searchTimer=null;
let wheelBusy=false;
let textObserver=null,selectingText=false;
const safeJson=value=>{try{return JSON.parse(value)}catch{return null}};
const visible=(id,on)=>$(id).hidden=!on;

// Author: chatgpt_gpt6. Copy native text, never OCR or normalized text.
function renderSelectableText(holder,info){
  if(!info.width||!info.height)return;
  const runs=(safeJson(doc.getPageTextLayout(page))?.runs||[]).filter(r=>r.text);
  const layer=document.createElement('div');layer.className='native-text-layer';
  Object.assign(layer.style,{position:'absolute',left:'0',top:'0',width:`${info.width}px`,height:`${info.height}px`,transformOrigin:'top left',pointerEvents:'none',zIndex:'4',userSelect:'text'});
  const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
  let previous=null;
  for(const run of runs){
    if(![run.x,run.y,run.w,run.h].every(Number.isFinite))continue;
    if(previous){
      const sameLine=Math.abs(run.y-previous.y)<Math.min(run.h,previous.h)*0.4;
      const sameCell=JSON.stringify(run.cellPath)===JSON.stringify(previous.cellPath)&&run.parentParaIdx===previous.parentParaIdx;
      const separator=document.createElement('span');
      separator.textContent=sameLine&&sameCell?'':'\n';
      Object.assign(separator.style,{position:'absolute',whiteSpace:'pre',color:'transparent',fontSize:'1px'});layer.append(separator);
    }
    const span=document.createElement('span');span.className='native-text-run';span.textContent=run.text;
    const size=run.fontSize||run.h;
    Object.assign(span.style,{position:'absolute',left:`${run.x}px`,top:`${run.y}px`,height:`${run.h}px`,fontFamily:run.fontFamily||'serif',fontSize:`${size}px`,fontWeight:run.bold?'bold':'normal',fontStyle:run.italic?'italic':'normal',lineHeight:`${run.h}px`,whiteSpace:'pre',color:'transparent',cursor:'text',pointerEvents:'auto',userSelect:'text',transformOrigin:'left top'});
    ctx.font=`${run.italic?'italic ':''}${run.bold?'bold ':''}${size}px "${run.fontFamily||'serif'}"`;
    const measured=ctx.measureText(run.text).width;
    if(measured>0&&run.w>0)span.style.transform=`scaleX(${run.w/measured})`;
    layer.append(span);previous=run;
  }
  holder.append(layer);
  const resize=()=>{layer.style.transform=`scale(${holder.clientWidth/info.width})`};
  textObserver=new ResizeObserver(resize);textObserver.observe(holder);resize();
}

function properties(control){
  const kind=control.type||'객체',sec=control.secIdx,para=control.paraIdx,idx=control.controlIdx;
  let detail={};
  try{
    if(kind==='table')detail=safeJson(doc.getTableProperties(sec,para,idx))||{};
    else if(kind==='picture'||kind==='image')detail=safeJson(doc.getPictureProperties(sec,para,idx))||{};
    else if(kind==='shape')detail=safeJson(doc.getShapeProperties(sec,para,idx))||{};
  }catch{}
  const fields=[['종류',kind],['표 크기',kind==='table'?`${control.rowCount}행 × ${control.colCount}열`:null],
    ['화면 크기',`${Math.round(control.w||0)} × ${Math.round(control.h||0)}`],
    ['페이지 나눔',detail.pageBreak],['반복 머리행',detail.repeatHeader],
    ['문자처럼 취급',detail.treatAsChar],['설명글',detail.caption||detail.altText],
    ['내부 여백',detail.paddingLeft!=null?`${detail.paddingLeft} / ${detail.paddingRight} / ${detail.paddingTop} / ${detail.paddingBottom}`:null]];
  const panel=$('object-panel');panel.replaceChildren();const heading=document.createElement('strong');heading.textContent='선택한 객체의 속성';panel.append(heading);
  const dl=document.createElement('dl');for(const [label,value] of fields){if(value==null||value==='')continue;const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=String(value);dl.append(dt,dd)}panel.append(dl);panel.hidden=false;
}

function renderHighlights(holder,info){
  if(!searchResults.length||!info.width||!info.height)return;
  const matches=searchResults.filter(item=>item.page===page);
  if(!matches.length)return;
  let layout;
  try{layout=safeJson(doc.getPageTextLayout(page))}catch{return}
  for(const run of layout?.runs||[]){
    const relevant=matches.filter(({match})=>{
      if(match.sec!==run.secIdx)return false;
      const cell=match.cellContext;
      return cell?run.parentParaIdx===cell.parentPara&&run.controlIdx===cell.ctrlIdx&&run.cellIdx===cell.cellIdx&&run.cellParaIdx===cell.cellPara:run.paraIdx===match.para&&!run.cellPath;
    });
    for(const {match} of relevant){
      const start=Math.max(0,match.charOffset-run.charStart);
      const end=Math.min(run.text.length,match.charOffset+match.length-run.charStart);
      if(start>=end||!Array.isArray(run.charX)||run.charX[end]==null)continue;
      const x0=run.x+run.charX[start],x1=run.x+run.charX[end];
      const mark=document.createElement('span');mark.className='search-highlight';
      mark.style.left=`${100*x0/info.width}%`;mark.style.top=`${100*run.y/info.height}%`;
      mark.style.width=`${100*Math.max(x1-x0,4)/info.width}%`;mark.style.height=`${100*run.h/info.height}%`;
      holder.append(mark);
    }
  }
}

function updateSearchCount(){
  $('native-search-count').textContent=searchResults.length?`${searchIndex+1} / ${searchResults.length}건`:searchQuery?'결과 없음':'Ctrl+F로 검색';
  $('native-search-prev').disabled=!searchResults.length;$('native-search-next').disabled=!searchResults.length;
}

function runSearch(query){
  if(pdfViewer.active)return pdfViewer.search(query);
  searchQuery=query.trim();searchResults=[];searchIndex=-1;
  if(!doc||!searchQuery){updateSearchCount();render();return}
  let matches=[];
  try{matches=safeJson(doc.searchAllText(searchQuery,false,true))||[]}catch(error){$('native-search-count').textContent=`검색 오류: ${error.message}`;return}
  for(const match of matches){
    const position=safeJson(doc.getPageOfPosition(match.sec,match.cellContext?.parentPara??match.para));
    if(position?.ok&&Number.isInteger(position.page))searchResults.push({page:position.page,match});
  }
  if(searchResults.length){searchIndex=0;page=searchResults[0].page}
  updateSearchCount();render();document.querySelector('.preview-viewport').scrollTop=0;
}

function moveSearch(step){
  if(pdfViewer.active)return pdfViewer.moveSearch(step);
  if(!searchResults.length){runSearch($('native-search-input').value);return}
  searchIndex=(searchIndex+step+searchResults.length)%searchResults.length;
  page=searchResults[searchIndex].page;updateSearchCount();render();document.querySelector('.preview-viewport').scrollTop=0;
}

function render(){
  if(!doc)return;
  const count=doc.pageCount();page=Math.min(Math.max(page,0),count-1);
  $('native-page-label').textContent=`${page+1} / ${count}쪽`;
  $('native-prev-hit').disabled=!hits.some(p=>p<page);$('native-next-hit').disabled=!hits.some(p=>p>page);
  const holder=$('native-page');holder.replaceChildren();$('object-panel').hidden=true;
  textObserver?.disconnect();
  if(svgUrl)URL.revokeObjectURL(svgUrl);
  const svg=doc.renderPageSvg(page);
  svgUrl=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'}));
  const image=document.createElement('img');image.src=svgUrl;image.alt=`HWP 원본 ${page+1}쪽`;image.draggable=false;image.style.userSelect='none';holder.append(image);
  const info=safeJson(doc.getPageInfo(page))||{};
  const layout=safeJson(doc.getPageControlLayout(page))||{};
  const controls=Array.isArray(layout.controls)?layout.controls:[];
  for(const [i,control] of controls.entries()){
    if(!Number.isFinite(control.x)||!Number.isFinite(control.y)||!Number.isFinite(control.w)||!Number.isFinite(control.h)||!info.width||!info.height)continue;
    const button=document.createElement('button');button.className='object-hotspot';button.type='button';
    button.title=`${control.type||'객체'} ${i+1} · 속성 확인`;
    button.setAttribute('aria-label',button.title);
    button.style.left=`${100*control.x/info.width}%`;button.style.top=`${100*control.y/info.height}%`;
    button.style.width=`${100*control.w/info.width}%`;button.style.height=`${100*control.h/info.height}%`;
    button.onclick=()=>properties(control);if(new URLSearchParams(location.search).get('selection_test')==='no_hotspots')button.style.pointerEvents='none';holder.append(button);
  }
  renderHighlights(holder,info);
  renderSelectableText(holder,info);
  $('preview-message').textContent=`글자 드래그 → Ctrl+C 복사 · 스크롤: 앞뒤 쪽 이동 · 주황 테두리: 객체 속성`;
}

function findPages(name){
  const variants=[name,name.replace(/(?:\([^)]*\)|（[^）]*）)+$/g,'').trim()].filter(Boolean);
  let matches=[];
  for(const query of variants){
    try{matches=safeJson(doc.searchAllText(query,false,true))||[]}catch{}
    if(matches.length)break;
  }
  const pages=[];
  for(const match of matches){
    const position=safeJson(doc.getPageOfPosition(match.sec,match.cellContext?.parentPara??match.para));
    if(position?.ok&&Number.isInteger(position.page))pages.push(position.page);
  }
  hits=[...new Set(pages)].sort((a,b)=>a-b);
  page=hits[0]??0;
}

async function openCase({row:newRow,name,searchText,filePage}){
  pdfViewer.clear();textObserver?.disconnect();
  $('native-page').style.height='';
  if(doc){doc.free();doc=null}
  const current=++request;row=newRow;doc=null;hits=[];visible('native-page',false);visible('object-panel',false);
  wheelBusy=false;document.querySelector('.preview-viewport').scrollTop=0;
  clearTimeout(searchTimer);
  searchResults=[];searchIndex=-1;searchQuery='';$('native-search-input').value='';updateSearchCount();visible('native-search',false);
  $('viewer-mode').textContent='rhwp 여는 중';visible('viewer-error',false);
  $('preview-message').textContent='HWP/HWPX 원본을 브라우저에서 여는 중…';
  let format=null;
  try{
    const infoResponse=await fetch(`/api/source-info?row=${encodeURIComponent(newRow)}`);
    const sourceInfo=await infoResponse.json();
    if(current!==request)return;
    if(!infoResponse.ok)throw Error(sourceInfo.error||'원본을 찾을 수 없습니다');
    format=sourceInfo.format;
    $('agency').title=`원본 문서 폴더 열기 · ${sourceInfo.filename}`;
    if(format==='.pdf'){
      $('viewer-mode').textContent='PDF 여는 중';$('preview-message').textContent='PDF 원본을 브라우저에서 여는 중…';
      await pdfViewer.open(newRow,name,()=>current===request);if(current===request&&Number.isInteger(filePage)){pdfViewer.page=filePage-1;await pdfViewer.render();}return;
    }
    const response=await fetch(`/api/source-native?row=${encodeURIComponent(newRow)}`);
    if(!response.ok){const error=await response.json();throw Error(error.error||'HWP 원본을 열 수 없습니다')}
    const bytes=new Uint8Array(await response.arrayBuffer());
    if(current!==request)return;
    if(!engine){globalThis.measureTextWidth=(font,text)=>{const canvas=document.createElement('canvas');const ctx=canvas.getContext('2d');ctx.font=font;return ctx.measureText(text).width};await init({module_or_path:'/rhwp/rhwp_bg.wasm'});engine=true}
    if(current!==request)return;
    doc=new HwpDocument(bytes);findPages(name);
    visible('native-controls',true);visible('pdf-controls',false);visible('native-page',true);visible('source-image',false);visible('native-search',true);render();
    document.querySelector('.preview-viewport').classList.add('native-scroll');
    $('viewer-mode').textContent='rhwp 원본 직접 표시';
    if(searchText){$('native-search-input').value=searchText;runSearch(searchText);}
  }catch(error){
    if(current!==request)return;
    doc=null;
    try{
      if(format==='.pdf'||format===null)throw error;
      await pdfViewer.open(newRow,name,()=>current===request);
      return;
    }catch(pdfError){
      if(current!==request)return;
      pdfViewer.clear();
      $('viewer-error').textContent=`원본 표시 실패: ${pdfError.message}`;
    }
    visible('native-controls',false);visible('pdf-controls',true);visible('native-page',false);
    visible('native-search',false);
    document.querySelector('.preview-viewport').classList.remove('native-scroll');
    $('viewer-mode').textContent='대체 화면';
    visible('viewer-error',true);
    if(typeof window.loadPreview==='function')window.loadPreview(newRow);
  }
}

$('native-prev-hit').onclick=()=>{if(pdfViewer.active)return pdfViewer.moveBusiness(-1);page=hits.filter(p=>p<page).at(-1);render();document.querySelector('.preview-viewport').scrollTop=0};
$('native-next-hit').onclick=()=>{if(pdfViewer.active)return pdfViewer.moveBusiness(1);page=hits.find(p=>p>page);render();document.querySelector('.preview-viewport').scrollTop=0};
document.querySelector('.preview-viewport').addEventListener('wheel',event=>{
  if(!doc||!document.querySelector('.preview-viewport').classList.contains('native-scroll'))return;
  event.stopPropagation();
  if(wheelBusy){event.preventDefault();return;}
  if(selectingText)return;
  const viewport=event.currentTarget;
  const atBottom=viewport.scrollTop+viewport.clientHeight>=viewport.scrollHeight-3;
  const atTop=viewport.scrollTop<=3;
  const forward=event.deltaY>0&&atBottom&&page<doc.pageCount()-1;
  const backward=event.deltaY<0&&atTop&&page>0;
  if(!forward&&!backward)return;
  event.preventDefault();wheelBusy=true;page+=forward?1:-1;render();
  const image=$('native-page').querySelector('img');
  const position=()=>{viewport.scrollTop=forward?0:viewport.scrollHeight-viewport.clientHeight};
  image.addEventListener('load',position,{once:true});
  if(image.complete)position();
  setTimeout(()=>{wheelBusy=false},450);
},{passive:false});
$('native-page').addEventListener('pointerdown',event=>{selectingText=!!event.target.closest('.native-text-layer')});
document.addEventListener('pointerup',()=>{selectingText=false});
document.addEventListener('pointercancel',()=>{selectingText=false});
document.addEventListener('copy',event=>{
  const selection=window.getSelection();
  if(!selection||selection.isCollapsed||!selection.rangeCount)return;
  const layer=$('native-page').querySelector('.native-text-layer');
  if(!layer||!layer.contains(selection.anchorNode)||!layer.contains(selection.focusNode))return;
  const fragment=selection.getRangeAt(0).cloneContents();
  if(event.clipboardData){event.clipboardData.setData('text/plain',fragment.textContent);event.preventDefault()}
});
$('native-search-input').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>runSearch($('native-search-input').value),180)};
$('native-search-input').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();clearTimeout(searchTimer);if($('native-search-input').value.trim()!==(pdfViewer.active?pdfViewer.query:searchQuery))runSearch($('native-search-input').value);else moveSearch(event.shiftKey?-1:1)}else if(event.key==='Escape'){$('native-search-input').blur()}};
$('native-search-prev').onclick=()=>moveSearch(-1);$('native-search-next').onclick=()=>moveSearch(1);
document.addEventListener('keydown',event=>{
  if((!doc&&!pdfViewer.active)||!(event.ctrlKey||event.metaKey)||event.key.toLowerCase()!=='f')return;
  event.preventDefault();$('native-search-input').focus();$('native-search-input').select();
},true);
window.addEventListener('source-case-change',event=>openCase(event.detail));
// 감사 카드 → XPath 위치 이동. XPath와 인용이 같은 곳을 가리킬 때만 이동·강조한다.
window.addEventListener('source-locate',({detail:{location:loc,quote,report,context_before:ctx}})=>{
  if(!doc){report('위치 확인 불가 — HWP 원본이 열려 있지 않음');return}
  let matches=[];try{matches=safeJson(doc.searchAllText(searchKey(quote),false,true))||[]}catch{}
  // 차별점 인용(quotes.json)에는 XPath가 없다: 원문에서 유일하면 확정, 여러 곳이면 앞 문맥(context_before)으로 특정, 그래도 안 되면 후보만 넘겨 본다(확정 아님).
  let r,how='XPath·인용 일치';
  if(loc){r=pickMatch(matches,loc)}
  else if(matches.length===1){r={status:'ok',match:matches[0]};how='원문에서 유일'}
  else if(matches.length>1&&ctx){
    const probe=(ctx.slice(-12)+quote.slice(0,12)).replace(/\s+/g,' ');let cm=[];try{cm=safeJson(doc.searchAllText(probe,false,true))||[]}catch{}
    const same=(a,b)=>a.sec===b.sec&&a.para===b.para&&JSON.stringify(a.cellContext||null)===JSON.stringify(b.cellContext||null);
    const hit=cm.length===1?matches.find(m=>same(m,cm[0])):null;
    r=hit?{status:'ok',match:hit}:{status:'ambiguous',reason:`원문에 ${matches.length}곳 — 앞 문맥으로도 특정되지 않음(후보를 ↑↓로 넘겨 보기, 확정 아님)`};how='앞 문맥으로 특정'}
  else r={status:'unlocatable',reason:matches.length?`원문에 ${matches.length}곳 — 특정 불가(후보를 ↑↓로 넘겨 보기, 확정 아님)`:'원문에서 인용 문자열을 찾지 못함'};
  if(r.status!=='ok'){
    if(matches.length>1){searchQuery=searchKey(quote);searchResults=matches.map(m=>({page:pageOfMatch(doc,m),match:m})).filter(x=>x.page!=null);searchIndex=searchResults.length?0:-1;if(searchResults.length){page=searchResults[0].page}updateSearchCount();render()}
    report('위치 확인 불가 — '+r.reason);return}
  const pg=pageOfMatch(doc,r.match);
  if(pg==null){report('위치 확인 불가 — 인용이 그려진 쪽을 찾지 못함');return}
  searchQuery=searchKey(quote);searchResults=[{page:pg,match:r.match}];searchIndex=0;page=pg;
  updateSearchCount();render();report(`${pg+1}쪽 · ${how}`);
  requestAnimationFrame(()=>$('native-page').querySelector('.search-highlight')?.scrollIntoView({block:'center'}));
});
// The classic script may finish loading cases before this module is evaluated.
if(location.hash.slice(1)&&$('excel').textContent){openCase({row:location.hash.slice(1),name:$('excel').textContent})}
