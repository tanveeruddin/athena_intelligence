"""
Skills for the Scraper Agent.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
import asyncio
import httpx
import fitz  # PyMuPDF

from models.database import get_db_session
from models.orm_models import Announcement
from models.schemas import ScraperInput, ScraperOutput, ScrapedAnnouncement
from utils.config import get_settings
from utils.logging import get_logger
from utils.playwright_scraper import ASXPlaywrightScraper
from utils.db_logger import log_to_db

logger = get_logger()
settings = get_settings()

async def scrape_asx_announcements(input_data: ScraperInput) -> ScraperOutput:
    """
    Scrapes ASX announcements for a specific company using Playwright (JavaScript-rendered pages).

    Args:
        input_data: The input parameters for the scraper skill (includes asx_code).

    Returns:
        The output of the scraper skill.
    """
    task_id = input_data.task_id
    log_to_db(task_id, "scraper", f"Executing scrape_asx_announcements skill with input: {input_data}")
    logger.info(f"Executing scrape_asx_announcements skill with input: {input_data}")
    asx_code = input_data.asx_code.upper()

    # Use config default if limit not specified
    limit = input_data.limit if input_data.limit is not None else settings.max_announcements_per_company

    # Scrape using Playwright (handles JavaScript-rendered content)
    try:
        log_to_db(task_id, "scraper", f"Starting Playwright scraper for {asx_code}...")
        logger.info(f"Starting Playwright scraper for {asx_code}...")
        async with ASXPlaywrightScraper() as scraper:
            # Fetch more than needed to account for duplicates and filtering
            # When filtering by price-sensitive, fetch 10x (since only ~10-20% are price-sensitive)
            # Otherwise fetch 3x to account for duplicates
            if input_data.price_sensitive_only:
                fetch_limit = (limit * 10) if limit else 50
                log_to_db(task_id, "scraper", f"Fetching {fetch_limit} announcements (10x limit) for price-sensitive filtering")
                logger.info(f"Fetching {fetch_limit} announcements (10x limit) for price-sensitive filtering")
            else:
                fetch_limit = (limit * 3) if limit else 20
                log_to_db(task_id, "scraper", f"Fetching {fetch_limit} announcements (3x limit)")
                logger.info(f"Fetching {fetch_limit} announcements (3x limit)")

            all_announcements = await scraper.scrape_company_announcements(
                asx_code=asx_code,
                max_announcements=fetch_limit
            )
            log_to_db(task_id, "scraper", f"Playwright scraper returned {len(all_announcements) if all_announcements else 0} announcements")
            logger.info(f"Playwright scraper returned {len(all_announcements) if all_announcements else 0} announcements")
    except Exception as e:
        log_to_db(task_id, "scraper", f"Error during scraping for {asx_code}: {e}")
        logger.error(f"Error during scraping for {asx_code}: {e}", exc_info=True)
        return ScraperOutput(announcements=[], total_scraped=0, new_count=0)

    if not all_announcements:
        log_to_db(task_id, "scraper", f"No announcements retrieved for ASX code: {asx_code}")
        logger.warning(f"No announcements retrieved for ASX code: {asx_code}")
        return ScraperOutput(announcements=[], total_scraped=0, new_count=0)

    log_to_db(task_id, "scraper", f"Scraped {len(all_announcements)} announcements from ASX for {asx_code}")
    logger.info(f"Scraped {len(all_announcements)} announcements from ASX for {asx_code}")

    # Filter by price sensitivity
    if input_data.price_sensitive_only:
        announcements = [ann for ann in all_announcements if ann['is_price_sensitive']]
        log_to_db(task_id, "scraper", f"Filtered to {len(announcements)} price-sensitive announcements")
        logger.info(f"Filtered to {len(announcements)} price-sensitive announcements")
    else:
        announcements = all_announcements

    # Filter out duplicates (already in database)
    new_announcements = await _filter_duplicates(announcements, task_id)
    log_to_db(task_id, "scraper", f"Found {len(new_announcements)} new announcements (not in DB)")
    logger.info(f"Found {len(new_announcements)} new announcements (not in DB)")

    # Apply limit
    if limit:
        new_announcements = new_announcements[:limit]
        log_to_db(task_id, "scraper", f"Limited to {limit} announcements")
        logger.info(f"Limited to {limit} announcements")

    # Process each new announcement: download PDF and convert to markdown
    processed_announcements = []
    for ann in new_announcements:
        try:
            # Create announcement record in database to get announcement_id
            announcement_id = await _create_announcement_record(ann, asx_code, task_id)

            # Download PDF and convert to markdown
            await _process_pdf_and_markdown(announcement_id, ann['pdf_url'], task_id)

            # Add announcement_id to the announcement data
            ann['announcement_id'] = announcement_id
            processed_announcements.append(ann)

        except Exception as e:
            log_to_db(task_id, "scraper", f"Error processing announcement {ann.get('title', 'Unknown')}: {e}")
            logger.error(f"Error processing announcement {ann.get('title', 'Unknown')}: {e}", exc_info=True)
            # Continue with other announcements even if one fails

    return ScraperOutput(
        announcements=[ScrapedAnnouncement(**ann) for ann in processed_announcements],
        total_scraped=len(all_announcements),
        new_count=len(processed_announcements),
    )

# NOTE: The following functions are deprecated and no longer used.
# Scraping is now handled by Playwright (utils/playwright_scraper.py)
# to properly handle JavaScript-rendered content and bypass bot detection.
#
# Old httpx-based approach returned 403 Forbidden due to ASX bot protection.
# Keeping this code for reference only.

async def _filter_duplicates(announcements: List[Dict[str, Any]], task_id: str) -> List[Dict[str, Any]]:
    """Filters out announcements that already exist in the database."""
    new_announcements = []
    with get_db_session() as db:
        for ann in announcements:
            existing = db.query(Announcement).filter(
                Announcement.asx_code == ann['asx_code'],
                Announcement.title == ann['title'],
                Announcement.announcement_date == ann['announcement_date'],
            ).first()
            if not existing:
                new_announcements.append(ann)
    return new_announcements


async def _create_announcement_record(ann: Dict[str, Any], asx_code: str, task_id: str) -> str:
    """Create announcement record in database and return announcement_id."""
    from models.orm_models import Company

    with get_db_session() as db:
        # Get or create company
        company = db.query(Company).filter(Company.asx_code == asx_code).first()
        if not company:
            log_to_db(task_id, "scraper", f"Creating new company record for {asx_code}")
            logger.info(f"Creating new company record for {asx_code}")
            company = Company(
                asx_code=asx_code,
                company_name=ann.get("company_name", f"{asx_code} Company"),
                industry="Unknown"
            )
            db.add(company)
            db.commit()
            db.refresh(company)

        # Create announcement record
        announcement = Announcement(
            company_id=company.id,
            asx_code=asx_code,
            title=ann["title"],
            announcement_date=ann["announcement_date"],
            pdf_url=ann["pdf_url"],
            is_price_sensitive=ann.get("is_price_sensitive", False)
        )
        db.add(announcement)
        db.commit()
        db.refresh(announcement)
        log_to_db(task_id, "scraper", f"Created announcement record: {announcement.id}")
        logger.info(f"Created announcement record: {announcement.id}")
        return announcement.id


async def _process_pdf_and_markdown(announcement_id: str, pdf_url: str, task_id: str):
    """Download PDF, convert to markdown, and update announcement record."""
    # Get paths
    pdf_path = _get_pdf_path(announcement_id)
    markdown_path = _get_markdown_path(announcement_id)

    # Download PDF
    await _download_pdf(pdf_url, pdf_path, task_id)

    # Convert to markdown
    markdown_content, num_pages = _pdf_to_markdown(pdf_path, task_id)

    # Save markdown
    _save_markdown(markdown_content, markdown_path, task_id)

    # Update announcement record
    file_size_kb = pdf_path.stat().st_size // 1024
    await _update_announcement_record(announcement_id, str(pdf_path), str(markdown_path), num_pages, file_size_kb, task_id)

    log_to_db(task_id, "scraper", f"Processed PDF and markdown for announcement {announcement_id}")
    logger.info(f"Processed PDF and markdown for announcement {announcement_id}")


def _get_pdf_path(announcement_id: str) -> Path:
    """Get path for PDF file."""
    pdf_dir = Path(settings.pdf_storage_path)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    return pdf_dir / f"{announcement_id}.pdf"


def _get_markdown_path(announcement_id: str) -> Path:
    """Get path for markdown file."""
    markdown_dir = Path(settings.markdown_storage_path)
    markdown_dir.mkdir(parents=True, exist_ok=True)
    return markdown_dir / f"{announcement_id}.md"


async def _download_pdf(pdf_url: str, output_path: Path, task_id: str):
    """Download PDF from URL."""
    if output_path.exists():
        log_to_db(task_id, "scraper", f"PDF already exists, skipping download: {output_path}")
        logger.info(f"PDF already exists, skipping download: {output_path}")
        return
    log_to_db(task_id, "scraper", f"Downloading PDF from: {pdf_url}")
    logger.info(f"Downloading PDF from: {pdf_url}")
    async with httpx.AsyncClient() as client:
        response = await client.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
    output_path.write_bytes(response.content)
    log_to_db(task_id, "scraper", f"Downloaded PDF to: {output_path}")
    logger.info(f"Downloaded PDF to: {output_path}")


def _pdf_to_markdown(pdf_path: Path, task_id: str) -> Tuple[str, int]:
    """Convert PDF to markdown text."""
    log_to_db(task_id, "scraper", f"Converting PDF to markdown: {pdf_path}")
    logger.info(f"Converting PDF to markdown: {pdf_path}")
    doc = fitz.open(pdf_path)
    markdown_content = "\n".join(page.get_text() for page in doc)
    num_pages = len(doc)
    doc.close()
    log_to_db(task_id, "scraper", f"Converted {num_pages} pages to {len(markdown_content)} chars of markdown.")
    logger.info(f"Converted {num_pages} pages to {len(markdown_content)} chars of markdown.")
    return markdown_content, num_pages


def _save_markdown(content: str, path: Path, task_id: str):
    """Save markdown content to file."""
    path.write_text(content, encoding='utf-8')
    log_to_db(task_id, "scraper", f"Saved markdown file: {path}")
    logger.info(f"Saved markdown file: {path}")


async def _update_announcement_record(ann_id: str, pdf_path: str, md_path: str, pages: int, size: int, task_id: str):
    """Update announcement record with PDF metadata."""
    with get_db_session() as db:
        announcement = db.query(Announcement).filter(Announcement.id == ann_id).first()
        if announcement:
            announcement.pdf_local_path = pdf_path
            announcement.markdown_path = md_path
            announcement.num_pages = pages
            announcement.file_size_kb = size
            db.commit()
            log_to_db(task_id, "scraper", f"Updated announcement record with PDF metadata: {ann_id}")
            logger.info(f"Updated announcement record with PDF metadata: {ann_id}")
