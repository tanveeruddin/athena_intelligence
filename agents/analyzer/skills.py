"""
Skills for the Analyzer Agent.
"""

import json
import time
import httpx
import fitz  # PyMuPDF
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Import both old and new genai packages
import google.generativeai as genai_old
from google.generativeai.generative_models import GenerativeModel
from google import genai  # New genai package for File API
from google.genai import types

from models.database import get_db_session
from models.orm_models import Analysis, Announcement
from models.schemas import AnalyzerInput, AnalyzerOutput, AnalysisResponse
from utils.config import get_settings
from utils.logging import get_logger
from utils.prompts import (
    ANNOUNCEMENT_ANALYSIS_SYSTEM_PROMPT,
    get_announcement_analysis_prompt,
    truncate_content,
    format_json_response
)
from utils.db_logger import log_to_db

logger = get_logger()
settings = get_settings()

# Configure and initialize the Gemini models
# Initialize both old and new genai clients
try:
    if settings.gemini_api_key:
        # Old genai for backwards compatibility
        genai_old.configure(api_key=settings.gemini_api_key)
        gemini_model = genai_old.GenerativeModel(
            model_name=settings.gemini_model,
            generation_config={
                "temperature": settings.gemini_temperature,
                "max_output_tokens": settings.gemini_max_tokens,
            }
        )

        # New genai client for File API (preferred method)
        genai_client = genai.Client(api_key=settings.gemini_api_key)
    else:
        gemini_model = None
        genai_client = None
        logger.warning("GEMINI_API_KEY not set - LLM analyzer will not function.")
except Exception as e:
    gemini_model = None
    genai_client = None
    logger.error(f"Failed to initialize Gemini model: {e}")


