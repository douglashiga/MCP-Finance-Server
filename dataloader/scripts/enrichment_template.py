"""
Template script for an Enrichment Job.
Fetch raw data (e.g. news, events), process with LLM, and save results.
"""
import sys
import logging
from datetime import datetime
from sqlalchemy import text
from dataloader.database import SessionLocal
from dataloader.models import RawMarketEvent
from dataloader.llm import get_llm_client

# Configure logging to stdout so it appears in the job runner UI
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
logger = logging.getLogger("enrichment_job")

def main():
    logger.info("Starting Enrichment Job Template...")
    
    # 1. Initialize LLM Client
    llm = get_llm_client()
    if not llm:
        logger.error("No active LLM configuration found. Please configure one in Settings.")
        return

    logger.info(f"Using LLM Provider: {llm.provider}, Model: {llm.model}")

    # 2. Fetch data to enrich (Example: RawMarketEvents that haven't been processed)
    # in a real scenario, you'd filter by processed=False or similar
    session = SessionLocal()
    try:
        # Fetch last 5 raw events as a sample
        events = session.query(RawMarketEvent).order_by(RawMarketEvent.fetched_at.desc()).limit(5).all()
        
        if not events:
            logger.info("No raw events found to process.")
            return

        logger.info(f"Found {len(events)} events to process.")

        for event in events:
            logger.info(f"Processing event {event.id} from {event.source}...")
            
            # 3. Construct Prompt
            prompt = [
                {"role": "system", "content": "You are a financial analyst. Summarize the following market event and extract the key sentiment (POSITIVE, NEGATIVE, NEUTRAL). Output format: Sentiment: [SENTIMENT] | Summary: [SUMMARY]"},
                {"role": "user", "content": f"Event Payload: {event.payload[:2000]}"} # Truncate to avoid context limits if needed
            ]

            # 4. Call LLM
            response = llm.chat_completion(prompt)
            
            if response:
                logger.info(f"LLM Response: {response}")
                # 5. Save result (Pseudo-code: In reality, you'd save to an 'enriched_events' table or similar)
                # event.enrichment_data = response 
                # session.commit()
            else:
                logger.warning(f"Failed to get response for event {event.id}")

    except Exception as e:
        logger.error(f"Job failed: {e}")
    finally:
        session.close()

    logger.info("Enrichment Job Completed.")

if __name__ == "__main__":
    main()
