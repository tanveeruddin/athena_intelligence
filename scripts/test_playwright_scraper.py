"""
Test script for Playwright-based ASX scraper.
Tests scraping and PDF downloading functionality.
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


import asyncio
from utils.playwright_scraper import ASXPlaywrightScraper
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()

# Enable DEBUG logging for detailed output
import logging
logger.remove()
logger.add(sys.stdout, level="DEBUG", colorize=True)


async def test_scraper(asx_code: str, max_announcements: int = 3, download_pdfs: bool = True, price_sensitive_only: bool = True):
    """
    Test the Playwright scraper with a specific ASX code.

    Args:
        asx_code: ASX ticker code (e.g., "CBA", "BHP")
        max_announcements: Number of announcements to fetch
        download_pdfs: Whether to download PDFs
        price_sensitive_only: Whether to only include price-sensitive announcements
    """
    print(f"\n{'='*80}")
    print(f"TESTING PLAYWRIGHT SCRAPER FOR: {asx_code}")
    print(f"{'='*80}\n")

    asx_code = asx_code.upper()

    # Create PDF directory
    pdf_dir = Path(settings.pdf_storage_path)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    print(f"📍 Configuration:")
    print(f"   ASX Code: {asx_code}")
    print(f"   Max Announcements: {max_announcements}")
    print(f"   Price Sensitive Only: {price_sensitive_only}")
    print(f"   Download PDFs: {download_pdfs}")
    print(f"   PDF Directory: {pdf_dir}")
    print()

    # Test scraping
    print(f"🚀 Starting Playwright scraper...")
    print(f"   This may take 30-60 seconds to load the page...\n")

    async with ASXPlaywrightScraper() as scraper:
        # Scrape announcements - fetch extra to ensure we get enough after filtering
        # For price-sensitive filtering, fetch more announcements since they may not be at the top
        if price_sensitive_only:
            # Fetch at least 25 announcements or 10x the requested amount, whichever is larger
            # This ensures we scan through enough announcements to find price-sensitive ones
            fetch_limit = max(25, max_announcements * 10)
        else:
            fetch_limit = max_announcements

        all_announcements = await scraper.scrape_company_announcements(
            asx_code=asx_code,
            max_announcements=fetch_limit
        )

        if not all_announcements:
            print(f"❌ No announcements found for {asx_code}")
            print(f"   This could mean:")
            print(f"   1. There are no recent announcements")
            print(f"   2. The page structure has changed")
            print(f"   3. The scraper needs adjustment")
            return

        print(f"✅ Found {len(all_announcements)} total announcements")

        # Filter by price sensitivity if requested
        if price_sensitive_only:
            announcements = [ann for ann in all_announcements if ann['is_price_sensitive']]
            print(f"✅ Filtered to {len(announcements)} price-sensitive announcements")
        else:
            announcements = all_announcements

        # Apply limit
        if len(announcements) > max_announcements:
            announcements = announcements[:max_announcements]
            print(f"✅ Limited to {max_announcements} announcements")

        if not announcements:
            print(f"❌ No {'price-sensitive ' if price_sensitive_only else ''}announcements found for {asx_code}")
            return

        print()

        # Display announcements
        print(f"{'='*80}")
        print(f"ANNOUNCEMENTS")
        print(f"{'='*80}\n")

        for i, ann in enumerate(announcements, 1):
            print(f"{i}. {ann['title'][:80]}")
            print(f"   Date: {ann['announcement_date']}")
            print(f"   Price Sensitive: {'Yes ✓' if ann['is_price_sensitive'] else 'No'}")
            print(f"   PDF: {ann['pdf_url'][:100]}...")
            print()

        # Download PDFs if requested
        if download_pdfs and announcements:
            print(f"\n{'='*80}")
            print(f"DOWNLOADING PDFs")
            print(f"{'='*80}\n")

            for i, ann in enumerate(announcements, 1):
                # Generate filename
                date_str = ann['announcement_date'].strftime('%Y%m%d_%H%M%S')
                safe_title = ''.join(c for c in ann['title'] if c.isalnum() or c in ' -_')[:50]
                filename = f"{asx_code}_{date_str}_{safe_title}.pdf"
                output_path = pdf_dir / filename

                print(f"{i}/{len(announcements)} Downloading: {filename}")

                success = await scraper.download_pdf(ann['pdf_url'], output_path)

                if success:
                    file_size = output_path.stat().st_size
                    print(f"   ✅ Downloaded {file_size:,} bytes")
                    ann['pdf_local_path'] = str(output_path)
                    ann['file_size_kb'] = file_size // 1024
                else:
                    print(f"   ❌ Download failed")

                print()

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"ASX Code: {asx_code}")
    print(f"Total Announcements: {len(announcements)}")
    print(f"Price Sensitive: {sum(1 for a in announcements if a['is_price_sensitive'])}")

    if download_pdfs:
        downloaded = sum(1 for a in announcements if 'pdf_local_path' in a)
        print(f"PDFs Downloaded: {downloaded}/{len(announcements)}")
        if downloaded > 0:
            total_size = sum(a.get('file_size_kb', 0) for a in announcements if 'file_size_kb' in a)
            print(f"Total Size: {total_size} KB")

    print(f"{'='*80}\n")

    # Show first PDF path if downloaded
    if download_pdfs and announcements and 'pdf_local_path' in announcements[0]:
        print(f"✅ First PDF saved to: {announcements[0]['pdf_local_path']}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Test Playwright-based ASX scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test scraping price-sensitive CBA announcements with PDF download (default)
  python test_playwright_scraper.py --asx-code CBA

  # Test without downloading PDFs
  python test_playwright_scraper.py --asx-code BHP --no-download

  # Fetch more price-sensitive announcements
  python test_playwright_scraper.py --asx-code WBC --limit 5

  # Include all announcements (not just price-sensitive)
  python test_playwright_scraper.py --asx-code CBA --no-price-sensitive
        """
    )

    parser.add_argument(
        "--asx-code",
        type=str,
        required=True,
        help="ASX ticker code (e.g., CBA, BHP, WBC)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum number of announcements to fetch (default: 3)"
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Skip PDF downloads (scraping only)"
    )
    parser.add_argument(
        "--no-price-sensitive",
        action="store_true",
        help="Include all announcements (not just price-sensitive)"
    )

    args = parser.parse_args()

    try:
        asyncio.run(test_scraper(
            asx_code=args.asx_code,
            max_announcements=args.limit,
            download_pdfs=not args.no_download,
            price_sensitive_only=not args.no_price_sensitive
        ))
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