async def process_and_analyze_announcement(input_data: AnalyzerInput) -> AnalyzerOutput:
    """
    Analyzes announcement content using an LLM by reading pre-downloaded markdown.

    Checks database first to avoid reprocessing - if analysis exists, returns cached result.
    The scraper agent has already downloaded the PDF and converted it to markdown.

    Args:
        input_data: The input parameters for the analyzer skill (announcement_id).

    Returns:
        The output of the analyzer skill, including paths and analysis results.
    """
    task_id = input_data.task_id
    log_to_db(task_id, "analyzer", f"Starting analysis for announcement_id: {input_data.announcement_id}")
    logger.info(f"Starting analysis for announcement_id: {input_data.announcement_id}")

    # --- Check if already analyzed ---
    existing_analysis = _check_existing_analysis(input_data.announcement_id)
    if existing_analysis:
        log_to_db(task_id, "analyzer", f"✅ Analysis already exists for {input_data.announcement_id}. Returning cached result.")
        logger.info(f"✅ Analysis already exists for {input_data.announcement_id}. Returning cached result.")
        return existing_analysis

    log_to_db(task_id, "analyzer", f"📄 No existing analysis found. Reading markdown and generating new analysis...")
    logger.info(f"📄 No existing analysis found. Reading markdown and generating new analysis...")

    # --- Get paths and metadata from announcement record ---
    with get_db_session() as db:
        announcement = db.query(Announcement).filter(Announcement.id == input_data.announcement_id).first()
        if not announcement:
            raise ValueError(f"Announcement {input_data.announcement_id} not found in database")

        if not announcement.pdf_local_path:
            raise ValueError(f"Announcement {input_data.announcement_id} missing PDF path - scraper should have created it")

        pdf_path = Path(announcement.pdf_local_path)
        markdown_path = Path(announcement.markdown_path) if announcement.markdown_path else None
        num_pages = announcement.num_pages or 0
        file_size_kb = announcement.file_size_kb or 0
        asx_code = announcement.asx_code

        # Get company name
        from models.orm_models import Company
        company = db.query(Company).filter(Company.id == announcement.company_id).first()
        company_name = company.company_name if company else f"{asx_code} Company"

    # --- Verify PDF exists ---
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # --- LLM Analysis Logic using Gemini File API ---
    if not genai_client:
        raise RuntimeError("Gemini client not initialized. Cannot perform analysis.")

    log_to_db(task_id, "analyzer", f"📤 Uploading PDF to Gemini File API: {pdf_path}")
    logger.info(f"📤 Uploading PDF to Gemini File API: {pdf_path}")

    start_time = time.time()

    # Upload PDF using File API
    try:
        uploaded_file = genai_client.files.upload(file=pdf_path)
        log_to_db(task_id, "analyzer", f"✅ PDF uploaded successfully. File URI: {uploaded_file.uri}")
        logger.info(f"✅ PDF uploaded successfully. File URI: {uploaded_file.uri}")
    except Exception as e:
        log_to_db(task_id, "analyzer", f"❌ Failed to upload PDF: {e}")
        logger.error(f"❌ Failed to upload PDF: {e}")
        raise

    # Create analysis prompt
    prompt = get_announcement_analysis_prompt(
        markdown_content="",  # Not using markdown anymore
        company_name=company_name,
        asx_code=asx_code,
    )

    # Generate content using uploaded PDF
    log_to_db(task_id, "analyzer", "🤖 Calling Gemini API with uploaded PDF...")
    logger.info("🤖 Calling Gemini API with uploaded PDF...")

    try:
        response = genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[uploaded_file, prompt]
        )
        response_text = response.text
        log_to_db(task_id, "analyzer", f"✅ Received response ({len(response_text)} chars)")
        logger.info(f"✅ Received response ({len(response_text)} chars)")
    except Exception as e:
        log_to_db(task_id, "analyzer", f"❌ Gemini API call failed: {e}")
        logger.error(f"❌ Gemini API call failed: {e}")
        raise
    finally:
        # Clean up uploaded file
        try:
            genai_client.files.delete(name=uploaded_file.name)
            log_to_db(task_id, "analyzer", f"🗑️  Deleted uploaded file: {uploaded_file.name}")
            logger.info(f"🗑️  Deleted uploaded file: {uploaded_file.name}")
        except Exception as e:
            logger.warning(f"Failed to delete uploaded file: {e}")

    processing_time_ms = int((time.time() - start_time) * 1000)

    analysis_data = _parse_analysis_response(response_text, task_id)
    tokens_used = (len(prompt) + len(response_text)) // 4
    
    log_to_db(task_id, "analyzer", "Creating analysis record in database...")
    analysis_record = await _create_analysis_record(
        announcement_id=input_data.announcement_id,
        analysis_data=analysis_data,
        processing_time_ms=processing_time_ms,
        tokens_used=tokens_used,
        task_id=task_id
    )

    return AnalyzerOutput(
        announcement_id=input_data.announcement_id,
        pdf_path=str(pdf_path),
        markdown_path=str(markdown_path) if markdown_path else "",
        num_pages=num_pages,
        file_size_kb=file_size_kb,
        analysis=AnalysisResponse.from_orm(analysis_record),
    )


# --- PDF Processing Helpers ---

def _get_pdf_path(announcement_id: str) -> Path:
    pdf_dir = Path(settings.pdf_storage_path)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    return pdf_dir / f"{announcement_id}.pdf"

def _get_markdown_path(announcement_id: str) -> Path:
    markdown_dir = Path(settings.markdown_storage_path)
    markdown_dir.mkdir(parents=True, exist_ok=True)
    return markdown_dir / f"{announcement_id}.md"

async def _download_pdf(pdf_url: str, output_path: Path):
    if output_path.exists():
        logger.info(f"PDF already exists, skipping download: {output_path}")
        return
    logger.info(f"Downloading PDF from: {pdf_url}")
    async with httpx.AsyncClient() as client:
        response = await client.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
    output_path.write_bytes(response.content)
    logger.info(f"Downloaded PDF to: {output_path}")

def _pdf_to_markdown(pdf_path: Path) -> Tuple[str, int]:
    logger.info(f"Converting PDF to markdown: {pdf_path}")
    doc = fitz.open(pdf_path)
    markdown_content = "\n".join(page.get_text() for page in doc)
    num_pages = len(doc)
    doc.close()
    logger.info(f"Converted {num_pages} pages to {len(markdown_content)} chars of markdown.")
    return markdown_content, num_pages

