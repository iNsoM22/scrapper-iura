import argparse
import logging
import sys
import os

# Ensure app is in path if running as script
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine, Base, get_db
from app.services.llm_service import LLMService
from app.scrapers.shc_scraper import SHCScraper

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="SHC Scraper Service")
    parser.add_argument("--cdp", type=str, default="http://localhost:9222", help="CDP URL for browser connection")
    parser.add_argument("--mode", type=str, default="shc", help="Scraper mode (only 'shc' for now)")
    parser.add_argument("--install-playwright", action="store_true", help="Install playwright browsers")
    args = parser.parse_args()

    if args.install_playwright:
        os.system("playwright install chromium")
        return

    # Initialize DB (Optional, usually handled by Alembic)
    # Base.metadata.create_all(bind=engine) 

    db_gen = get_db()
    db = next(db_gen)
    
    try:
        llm_service = LLMService()

        if args.mode == "shc":
            scraper = SHCScraper(db=db, llm_service=llm_service)
            try:
                logger.info(f"Connecting to browser at {args.cdp}...")
                scraper.connect(cdp_url=args.cdp)
                logger.info("Connected to browser successfully.")
                
                while True:
                    user_input = input("\nPress Enter to start/continue (or enter skip count, e.g. '40', or 'q' to quit): ")
                    if user_input.lower() == 'q':
                        break
                    
                    skip_count = 0
                    if user_input.strip().isdigit():
                        skip_count = int(user_input.strip())
                        logger.info(f"Skipping first {skip_count} records.")
                    
                    logger.info("Starting scrape...")
                    scraper.scrape(skip_count=skip_count)
                    logger.info("Batch completed. Waiting for input...")
            except Exception as e:
                logger.error(f"Scraper failed: {e}")
            finally:
                scraper.close()
        else:
            logger.error(f"Unknown mode: {args.mode}")

    finally:
        db.close()

if __name__ == "__main__":
    main()
