from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import json
import logging
from app.services.key_manager import KeyManager

logger = logging.getLogger(__name__)

class QuotaExhaustedException(Exception):
    pass

class LLMService:
    def __init__(self, key_file_path: str = "keys.json"):
        self.key_manager = KeyManager(key_file_path)
        self.providers = [
            ("gemini", "gemini-2.5-flash-lite"),
            ("groq", "llama-3.3-70b-versatile")
        ]
        self.current_provider_index = 0

    def get_llm(self, host: str, model_name: str):
        api_key = self.key_manager.get_key(host, model_name)
        if not api_key:
            if not api_key:
                raise ValueError(f"No available keys for {host}/{model_name}")

        if host == "gemini":
            # Disable internal retries so we can handle rotation manually
            return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0, max_retries=0), api_key
        elif host == "groq":
             # Use OpenAI client for Groq compatibility
             return ChatOpenAI(model=model_name, api_key=api_key, base_url="https://api.groq.com/openai/v1", temperature=0, max_retries=0), api_key
        else:
            raise ValueError(f"Unknown host: {host}")

    def extract_case_data(self, scraped_data: dict, pdf_text: str) -> dict:
        """
        Extracts structured case data using LLM. 
        Sticky Fallback: Uses current provider until failure, then switches.
        Circular Retry: If all providers fail, waits and retries.
        """
        import time
        
        last_exception = None
        providers_tried = 0
        
        # Infinite Loop until success
        while True:
            current_host, current_model = self.providers[self.current_provider_index]
            logger.info(f"Attempting extraction with provider: {current_host}/{current_model}")
            
            # Internal Retry Loop for the specific provider
            max_retries = 3 
            provider_success = False
            
            for attempt in range(max_retries):
                llm = None
                api_key = None
                try:
                    llm, api_key = self.get_llm(current_host, current_model)
                except ValueError as e:
                    logger.warning(f"Setup failed for {current_host}/{current_model}: {e}. Skipping to next provider.")
                    break # Break retry loop to switch provider

                schema = {
                    "reference_no": "The specific Case Reference Number (e.g. 'Suit 540/2005 (S.B.)' or 'CP D-123/2024'). It is usually the first part of the Case No field.",
                    "case_title": "The Title of the case, usually the Parties names (e.g. 'MANSOOR AHMED & ORS V/S MST. SAEEDA BEGUM & ORS'). Exclude the reference number.",
                    "advocates": "List of advocates names",
                    "tag_line": "The tag line or subject header",
                    "case_type": "Type of case (e.g. Cr.Misc, Suit, Const. P.)",
                    "case_number": "The numeric part of the case number (e.g. 540/2005)",
                    "bench": "The bench (e.g. S.B., D.B.)",
                    "parties": "The full title of parties (e.g. Hussain Bux Dal vs Muhammad Khan...)",
                    "topic": "The topic category (e.g. Criminal Procedure Code)",
                    "citation": "Citation reference",
                    "decision_date": "Date of decision in YYYY-MM-DD format",
                    "legal_status": "Status (e.g. Allowed, Dismissed)",
                    "year": "The year of the case (e.g. 2005)",
                    "summary": "Brief summary of the judgment"
                }

                prompt = ChatPromptTemplate.from_messages([
                    ("system", "You are a legal assistant. Extract the following fields from the provided case text and scraped metadata. Return strictly VALID JSON."),
                    ("user", """
                    Target Schema: {schema}
        
                    Scraped Metadata: {scraped_data}
        
                    PDF Content (Truncated): {pdf_text}
        
                    Return only the JSON object.
                    """)
                ])

                chain = prompt | llm | StrOutputParser()

                try:
                    result = chain.invoke({
                        "schema": json.dumps(schema, indent=2),
                        "scraped_data": json.dumps(scraped_data, indent=2),
                        "pdf_text": pdf_text[:30000]
                    })
                    
                    result = result.replace("```json", "").replace("```", "").strip()
                    return json.loads(result) # Success! Return immediately.
                
                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        logger.warning(f"Quota exceeded for key {api_key[:10]}... for {current_host}/{current_model}. Rotating...")
                        self.key_manager.mark_key_limit_reached(current_host, current_model, api_key)
                        continue # Retry with next key
                    else:
                        logger.error(f"Error {current_host}: {e}")
                        last_exception = e
                        continue # Retry (maybe transient)

            # If we are here, the current provider failed all retries (or setup failed)
            logger.warning(f"Provider {current_host} validation failed. Switching to next provider.")
            
            # Switch to next provider PERMANENTLY (for this session)
            self.current_provider_index = (self.current_provider_index + 1) % len(self.providers)
            providers_tried += 1
            
            # Check if we have tried ALL providers in this cycle
            if providers_tried >= len(self.providers):
                logger.critical("All providers exhausted/cooling down. Sleeping 60s...")
                try:
                    time.sleep(60)
                except KeyboardInterrupt:
                    raise
                providers_tried = 0 # Reset cycle counter