def _save_markdown(content: str, path: Path):
    path.write_text(content, encoding='utf-8')
    logger.info(f"Saved markdown file: {path}")

async def _update_announcement_record(ann_id: str, pdf_path: str, md_path: str, pages: int, size: int):
    with get_db_session() as db:
        announcement = db.query(Announcement).filter(Announcement.id == ann_id).first()
        if announcement:
            announcement.pdf_local_path = pdf_path
            announcement.markdown_path = md_path
            announcement.num_pages = pages
            announcement.file_size_kb = size
            db.commit()
            logger.info(f"Updated announcement record with PDF metadata: {ann_id}")

# --- LLM Analysis Helpers ---

async def _call_gemini(model: GenerativeModel, prompt: str, task_id: str) -> str:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            full_prompt = f"{ANNOUNCEMENT_ANALYSIS_SYSTEM_PROMPT}\n\n{prompt}"
            response = await model.generate_content_async(full_prompt)
            return response.text
        except Exception as e:
            log_to_db(task_id, "analyzer", f"Gemini API call attempt {attempt + 1} failed: {e}")
            logger.warning(f"Gemini API call attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                raise

def _parse_analysis_response(response_text: str, task_id: str) -> Dict[str, Any]:
    try:
        cleaned = format_json_response(response_text)
        data = json.loads(cleaned)
        required = ["summary", "sentiment", "key_insights"]
        if not all(k in data for k in required):
            raise ValueError(f"Missing one of required fields: {required}")
        if data["sentiment"] not in ["BULLISH", "BEARISH", "NEUTRAL"]:
            data["sentiment"] = "NEUTRAL"
        return data
    except (json.JSONDecodeError, ValueError) as e:
        log_to_db(task_id, "analyzer", f"Failed to parse LLM JSON response: {e}")
        logger.error(f"Failed to parse LLM JSON response: {e}")
        return {
            "summary": "Error: Failed to parse LLM response.",
            "sentiment": "NEUTRAL",
            "key_insights": [],
            "management_promises": [],
            "financial_impact": "Unknown",
        }

async def _create_analysis_record(announcement_id: str, analysis_data: Dict[str, Any], processing_time_ms: int, tokens_used: int, task_id: str) -> Analysis:
    with get_db_session() as db:
        # Convert lists to JSON strings for SQLite storage
        key_insights = analysis_data.get("key_insights", [])
        management_promises = analysis_data.get("management_promises", [])

        analysis = Analysis(
            announcement_id=announcement_id,
            summary=analysis_data.get("summary"),
            sentiment=analysis_data.get("sentiment"),
            key_insights=json.dumps(key_insights) if isinstance(key_insights, list) else key_insights,
            management_promises=json.dumps(management_promises) if isinstance(management_promises, list) else management_promises,
            financial_impact=analysis_data.get("financial_impact"),
            llm_model=settings.gemini_model,
            processing_time_ms=processing_time_ms,
            tokens_used=tokens_used,
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        log_to_db(task_id, "analyzer", f"Created analysis record: {analysis.id}")
        logger.info(f"Created analysis record: {analysis.id}")
        return analysis


def _check_existing_analysis(announcement_id: str) -> Optional[AnalyzerOutput]:
    """
    Check if analysis already exists for this announcement in the database.

    Args:
        announcement_id: The announcement ID to check

    Returns:
        AnalyzerOutput if analysis exists, None otherwise
    """
    with get_db_session() as db:
        # Check if Analysis record exists
        analysis = db.query(Analysis).filter(Analysis.announcement_id == announcement_id).first()

        if not analysis:
            return None

        # Analysis exists - get announcement metadata for paths
        announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()

        if not announcement:
            logger.warning(f"Analysis exists but announcement not found: {announcement_id}")
            return None

        # Construct output from existing data
        return AnalyzerOutput(
            announcement_id=announcement_id,
            pdf_path=announcement.pdf_local_path or "",
            markdown_path=announcement.markdown_path or "",
            num_pages=announcement.num_pages or 0,
            file_size_kb=announcement.file_size_kb or 0,
            analysis=AnalysisResponse.from_orm(analysis),
        )
