import asyncio
import aiohttp
import random
import string
import time
import argparse
import logging
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def generate_random_data(length=20):
    data = ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    return data

def single_request(url):
    try:
        import requests
        data = {"data": generate_random_data()}
        response = requests.post(url, json=data)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        return False

def process_batch(args):
    url, batch_size = args
    results = []
    for _ in range(batch_size):
        result = single_request(url)
        results.append(result)
    return results

def main():
    parser = argparse.ArgumentParser(description='Load test for objects endpoint')
    parser.add_argument('total', type=int, help='Total number of requests to make')
    parser.add_argument('concurrent', type=int, help='Number of concurrent requests')
    parser.add_argument('--processes', type=int, default=mp.cpu_count(), help='Number of processes to use')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    url = 'http://localhost:8002/objects'
    total_requests = args.total
    concurrent_requests = args.concurrent
    num_processes = min(args.processes, concurrent_requests)
    
    logger.info(f"Starting load test with {total_requests} total requests")
    logger.info(f"Using {num_processes} processes for concurrent execution")
    
    start_time = time.time()
    
    # Prepare batches
    batch_size = concurrent_requests
    num_batches = total_requests // batch_size
    remaining = total_requests % batch_size
    
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        # Process full batches
        batch_args = [(url, batch_size) for _ in range(num_batches)]
        results = list(executor.map(process_batch, batch_args))
        
        # Process remaining requests if any
        if remaining > 0:
            final_batch = process_batch((url, remaining))
            results.append(final_batch)
    
    # Calculate statistics
    end_time = time.time()
    duration = end_time - start_time
    
    successful = sum(sum(batch) for batch in results)
    total_completed = sum(len(batch) for batch in results)
    rate = total_completed / duration
    
    logger.info("----- Test Complete -----")
    logger.info(f"Completed {total_completed} requests, {successful} successful")
    logger.info(f"Total time: {duration:.2f} seconds")
    logger.info(f"Average rate: {rate:.2f} requests/second")

if __name__ == "__main__":
    print("Script initialized")
    main()
    print("Script completed")
