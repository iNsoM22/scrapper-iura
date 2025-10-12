from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import sys
import os
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service import store_batch_records, store_raw_metadata

def _build_driver_attach():
    """Attach to an existing Edge window (opened with --remote-debugging-port=9222)."""
    options = Options()
    options.add_experimental_option("debuggerAddress", "localhost:9222")
    return webdriver.Edge(options=options)


def crawl_attached(start: int | None = None, end: int | None = None, save_interval: int = 20):
    driver = _build_driver_attach()
    print("Attached to existing Edge session!")
    print("Current URL:", driver.current_url)
    print("Page title:", driver.title)

    actions = ActionChains(driver)
    fieldnames = ["S.No", "Topic", "Case No", "Advocates", "Tag Line", "Citation", "Judgement"]
    delimiter = '[COLEND;]'
    
    metadata_id = store_raw_metadata(driver.current_url, delimiter, fieldnames)

    new_batch = []
    current_year = time.localtime().tm_year

    start_year = start if isinstance(start, int) and start > 0 else 1955
    end_year = end if isinstance(end, int) and end > 0 else current_year
    if end_year < start_year:
        print(f"Provided range invalid (start={start_year}, end={end_year}). Swapping.")
        start_year, end_year = end_year, start_year

    print(f"Processing years from {start_year} to {end_year}...")

    for year in range(start_year, end_year + 1):
        print(f"\nProcessing year {year}...")
        try:
            # Locate input field and set the year
            input_field = WebDriverWait(driver, 20 + abs(1947 - year)).until(
                EC.presence_of_element_located((By.ID, "citation_year"))
            )
            input_field.clear()
            input_field.send_keys(str(year))

            # Click the search/submit button
            search_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Search')] | //input[@value='Search']")
            search_button.click()

            # Wait for results to load (table rows to appear)
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table tr"))
            )

            # Get table rows
            rows = driver.find_elements(By.CSS_SELECTOR, "table tr")
            print(f"Found {len(rows)} rows for year {year}")

            for i, row in enumerate(rows, start=1):
                try:
                    cells = [c.text.strip() for c in row.find_elements(By.TAG_NAME, "td")]
                    if not cells:
                        continue

                    # Extract "View Judgement" PDF link
                    pdf_link = None
                    view_btns = row.find_elements(
                        By.XPATH, ".//a[contains(., 'View Judgement')] | .//button[contains(., 'View Judgement')]"
                    )
                    if view_btns:
                        elem = view_btns[0]
                        pdf_link = elem.get_attribute("href") or elem.get_attribute("onclick")

                    record = {
                        "S.No": cells[0] if len(cells) > 0 else "",
                        "Topic": cells[1] if len(cells) > 1 else "",
                        "Case No": cells[2] if len(cells) > 2 else "",
                        "Advocates": cells[3] if len(cells) > 3 else "",
                        "Tag Line": cells[4] if len(cells) > 4 else "",
                        "Citation": cells[5] if len(cells) > 5 else "",
                        "Judgement": pdf_link or "N/A",
                    }

                    new_batch.append(record)

                    # Small scroll for lazy loading
                    actions.scroll_by_amount(0, 150).perform()
                    time.sleep(0.5)

                    # Save in batches
                    if len(new_batch) >= save_interval:
                        records_to_store = new_batch.copy()
                        store_batch_records(metadata_id, records_to_store, "Judgement")
                        new_batch.clear()

                except Exception as e:
                    print(f"Error parsing row {i}: {e}")

        except Exception as e:
            print(f"Error for year {year}: {e}")

        print(f"Completed year {year}. Waiting before next...")
        time.sleep(5)

    # Save remaining records
    if new_batch:
        records_to_store = new_batch.copy()
        store_batch_records(metadata_id, records_to_store, "Judgement")
        new_batch.clear()
        print(f"Final save: {len(records_to_store)} records written.")

    print("\nCrawling complete.")
    input("\nPress ENTER to detach (browser will stay open)...")
    driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Attach to an existing Edge (port 9222) and crawl by year range")
    parser.add_argument("--start", type=int, help="Start year (e.g., 1947)")
    parser.add_argument("--end", type=int, help="End year (e.g., 1970)")
    parser.add_argument("--save-interval", type=int, default=20, help="How many rows to buffer before saving")
    args = parser.parse_args()

    crawl_attached(start=args.start, end=args.end, save_interval=args.save_interval)
