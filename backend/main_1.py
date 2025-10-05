from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pandas as pd
from rapidfuzz import process, fuzz
from deep_translator import GoogleTranslator
import itertools
from typing import List, Dict, Any
import os
import logging
from contextlib import asynccontextmanager
import re
from lxml import etree
import requests 
import json     

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Drug-Drug Interaction Checker API",
    description="API for checking drug interactions with English and Thai support",
    version="1.0.0",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_data()
    yield

app.router.lifespan_context = lifespan

df = None
drug_interactions_data = []
all_drugs_list = []
translation_cache = {}

# --- ฟังก์ชันที่เรียกใช้ Groq API ---

# !! วาง GROQ API KEY ของคุณที่นี่ !!
GROQ_API_KEY = "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" 

# URL ของ Groq API
API_URL = "https://api.groq.com/openai/v1/chat/completions"

async def get_ai_interaction_analysis(drug1: str, drug2: str, description_en: str) -> dict:
    cache_key = f"{drug1}-{drug2}-{description_en}"
    if cache_key in translation_cache:
        return translation_cache[cache_key]

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = (
        "คุณคือเภสัชกรผู้เชี่ยวชาญเกี่ยวกับปฏิกิริยาระหว่างยาที่มีหน้าที่ให้ข้อมูลที่ถูกต้องและปลอดภัยเท่านั้น "
        "งานของคุณคือวิเคราะห์ข้อมูลทางเทคนิคเกี่ยวกับปฏิกิริยาระหว่างยาแล้วตอบกลับเป็น JSON object เท่านั้น "
        "JSON object ต้องมี 2 keys: 'severity' และ 'explanation_th'. "
        "สำหรับ key 'severity' ให้ประเมินระดับความรุนแรงและเลือกค่าใดค่าหนึ่งจากลิสต์นี้เท่านั้น: ['Contraindicated', 'Major', 'Moderate', 'Minor']. "
        "สำหรับ key 'explanation_th' ให้แปลข้อมูลทางการแพทย์ที่เป็นศัพท์เทคนิคเป็นภาษาไทยทางการแพทย์ โดยเน้นที่กลไกและความอันตราย "
        "ให้ยึดตามข้อมูลทางเทคนิคที่ให้มาเท่านั้น ห้ามแต่งข้อมูลขึ้นมาเองเด็ดขาด"
    )
    
    user_prompt = (
        f"โปรดวิเคราะห์ปฏิกิริยาระหว่างยาต่อไปนี้:\nยา 1: {drug1}\nยา 2: {drug2}\nข้อมูลทางเทคนิค: {description_en}"
    )

    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 350,
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=data)
        response.raise_for_status()
            
        result = response.json()
        ai_response_str = result['choices'][0]['message']['content']

        # --- ส่วนที่แก้ไข ---
        # ค้นหาส่วนที่เป็น JSON object ในข้อความที่ AI ตอบกลับ
        # เผื่อกรณีที่ AI ตอบข้อความอื่นปนมาด้วย
        match = re.search(r'\{.*\}', ai_response_str, re.DOTALL)
        
        if not match:
            raise ValueError("No JSON object found in the AI response.")
        
        # ดึงเฉพาะส่วนที่เป็น JSON มาใช้งาน
        json_str = match.group(0)
        ai_data = json.loads(json_str)
        # --- จบส่วนที่แก้ไข ---
        
        if 'severity' not in ai_data or 'explanation_th' not in ai_data:
            raise ValueError("AI response is missing required keys.")

        translation_cache[cache_key] = ai_data
        return ai_data
        
    except Exception as e:
        return {
            "severity": "Minor",
            "explanation_th": f"(ไม่สามารถวิเคราะห์ข้อมูลจาก AI ได้: {str(e)})"
        }

# --- จบส่วนของ Groq ---


def get_all_drugs():
    return all_drugs_list

