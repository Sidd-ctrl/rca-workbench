"""AIVOA RCA API. AI suggestions are explicitly non-determinative; QA remains accountable."""
from __future__ import annotations
import json, os, re
from datetime import datetime, timezone
from typing import Any, TypedDict
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, DateTime, JSON, Text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL=os.getenv('DATABASE_URL','sqlite:///./backend/aivoa_rca.db')
engine=create_engine(DATABASE_URL,connect_args={'check_same_thread':False} if DATABASE_URL.startswith('sqlite') else {},pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False)
Base=declarative_base()
class Investigation(Base):
    __tablename__='investigations'
    id=Column(String,primary_key=True); title=Column(String,nullable=False); status=Column(String,default='Draft'); severity=Column(String,default='Major'); product=Column(String); batch=Column(String); detected=Column(String); department=Column(String); description=Column(Text); source_text=Column(Text); payload=Column(JSON); updated_at=Column(DateTime,default=lambda:datetime.now(timezone.utc))
Base.metadata.create_all(engine)
app=FastAPI(title='AIVOA RCA API',version='1.0.0',description='Evidence-led deviation investigation and RCA assistance')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
class TextRequest(BaseModel):
    text:str; filename:str|None=None
class RcaRequest(BaseModel):
    investigation:dict[str,Any]
class SaveRequest(BaseModel):
    id:str; title:str=''; status:str='Draft'; severity:str='Major'; product:str=''; batch:str=''; detected:str=''; department:str=''; description:str=''; source_text:str=''; payload:dict[str,Any]|None=None

class RCAState(TypedDict, total=False): text:str; investigation:dict; extracted:dict; analysis:dict; error:str

def local_extract(text:str)->dict:
    """Conservative no-key fallback; never asserts an unsubstantiated cause."""
    def match(pattern,default=''):
        m=re.search(pattern,text,re.I|re.M);return m.group(1).strip() if m else default
    lower=text.lower()
    batch=match(r'(?:batch|lot)(?:\s*(?:number|no\.?|id))?\s*[:#-]?\s*([A-Z0-9-]{4,})','AX-24091')
    product=match(r'(?:product|material)\s*[:#-]?\s*([^\n,;]+)','Metformin Hydrochloride API')
    return {'title':'Impurity OOS — API lot '+batch if ('oos' in lower or 'impurity' in lower) else 'Deviation investigation — '+batch,'severity':'Major','product':product,'batch':batch,'detected':match(r'(?:detected|reported|opened)\s*(?:on)?\s*[:#-]?\s*([\w ,/-]{6,30})','29 Oct 2026'),'department':match(r'department\s*[:#-]?\s*([^\n,;]+)','Quality Control'),'description':'An out-of-specification or quality event was reported. Verify the event description, result, specification, and source record before finalizing this intake.','eventDate':'','impact':'Assess affected batch, related batches, release/distribution status, patient impact, and regulatory obligations.','containment':'Place potentially affected material on QA hold as appropriate; preserve original records and notify QA. Verify actual actions and status.','evidence':['Supplied incident narrative received for review.'],'missing':['Original source report and raw data / audit trail','Applicable specification, method and OOS procedure','Analyst / operator interview and contemporaneous records','Batch record, related-lot review and product impact assessment']}

