import time
import os
import shutil
import logging
from typing import List, Optional
from playwright.sync_api import sync_playwright, Page, BrowserContext
from pypdf import PdfReader
from sqlalchemy.orm import Session
from app.models.documents import CaseDocument
from app.services.llm_service import LLMService, QuotaExhaustedException
from app.scrapers.base_scraper import BaseScraper
from app.database import get_db

import logging
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Suppress only the single warning from urllib3 needed.
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

logger = logging.getLogger(__name__)

class SHCScraper(BaseScraper):
    def __init__(self, db: Session, llm_service: LLMService, download_dir: str = "downloads"):
        self.db = db
        self.llm_service = llm_service
        self.download_dir = download_dir
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

    def connect(self, cdp_url: str = "http://localhost:9222"):
        """Connects to an existing Chrome instance via CDP."""
        self.playwright = sync_playwright().start()
        try:
            self.browser = self.playwright.chromium.connect_over_cdp(cdp_url)
            self.context = self.browser.contexts[0]
            if not self.context.pages:
                self.page = self.context.new_page() # Fallback
            else:
                self.page = self.context.pages[0] # Use active page
            logger.info("Connected to browser successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to browser: {e}")
            raise

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _extract_pdf_text(self, pdf_path: str) -> str:
        try:
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            logger.error(f"Error extracting PDF text from {pdf_path}: {e}")
            return ""

    def scrape(self):
        """Scrapes the SHC website table."""
        if not self.page:
            logger.error("No page connected.")
            return

        # Ensure we are on the right page? User said they navigate.
        # Assuming current page is the target.

        processed_case_nos = set() # To avoid duplicates in this run

        # Loop for scrolling and processing
        last_height = 0
        while True:
            # Get all rows
            rows = self.page.locator("table tbody tr").all()
            logger.info(f"Found {len(rows)} rows visible.")

            for i, row in enumerate(rows):
                # Retry Logic (3 attempts)
                pdf_text = ""
                pdf_filename = ""
                pdf_url = ""
                extracted_data = {}
                
                for attempt in range(3):
                    try:
                        # Extract basic data
                        cols = row.locator("td").all()
                        if len(cols) < 7:
                            break # Skip invalid rows immediately

                        s_no = cols[0].inner_text().strip()
                        topic = cols[1].inner_text().strip()
                        case_no_raw = cols[2].inner_text().strip()
                        tag_line = cols[4].inner_text().strip()
                        citation = cols[5].inner_text().strip()
                        
                        if case_no_raw in processed_case_nos:
                            break

                        logger.info(f"Processing Case: {case_no_raw} (Attempt {attempt+1})")

                        # Check DB for existing via Reference ID
                        existing = self.db.query(CaseDocument).filter(CaseDocument.reference_id == case_no_raw).first()
                        
                        if existing:
                            logger.info(f"Case {case_no_raw} already exists. Skipping.")
                            processed_case_nos.add(case_no_raw)
                            break

                        # Handle PDF Download via New Tab
                        view_btn = cols[6].locator("a, button, .btn")
                        
                        try:
                            if view_btn.count() > 0:
                                with self.context.expect_page(timeout=10000) as new_page_info:
                                    view_btn.first.click(modifiers=["Control"])
                                
                                new_page = new_page_info.value
                                try:
                                    new_page.wait_for_load_state("domcontentloaded", timeout=60000)
                                    if new_page.url == "about:blank": time.sleep(2)
                                    
                                    pdf_url = new_page.url
                                    logger.info(f"PDF Tab URL: {pdf_url}")

                                    if pdf_url and pdf_url != "about:blank":
                                        existing_pdf = self.db.query(CaseDocument).filter(CaseDocument.raw_content_uri == pdf_url).first()
                                        if existing_pdf:
                                            logger.info(f"Duplicate PDF URL found: {pdf_url}. Skipping.")
                                            new_page.close()
                                            break

                                    # Heuristic: URL ends with .pdf OR contains 'view-file' (common pattern)
                                    is_pdf_candidate = pdf_url.lower().endswith('.pdf') or 'view-file' in pdf_url.lower()
                                    
                                    if is_pdf_candidate:
                                         import requests
                                         # Stream to check headers first if needed, but we'll just download
                                         response = requests.get(pdf_url, stream=True, verify=False)
                                         
                                         content_type = response.headers.get('Content-Type', '').lower()
                                         if response.status_code == 200:
                                             # Determine filename
                                             basename = os.path.basename(pdf_url).split('?')[0]
                                             if not basename.lower().endswith('.pdf'):
                                                 basename += ".pdf"
                                             
                                             pdf_filename = os.path.join(self.download_dir, f"{s_no}_{basename}".replace("?", "_").replace("=", "_"))
                                             
                                             with open(pdf_filename, 'wb') as f:
                                                 for chunk in response.iter_content(chunk_size=8192):
                                                     f.write(chunk)
                                             
                                             logger.info(f"Downloaded PDF from {pdf_url} (Type: {content_type})")
                                             pdf_text = self._extract_pdf_text(pdf_filename)
                                         else:
                                             logger.warning(f"Failed to download PDF. Status: {response.status_code}")
                                    else:
                                        # Assume HTML content
                                        pdf_text = new_page.locator("body").inner_text()
                                        logger.info("Extracted text from HTML Judgement page.")
                                        pdf_filename = pdf_url

                                except Exception as tab_err:
                                    logger.warning(f"Error processing PDF tab: {tab_err}")
                                finally:
                                    if not new_page.is_closed(): new_page.close()
                        except Exception as e:
                            logger.warning(f"Failed to handle View Link for {case_no_raw}: {e}")
                        
                        # LLM Extraction
                        scraped_metadata = {
                            "s_no": s_no,
                            "topic": topic,
                            "case_no_raw": case_no_raw,
                            "tag_line": tag_line,
                            "citation": citation
                        }
                        
                        try:
                            # Explicitly pass model name just in case, or rely on default which we updated
                            # Truncate text for LLM but keep full text for DB
                            llm_input_text = pdf_text[:40000] if pdf_text else ""
                            # Let LLMService handle provider selection (Gemini -> Groq)
                            extracted_data = self.llm_service.extract_case_data(scraped_metadata, llm_input_text)
                        except QuotaExhaustedException as qe:
                            logger.critical(f"Critical Quota Error: {qe} - Stopping Scraper.")
                            return # Stop scraping entirely
                        except Exception as llm_err:
                            logger.error(f"LLM extraction step failed: {llm_err}")
                            if attempt < 2: raise llm_err # Retry if not last attempt
                            # If last attempt, proceed with empty extracted_data

                        # Create DB Record Setup
                        final_reference_id = extracted_data.get("reference_no") or case_no_raw
                        final_title = extracted_data.get("case_title") or topic

                        new_case = CaseDocument(
                            reference_id=final_reference_id,
                            title=final_title, 
                            doc_type="Judgement",
                            jurisdiction="Sindh High Court",
                            source="SHC Website",
                            citation=citation,
                            year=int(extracted_data.get("year", 0)) if extracted_data.get("year") else 0, 
                            raw_content_uri=pdf_url, # Ensure usage of URL, not local path
                            legal_status=extracted_data.get("legal_status"),
                            contents=pdf_text, # Ensure full text is stored

                            advocates=extracted_data.get("advocates"), 
                            case_type=extracted_data.get("case_type"),
                            case_number=extracted_data.get("case_number"),
                            bench=extracted_data.get("bench"),
                            parties=extracted_data.get("parties"),
                            topic=extracted_data.get("topic"),
                            decision_date=None, 
                            extra_metadata={
                                "tag_line": tag_line,
                                "summary": extracted_data.get("summary"),
                                "other_llm_data": extracted_data,
                                "original_case_no_raw": case_no_raw
                            }
                        )
                        
                        self.db.add(new_case)
                        self.db.commit()
                        processed_case_nos.add(case_no_raw)
                        logger.info(f"Saved Case {final_reference_id}")
                        break # Success

                    except Exception as row_err:
                        logger.error(f"Error processing row {i} (Attempt {attempt+1}): {row_err}")
                        self.db.rollback()
                        time.sleep(2)
                        
                        # Fallback after 3 attempts
                        if attempt == 2:
                             logger.warning(f"Failed after 3 attempts. Saving partial record for {case_no_raw}...")
                             try:
                                 # Save with whatever we have (scraped metadata only)
                                 fallback_case = CaseDocument(
                                    reference_id=case_no_raw,
                                    title=topic, 
                                    doc_type="Judgement",
                                    jurisdiction="Sindh High Court",
                                    source="SHC Website",
                                    citation=citation,
                                    year=0,
                                    raw_content_uri=pdf_filename or pdf_url,
                                    legal_status="N/A",
                                    contents=pdf_text, # Might be empty
                                    advocates="N/A",
                                    case_type="N/A",
                                    case_number="N/A",
                                    bench="N/A",
                                    parties="N/A",
                                    topic=topic,
                                    decision_date=None, 
                                    extra_metadata={
                                        "tag_line": tag_line,
                                        "original_case_no_raw": case_no_raw,
                                        "note": "Partial record saved after retries failed."
                                    }
                                 )
                                 self.db.add(fallback_case)
                                 self.db.commit()
                                 processed_case_nos.add(case_no_raw)
                                 logger.info(f"Saved Partial Case {case_no_raw}")
                             except Exception as save_err:
                                 logger.error(f"Failed to save partial record: {save_err}")
                                 self.db.rollback()

            # Scroll Down
            logger.info("Scrolling down...")
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2) # Wait for load
            
            # Check if height changed (end of page)
            # This is a simple check, user said "so more records could be loaded"
            # We can also check if number of rows increased.
            new_rows = len(self.page.locator("table tbody tr").all())
            if new_rows == len(rows):
                # Maybe no more records? Or check height
                # new_height = self.page.evaluate("document.body.scrollHeight")
                # if new_height == last_height:
                #    break
                # last_height = new_height
                # For now, let's just break if no new rows for 3 attempts?
                # Or just assume infinite scroll until explicit stop?
                # I'll rely on row count for now.
                logger.info("No new rows loaded. Stopping.")
                break
