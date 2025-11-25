#!/usr/bin/env python3
"""
Database initialization script.
Creates all tables and optionally seeds test data.

Usage:
    python scripts/init_db.py [--reset] [--seed]

Options:
    --reset: Drop existing tables before creating new ones
    --seed: Add sample test data after initialization
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import (
    create_all_tables,
    reset_database,
    check_database_connection,
    get_db_session,
)
from models.orm_models import Company, Announcement, Analysis
from utils.config import get_settings
from utils.logging import get_logger
from datetime import datetime, timedelta

logger = get_logger()


def init_database(reset: bool = False):
    """
    Initialize the database.

    Args:
        reset: If True, drop all tables before creating
    """
    logger.info("Starting database initialization...")

    # Check connection
    if not check_database_connection():
        logger.error("Database connection failed. Please check your configuration.")
        return False

    # Create or reset tables
    if reset:
        logger.warning("Resetting database (dropping all tables)...")
        reset_database()
    else:
        logger.info("Creating database tables...")
        create_all_tables()

    logger.info("Database initialization complete!")
    return True


def seed_test_data():
    """Seed the database with sample test data."""
    logger.info("Seeding test data...")

    with get_db_session() as db:
        # Check if data already exists
        existing_count = db.query(Company).count()
        if existing_count > 0:
            logger.warning(f"Database already contains {existing_count} companies. Skipping seed.")
            return

        # Create sample companies
        companies = [
            Company(
                asx_code="BHP",
                company_name="BHP Group Limited",
                industry="Mining",
            ),
            Company(
                asx_code="CBA",
                company_name="Commonwealth Bank of Australia",
                industry="Banking",
            ),
            Company(
                asx_code="WBC",
                company_name="Westpac Banking Corporation",
                industry="Banking",
            ),
            Company(
                asx_code="CSL",
                company_name="CSL Limited",
                industry="Biotechnology",
            ),
            Company(
                asx_code="NAB",
                company_name="National Australia Bank Limited",
                industry="Banking",
            ),
        ]

        db.add_all(companies)
        db.commit()

        logger.info(f"Created {len(companies)} sample companies")

        # Create sample announcements for BHP
        bhp = db.query(Company).filter(Company.asx_code == "BHP").first()
        if bhp:
            announcements = [
                Announcement(
                    company_id=bhp.id,
                    asx_code="BHP",
                    title="Quarterly Production Report - Strong Results",
                    announcement_date=datetime.now() - timedelta(days=30),
                    pdf_url="https://example.com/bhp_q1_2025.pdf",
                    is_price_sensitive=True,
                ),
                Announcement(
                    company_id=bhp.id,
                    asx_code="BHP",
                    title="Cost Reduction Initiative Announced",
                    announcement_date=datetime.now() - timedelta(days=15),
                    pdf_url="https://example.com/bhp_cost_reduction.pdf",
                    is_price_sensitive=True,
                ),
                Announcement(
                    company_id=bhp.id,
                    asx_code="BHP",
                    title="Dividend Declaration",
                    announcement_date=datetime.now() - timedelta(days=5),
                    pdf_url="https://example.com/bhp_dividend.pdf",
                    is_price_sensitive=True,
                ),
            ]

            db.add_all(announcements)
            db.commit()

            logger.info(f"Created {len(announcements)} sample announcements for BHP")

            # Create sample analysis for first announcement
            first_announcement = announcements[0]
            analysis = Analysis(
                announcement_id=first_announcement.id,
                summary="BHP reports strong quarterly production results with iron ore volumes exceeding guidance. Copper production remains robust.",
                sentiment="BULLISH",
                key_insights='["Iron ore production up 5% QoQ", "Copper volumes exceed expectations", "Cost discipline maintained"]',
                management_promises='["Maintain production guidance for FY25", "Continue cost reduction initiatives"]',
                financial_impact="Positive impact expected on quarterly earnings",
                llm_model="gemini-2.0-flash-exp",
                processing_time_ms=1500,
                tokens_used=450,
            )

            db.add(analysis)
            db.commit()

            logger.info("Created sample analysis for BHP announcement")

    logger.info("Test data seeding complete!")


def verify_database():
    """Verify database structure."""
    logger.info("Verifying database structure...")

    with get_db_session() as db:
        # Count records in each table
        company_count = db.query(Company).count()
        announcement_count = db.query(Announcement).count()
        analysis_count = db.query(Analysis).count()

        logger.info(f"Database statistics:")
        logger.info(f"  - Companies: {company_count}")
        logger.info(f"  - Announcements: {announcement_count}")
        logger.info(f"  - Analysis: {analysis_count}")

        # Test a simple query
        if company_count > 0:
            sample_company = db.query(Company).first()
            logger.info(f"  - Sample company: {sample_company.asx_code} - {sample_company.company_name}")

    logger.info("Database verification complete!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Initialize the ASX Scraper database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset database (drop all tables)",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed database with test data",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify database structure",
    )

    args = parser.parse_args()

    # Get settings to ensure directories exist
    settings = get_settings()
    logger.info(f"Using database: {settings.database_url}")

    try:
        # Initialize database
        if not init_database(reset=args.reset):
            logger.error("Database initialization failed")
            return 1

        # Seed test data if requested
        if args.seed:
            seed_test_data()

        # Verify database
        if args.verify or args.seed:
            verify_database()

        logger.info("All operations completed successfully!")
        return 0

    except Exception as e:
        logger.error(f"Error during database initialization: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