def local_analysis(inv:dict)->dict:
    return {'hypothesis':'The information supplied is not sufficient to establish an assignable cause. Review plausible laboratory, equipment, material, process, and human-factor hypotheses against objective evidence; document why each is accepted or excluded.','cause':'Undetermined — investigation in progress. No root cause is confirmed by the information currently available.','evidence':inv.get('evidence',[]),'missing':inv.get('missing',[]),'whys':[{'q':'Why did the quality event occur?','a':'The source describes an event, but the underlying mechanism is not yet evidenced.'},{'q':'Why is the mechanism unknown?','a':'The primary records and investigation evidence have not yet been reviewed in this workflow.'},{'q':'What evidence can distinguish potential causes?','a':'Review contemporaneous source data, records, equipment status, materials, method/process parameters, and interviews.'},{'q':'Why might the control system not have prevented or detected it?','a':'Assess relevant controls only after the causal pathway is supported by evidence.'},{'q':'What is the defensible conclusion now?','a':'Cause remains undetermined; avoid assigning blame or treating an untested hypothesis as fact.'}],'capa':[{'type':'Correction','action':'Contain affected material and preserve relevant records; verify material status and document product-impact assessment.','owner':'QA / Material Control','due':'Immediate','why':'Protects patients and prevents unintended use or release while facts are established.'},{'type':'Corrective','action':'Complete an evidence-based investigation under the current approved procedure; test and document plausible hypotheses, including objective raw-data review.','owner':'Investigation Lead','due':'Per approved SOP','why':'Determines whether a supported assignable cause exists and addresses it.'},{'type':'Preventive','action':'Use investigation findings and trend review to identify systemic improvements; implement only actions linked to a verified cause or substantiated risk.','owner':'QA + Process Owner','due':'Risk-based','why':'Avoids generic actions and targets demonstrated recurrence risk.'},{'type':'Effectiveness','action':'Define an effectiveness check with measurable acceptance criteria, sample / time window, owner, and QA approval before implementation.','owner':'QA Compliance','due':'After implementation','why':'Confirms the action addressed the underlying risk.'}]}

def make_llm():
    key=os.getenv('GROQ_API_KEY')
    if not key:return None
    try:
        from langchain_groq import ChatGroq
        return ChatGroq(model=os.getenv('GROQ_MODEL','llama-3.3-70b-versatile'),api_key=key,temperature=0.1)
    except Exception: return None

def parse_json(content:Any)->dict:
    raw=content if isinstance(content,str) else str(content)
    raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip(),flags=re.I)
    try:return json.loads(raw)
    except Exception:
        m=re.search(r'\{.*\}',raw,re.S)
        if m:
            try:return json.loads(m.group(0))
            except Exception:pass
        raise ValueError('Model response was not valid JSON')

def extraction_node(state:RCAState)->RCAState:
    fallback=local_extract(state['text'])
    llm=make_llm()
    if not llm:return {'extracted':fallback}
    prompt=f'''Extract factual incident intake data from this pharmaceutical API manufacturing deviation. Do not invent facts. Return ONLY JSON with keys title,severity,product,batch,detected,department,description,eventDate,impact,containment,evidence,missing. Use empty strings/lists for absent facts. Keep evidence as statements actually supported by source. Missing should list important records to obtain, tailored to event. Preserve uncertainty.\nSOURCE:\n{state['text'][:14000]}'''
    try:
        result=parse_json(llm.invoke(prompt).content)
        return {'extracted':{**fallback,**result}}
    except Exception as e:
        return {'extracted':fallback,'error':f'AI extraction fallback: {type(e).__name__}'}

def analysis_node(state:RCAState)->RCAState:
    inv=state.get('investigation',{});fallback=local_analysis(inv);llm=make_llm()
    if not llm:return {'analysis':fallback}
    prompt=f'''You are assisting a qualified pharmaceutical API quality investigator. Analyze only the provided record. Return ONLY JSON keys hypothesis,cause,evidence,missing,whys,capa. whys is exactly five objects {{q,a}}. capa is an array of 3-5 objects {{type,action,owner,due,why}} including an effectiveness check. Label unsupported cause as undetermined; never invent confirmatory evidence, assign blame, recommend invalid retesting, or imply AI replaces QA. For OOS, recommend approved SOP, raw data/audit trail review and scientifically justified investigation. CAPAs must be risk-based, measurable where possible, and distinguished correction/corrective/preventive/effectiveness.\nINVESTIGATION:\n{json.dumps(inv,ensure_ascii=False)[:16000]}'''
    try:
        result=parse_json(llm.invoke(prompt).content)
        merged={**fallback,**result}
        # fail safely if the model omits safeguards or expected structures
        if not isinstance(merged.get('whys'),list) or not merged['whys']:merged['whys']=fallback['whys']
        if not isinstance(merged.get('capa'),list) or not merged['capa']:merged['capa']=fallback['capa']
        if not isinstance(merged.get('missing'),list):merged['missing']=fallback['missing']
        return {'analysis':merged}
    except Exception as e:return {'analysis':fallback,'error':f'AI analysis fallback: {type(e).__name__}'}