def parse_xml_drug_interactions(xml_file_path):
    global drug_interactions_data, all_drugs_list
    drug_interactions_data = []
    drugs_set = set()
    try:
        context = etree.iterparse(xml_file_path, events=('start', 'end'), tag='{http://www.drugbank.ca}drug')
        for event, drug_elem in context:
            if event == 'end':
                name_elem = drug_elem.find('.//{http://www.drugbank.ca}name')
                if name_elem is None or not name_elem.text: continue
                drug_name = name_elem.text.strip()
                drugs_set.add(drug_name.lower())
                interactions_elem = drug_elem.find('.//{http://www.drugbank.ca}drug-interactions')
                if interactions_elem is not None:
                    for interaction_elem in interactions_elem.findall('.//{http://www.drugbank.ca}drug-interaction'):
                        int_name_elem = interaction_elem.find('.//{http://www.drugbank.ca}name')
                        int_desc_elem = interaction_elem.find('.//{http://www.drugbank.ca}description')
                        if int_name_elem is not None and int_desc_elem is not None:
                            drug_interactions_data.append({
                                'Drug 1': drug_name,
                                'Drug 2': int_name_elem.text.strip(),
                                'Interaction Description': int_desc_elem.text.strip()
                            })
                drug_elem.clear()
        all_drugs_list = sorted(list(drugs_set))
    except Exception as e:
        logger.error(f"Error parsing XML: {e}")

severity_translations = {"Contraindicated": "ห้ามใช้ร่วมกัน", "Major": "รุนแรงมาก", "Moderate": "ปานกลาง", "Minor": "เล็กน้อย"}

def is_thai_text(text: str) -> bool:
    return bool(re.search(r'[\u0E00-\u0E7F]', text))

def translate_to_english(text: str) -> str:
    return GoogleTranslator(source='th', target='en').translate(text).lower().strip() if is_thai_text(text) else text.lower().strip()

def fuzzy_match_drug(drug_name: str, threshold: int = 80) -> str:
    if not drug_name: return drug_name
    all_drugs = get_all_drugs()
    if not all_drugs: return drug_name
    clean_drug = translate_to_english(drug_name)
    matches = process.extract(clean_drug, all_drugs, limit=1)
    return matches[0][0] if matches and matches[0][1] >= threshold else clean_drug

def normalize_drug_name(drug_name: str) -> str:
    return fuzzy_match_drug(drug_name)

class DrugListRequest(BaseModel): drugs: List[str]
class DrugSearchRequest(BaseModel): query: str

def load_data():
    global df
    xml_path = os.path.join(os.path.dirname(__file__), "..", "db", "full database.xml")
    if os.path.exists(xml_path):
        parse_xml_drug_interactions(xml_path)
        if drug_interactions_data:
            df = pd.DataFrame(drug_interactions_data)
    else:
        df = pd.DataFrame()

@app.get("/health")
async def health_check():
    return {"status": "healthy", "data_loaded": not df.empty if df is not None else False}

@app.post("/search_drugs/")
async def search_drugs(request: DrugSearchRequest):
    if not request.query: return {"drugs": []}
    matches = process.extract(request.query.lower(), all_drugs_list, limit=10)
    return {"drugs": [{"name": match[0]} for match in matches]}

@app.post("/check_interactions/")
async def check_interactions(request: DrugListRequest):
    if len(request.drugs) < 2:
        raise HTTPException(status_code=400, detail="At least 2 drugs are required")
    
    normalized_drugs = [normalize_drug_name(drug) for drug in request.drugs]
    interactions = []
    
    for drug1, drug2 in itertools.combinations(normalized_drugs, 2):
        interaction_row = df[((df["Drug 1"].str.lower() == drug1) & (df["Drug 2"].str.lower() == drug2)) | ((df["Drug 1"].str.lower() == drug2) & (df["Drug 1"].str.lower() == drug1))]
        if not interaction_row.empty:
            row = interaction_row.iloc[0]
            interaction_desc_en = row["Interaction Description"]
            
            ai_analysis = await get_ai_interaction_analysis(drug1, drug2, interaction_desc_en)
            
            severity = ai_analysis.get("severity", "Minor")
            description_th_ai = ai_analysis.get("explanation_th", "ไม่พบข้อมูล")

            interactions.append({
                "drug1": drug1, 
                "drug2": drug2, 
                "severity": severity,
                "severity_th": severity_translations.get(severity, severity),
                "description": interaction_desc_en, 
                "description_th": description_th_ai
            })
            
    return {"total_interactions": len(interactions), "interactions": interactions}

@app.get("/", response_class=FileResponse)
async def read_index():
    return os.path.join(os.path.dirname(__file__), "..", "static", "index.html")

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "static")), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)