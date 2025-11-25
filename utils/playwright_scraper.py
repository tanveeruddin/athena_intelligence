"""
Playwright-based scraper for ASX announcements.
Handles JavaScript-rendered pages and bot detection bypass.
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import re

from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()


class ASXPlaywrightScraper:
    """Scraper that uses Playwright to handle JavaScript-rendered ASX pages."""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.playwright = await async_playwright().start()
        # Use chromium for best compatibility
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',  # Hide automation
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def scrape_company_announcements(
        self,
        asx_code: str,
        max_announcements: int = 10,
        wait_timeout: int = 30000
    ) -> List[Dict[str, Any]]:
        """
        Scrape announcements for a specific ASX company.

        Args:
            asx_code: ASX ticker code (e.g., "CBA", "BHP")
            max_announcements: Maximum number of announcements to return
            wait_timeout: Timeout in milliseconds to wait for page load

        Returns:
            List of announcement dictionaries
        """
        if not self.browser:
            raise RuntimeError("Browser not initialized. Use 'async with' context manager.")

        url = settings.company_announcements_url_template.format(asx_code=asx_code)
        logger.info(f"Scraping announcements for {asx_code} from {url}")

        # Create new page
        page = await self.browser.new_page()

        try:
            # Set viewport and user agent to look more like a real browser
            await page.set_viewport_size({"width": 1920, "height": 1080})
            await page.set_extra_http_headers({
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            })

            # Navigate to the page
            logger.debug(f"Navigating to {url}")
            response = await page.goto(url, wait_until='networkidle', timeout=wait_timeout)

            if not response:
                logger.error(f"No response received for {asx_code}")
                return []

            if response.status >= 400:
                logger.error(f"HTTP {response.status} for {asx_code}")
                return []

            # Wait for the announcements section to be populated
            # The page uses JavaScript to load announcements into #markets_announcements
            logger.debug("Waiting for announcements to load...")

            try:
                # Wait for the announcements container to have content
                await page.wait_for_selector('#markets_announcements table', timeout=wait_timeout)

                # Give it a bit more time for all announcements to render
                await asyncio.sleep(2)

            except PlaywrightTimeoutError:
                logger.warning(f"Timeout waiting for announcements table for {asx_code}")
                # Try to continue anyway - maybe there are no announcements

            # Get the page content after JavaScript has rendered
            html_content = await page.content()

            # Debug: Save rendered HTML for inspection
            # debug_file = Path(f"debug_{asx_code.lower()}_rendered.html")
            # debug_file.write_text(html_content, encoding='utf-8')
            # logger.info(f"Saved rendered HTML to {debug_file}")

            # Parse announcements from the rendered HTML
            announcements = self._parse_announcements(html_content, asx_code)

            logger.info(f"Found {len(announcements)} announcements for {asx_code}")

            # Limit results
            return announcements[:max_announcements]

        except Exception as e:
            logger.error(f"Error scraping {asx_code}: {e}")
            return []

        finally:
            await page.close()

    def _parse_announcements(self, html_content: str, asx_code: str) -> List[Dict[str, Any]]:
        """
        Parse announcements from the JavaScript-rendered HTML.

        Args:
            html_content: HTML content after JavaScript rendering
            asx_code: ASX ticker code

        Returns:
            List of announcement dictionaries
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        announcements = []

        # Find the markets_announcements section
        announcements_section = soup.find('section', id='markets_announcements')

        if not announcements_section:
            logger.warning("No announcements section found")
            # Try alternative selectors
            announcements_section = soup.find('div', class_='markit-market-announcements')
            if not announcements_section:
                logger.warning("No alternative announcements section found either")
                return []

        # Find all tables in the announcements section
        tables = announcements_section.find_all('table')
        logger.debug(f"Found {len(tables)} tables in announcements section")

        # Also try to find table with DataTables class (common for dynamic tables)
        if not tables:
            tables = soup.find_all('table', class_=lambda x: x and 'datatable' in x.lower() if x else False)
            logger.debug(f"Found {len(tables)} DataTables tables")

        for table_idx, table in enumerate(tables):
            rows = table.find_all('tr')
            logger.debug(f"Table {table_idx}: {len(rows)} rows")

            # Check if first row is header
            header_row = rows[0] if rows else None
            start_idx = 1 if header_row and header_row.find_all('th') else 0

            for row_idx, row in enumerate(rows[start_idx:]):
                cells = row.find_all('td')

                if len(cells) < 3:  # Need at least 3 cells
                    continue

                try:
                    # Try to identify columns by content
                    # Look for date, price sensitive marker, PDF link, and title

                    # Find document link (PDF via API gateway or direct PDF link)
                    pdf_link = None
                    pdf_cell_idx = None
                    for idx, cell in enumerate(cells):
                        # Look for links to ASX documents (API gateway or PDF)
                        link = cell.find('a', href=lambda x: x and (
                            '.pdf' in x.lower() or
                            'markitdigital.com' in x.lower() or
                            'asx-research' in x.lower() or
                            '/file/' in x.lower()
                        ) if x else False)
                        if link:
                            pdf_link = link
                            pdf_cell_idx = idx
                            break

                    if not pdf_link:
                        logger.debug(f"Row {row_idx}: No PDF link found")
                        continue

                    pdf_href = pdf_link.get('href', '')

                    # Build full PDF URL
                    if pdf_href.startswith('http'):
                        # Already a full URL (e.g., API gateway)
                        pdf_url = pdf_href
                    elif pdf_href.startswith('/'):
                        # Relative path from root
                        pdf_url = f"https://www.asx.com.au{pdf_href}"
                    else:
                        # Relative path
                        pdf_url = f"https://www.asx.com.au/{pdf_href}"

                    # Remove any trailing &v=undefined from API URLs
                    pdf_url = pdf_url.replace('&v=undefined', '')

                    # Get title from link text or nearby cell
                    title = pdf_link.get_text(strip=True)
                    if not title and pdf_cell_idx is not None and pdf_cell_idx + 1 < len(cells):
                        title = cells[pdf_cell_idx + 1].get_text(strip=True)
                    if not title:
                        title = "Untitled"

                    # Clean title
                    title = re.sub(r'\s+', ' ', title).strip()
                    title = re.sub(r'\s*PDF\s*\d+\s*(KB|MB)\s*$', '', title, flags=re.IGNORECASE)
                    title = re.sub(r'\s*\d+\s*(KB|MB|pages?)\s*$', '', title, flags=re.IGNORECASE)

                    # Find date (usually first cell or cell before PDF)
                    date_cell = None
                    for idx in range(min(3, len(cells))):
                        cell_text = cells[idx].get_text(strip=True)
                        # Check if it looks like a date
                        if any(month in cell_text for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                                                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                            date_cell = cell_text
                            break

                    announcement_date = self._parse_date(date_cell) if date_cell else datetime.now()

                    # Find price sensitive indicator
                    # Price-sensitive announcements have: <td class="price-sensitive"><svg ...>
                    # Non price-sensitive have: <td class="price-sensitive"><span class="sr-only">no</span>
                    is_price_sensitive = False
                    for cell_idx, cell in enumerate(cells):
                        cell_classes = cell.get('class', [])

                        # Check if this is the price-sensitive column
                        if cell_classes and 'price-sensitive' in cell_classes:
                            # Check if it contains an SVG (price-sensitive) or just text "no" (not price-sensitive)
                            svg = cell.find('svg')
                            if svg:
                                # Has SVG icon = price-sensitive
                                is_price_sensitive = True
                                logger.debug(f"Row {row_idx}: Found price-sensitive SVG in cell {cell_idx}")
                                break
                            else:
                                # No SVG, check text content
                                cell_text = cell.get_text(strip=True).lower()
                                if cell_text == 'yes':
                                    is_price_sensitive = True
                                    logger.debug(f"Row {row_idx}: Found 'yes' in price-sensitive cell {cell_idx}")
                                    break
                                elif cell_text == 'no':
                                    # Explicitly not price-sensitive
                                    logger.debug(f"Row {row_idx}: Found 'no' in price-sensitive cell {cell_idx}")
                                    break

                    announcements.append({
                        'asx_code': asx_code,
                        'company_name': '',  # Not available in this table
                        'title': title,
                        'pdf_url': pdf_url,
                        'announcement_date': announcement_date,
                        'is_price_sensitive': is_price_sensitive,
                    })

                    logger.debug(f"Row {row_idx}: Parsed {title[:50]} | Price-sensitive: {is_price_sensitive}")

                except Exception as e:
                    logger.debug(f"Error parsing row {row_idx}: {e}")
                    continue

        return announcements

    def _parse_date(self, date_str: str) -> datetime:
        """
        Parse date string from ASX announcements.

        Args:
            date_str: Date string (e.g., "13 Nov 20252:03pm", "19/11/2025 9:52 AM")

        Returns:
            datetime object
        """
        if not date_str:
            return datetime.now()

        # Clean up the string
        date_str = date_str.strip()

        # Fix common issues in date strings
        # Handle "20252:03pm" -> "2025 2:03pm"
        date_str = re.sub(r'(\d{4})(\d{1,2}:\d{2})', r'\1 \2', date_str)

        # Normalize AM/PM
        date_str = date_str.replace('am', ' AM').replace('pm', ' PM')
        date_str = re.sub(r'\s+', ' ', date_str).strip()

        # Common formats
        formats = [
            "%d %b %Y %I:%M %p",  # 13 Nov 2025 2:03 PM
            "%d %b %Y %I:%M%p",   # 13 Nov 2025 2:03PM
            "%d/%m/%Y %I:%M %p",  # 19/11/2025 9:52 AM
            "%d/%m/%Y %H:%M",     # 19/11/2025 09:52
            "%d/%m/%Y",           # 19/11/2025
            "%Y-%m-%d %H:%M:%S",  # 2025-11-19 09:52:00
            "%Y-%m-%d %H:%M",     # 2025-11-19 09:52
            "%Y-%m-%d",           # 2025-11-19
            "%d %B %Y %I:%M %p",  # 13 November 2025 2:03 PM
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        logger.warning(f"Could not parse date: {date_str}, using current time")
        return datetime.now()

    async def download_pdf(
        self,
        pdf_url: str,
        output_path: Path,
        timeout: int = 60000
    ) -> bool:
        """
        Download a PDF file using Playwright to handle authentication/redirects/modals.

        Args:
            pdf_url: URL to the PDF
            output_path: Path where to save the PDF
            timeout: Timeout in milliseconds

        Returns:
            True if download successful, False otherwise
        """
        if not self.browser:
            raise RuntimeError("Browser not initialized. Use 'async with' context manager.")

        logger.debug(f"Downloading PDF from {pdf_url}")

        page = await self.browser.new_page()

        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Try to set up download listener and navigate
            # This handles both direct downloads and modal scenarios
            download_started_immediately = False

            try:
                async with page.expect_download(timeout=5000) as download_info:
                    # Navigate to the PDF URL
                    logger.debug("Navigating to PDF URL...")
                    try:
                        await page.goto(pdf_url, wait_until='domcontentloaded', timeout=5000)
                    except Exception as nav_error:
                        # Navigation might fail if download starts - that's OK
                        if "net::ERR_ABORTED" not in str(nav_error):
                            logger.debug(f"Navigation: {nav_error}")

                # Download started during navigation
                download = await download_info.value
                download_started_immediately = True
                logger.debug("Download started immediately (no modal)")

                # Save the download
                await download.save_as(output_path)

                if output_path.exists():
                    file_size = output_path.stat().st_size
                    logger.info(f"Downloaded PDF to {output_path} ({file_size:,} bytes)")
                    return True

            except PlaywrightTimeoutError:
                # Download didn't start immediately - check for modals
                logger.debug("Download didn't start immediately, checking for modals...")

                # Wait a moment for page to load
                await asyncio.sleep(1)

                # Check for terms and conditions modal
                modal_button_selectors = [
                    'button:has-text("Agree and Proceed")',
                    'button:has-text("Agree & Proceed")',
                    'button:has-text("Accept")',
                    'button:has-text("Continue")',
                    'a:has-text("Agree and Proceed")',
                    'a:has-text("Agree & Proceed")',
                    '[role="button"]:has-text("Agree")',
                    '.modal button:has-text("Proceed")',
                    '.dialog button:has-text("Proceed")',
                ]

                modal_found = False
                for selector in modal_button_selectors:
                    try:
                        button = await page.wait_for_selector(selector, timeout=1000)
                        if button:
                            logger.info(f"Found modal button: {selector}")
                            # Set up download listener before clicking
                            async with page.expect_download(timeout=30000) as modal_download_info:
                                await button.click()
                                logger.info("Clicked 'Agree and Proceed' button")

                            # Get and save the download
                            download = await modal_download_info.value
                            await download.save_as(output_path)

                            if output_path.exists():
                                file_size = output_path.stat().st_size
                                logger.info(f"Downloaded PDF to {output_path} ({file_size:,} bytes)")
                                return True

                            modal_found = True
                            break
                    except PlaywrightTimeoutError:
                        continue
                    except Exception as e:
                        logger.debug(f"Error with {selector}: {e}")
                        continue

                if not modal_found:
                    # No modal found, and download didn't start automatically
                    # Fall through to httpx fallback
                    logger.debug("No modal found, using fallback method")
                    raise Exception("No download started and no modal found")

        except Exception as e:
            # Only log actual errors (not expected download-related navigation errors)
            if "Download is starting" not in str(e):
                logger.error(f"Error downloading PDF from {pdf_url}: {e}")
            # Try alternative method using httpx as fallback
            try:
                import httpx
                logger.info("Attempting fallback download with httpx...")
                async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
                    response = await client.get(
                        pdf_url,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                    )
                    if response.status_code == 200:
                        output_path.write_bytes(response.content)
                        logger.info(f"Fallback download successful: {len(response.content):,} bytes")
                        return True
                    else:
                        logger.error(f"Fallback download failed: HTTP {response.status_code}")
                        return False
            except Exception as fallback_error:
                logger.error(f"Fallback download also failed: {fallback_error}")
                return False

        finally:
            await page.close()


async def scrape_asx_with_playwright(
    asx_code: str,
    max_announcements: int = 3,
    download_pdfs: bool = False,
    pdf_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """
    Convenience function to scrape ASX announcements using Playwright.

    Args:
        asx_code: ASX ticker code
        max_announcements: Maximum number of announcements to return
        download_pdfs: Whether to download PDFs
        pdf_dir: Directory to save PDFs (default: settings.pdf_storage_path)

    Returns:
        List of announcement dictionaries
    """
    async with ASXPlaywrightScraper() as scraper:
        announcements = await scraper.scrape_company_announcements(
            asx_code=asx_code,
            max_announcements=max_announcements
        )

        if download_pdfs and announcements:
            if pdf_dir is None:
                pdf_dir = Path(settings.pdf_storage_path)

            logger.info(f"Downloading {len(announcements)} PDFs to {pdf_dir}")

            for ann in announcements:
                # Generate filename from announcement date and title
                date_str = ann['announcement_date'].strftime('%Y%m%d_%H%M%S')
                safe_title = re.sub(r'[^\w\s-]', '', ann['title'])[:50]
                filename = f"{asx_code}_{date_str}_{safe_title}.pdf"
                output_path = pdf_dir / filename

                success = await scraper.download_pdf(ann['pdf_url'], output_path)

                if success:
                    ann['pdf_local_path'] = str(output_path)
                    ann['file_size_kb'] = output_path.stat().st_size // 1024

        return announcements