# LangGraph composes intake and evidence-led analysis; each operation is callable independently.
def build_graph():
    try:
        from langgraph.graph import StateGraph,START,END
        g=StateGraph(RCAState);g.add_node('extract',extraction_node);g.add_node('analyze',analysis_node)
        g.add_edge(START,'extract');g.add_edge('extract','analyze');g.add_edge('analyze',END);return g.compile()
    except Exception:return None
GRAPH=build_graph()
@app.get('/api/health')
def health():return {'status':'ok','ai_configured':bool(os.getenv('GROQ_API_KEY')),'database':DATABASE_URL.split(':',1)[0],'workflow':'LangGraph' if GRAPH else 'safe local fallback'}
@app.post('/api/extract')
def extract(req:TextRequest):
    if not req.text.strip():raise HTTPException(400,'Source text is required')
    state={'text':req.text}
    if GRAPH:
        result=GRAPH.invoke(state);data=result.get('extracted',local_extract(req.text))
    else:data=extraction_node(state).get('extracted')
    return {'extracted':data,'filename':req.filename,'review_required':True,'source_text':req.text}
@app.post('/api/rca')
def rca(req:RcaRequest):
    inv=req.investigation
    if GRAPH:
        # Workflow intake node also runs for reproducibility; analysis consumes reviewed, user-edited form fields.
        result=GRAPH.invoke({'text':inv.get('description',''),'investigation':inv});analysis=result.get('analysis',local_analysis(inv))
    else:analysis=analysis_node({'investigation':inv}).get('analysis')
    return {'analysis':analysis,'review_required':True,'model':os.getenv('GROQ_MODEL','llama-3.3-70b-versatile') if os.getenv('GROQ_API_KEY') else 'local evidence-safe fallback'}
@app.post('/api/extract-file')
async def extract_file(file:UploadFile=File(...)):
    name=(file.filename or '').lower();raw=await file.read()
    if len(raw)>20*1024*1024:raise HTTPException(413,'Maximum file size is 20 MB')
    try:
        if name.endswith('.pdf'):
            from pypdf import PdfReader
            import io
            text='\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(raw)).pages)
        elif name.endswith('.docx'):
            from docx import Document
            import io
            text='\n'.join(p.text for p in Document(io.BytesIO(raw)).paragraphs)
        elif name.endswith(('.txt','.eml')):text=raw.decode('utf-8-sig',errors='replace')
        else:raise HTTPException(415,'Supported formats: PDF, DOCX, TXT, EML')
    except HTTPException:raise
    except Exception as e:raise HTTPException(422,f'Unable to read document: {e}')
    if not text.strip():raise HTTPException(422,'No text extracted. Scanned PDFs require OCR before upload.')
    result=extract(TextRequest(text=text,filename=file.filename));result['source_text']=text;return result
@app.post('/api/investigations')
def save(req:SaveRequest):
    db=SessionLocal()
    try:
        row=db.get(Investigation,req.id)
        values=req.model_dump();values['payload']=values.get('payload') or values
        if row:
            for k,v in values.items():setattr(row,k,v)
            row.updated_at=datetime.now(timezone.utc)
        else:row=Investigation(**values);db.add(row)
        db.commit();return {'saved':True,'id':row.id,'updated_at':row.updated_at.isoformat()}
    except Exception as e:db.rollback();raise HTTPException(500,f'Unable to save investigation: {e}')
    finally:db.close()
@app.get('/api/investigations')
def list_investigations():
    db=SessionLocal()
    try:
        rows=db.query(Investigation).order_by(Investigation.updated_at.desc()).limit(100).all()
        return [{'id':r.id,'title':r.title,'status':r.status,'severity':r.severity,'product':r.product,'batch':r.batch,'detected':r.detected,'department':r.department,'description':r.description,'payload':r.payload,'updated_at':r.updated_at.isoformat() if r.updated_at else None} for r in rows]
    finally:db.close()
@app.get('/')
def root():return {'service':'AIVOA RCA API','docs':'/docs'}
