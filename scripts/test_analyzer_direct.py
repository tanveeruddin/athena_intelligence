#!/usr/bin/env python3
"""Direct test of analyzer agent"""
import asyncio
from agents.analyzer.skills import process_and_analyze_announcement
from models.schemas import AnalyzerInput

async def main():
    input_data = AnalyzerInput(
        announcement_id="11f6195b-b6c0-4dda-9eb0-40de934716cc",
        pdf_url="https://cdn-api.markitdigital.com/apiman-gateway/ASX/asx-research/1.0/file/2924-03023532-3A681440",
        company_name="BHP",
        asx_code="BHP"
    )

    print(f"Testing analyzer with: {input_data}")
    result = await process_and_analyze_announcement(input_data)
    print(f"\nResult type: {type(result)}")
    print(f"Result: {result}")

    if hasattr(result, 'dict'):
        print(f"\nResult dict: {result.dict()}")

if __name__ == "__main__":
    asyncio.run(main())
