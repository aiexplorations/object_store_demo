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

def generate_random_data(size_bytes):
    # Calculate string length needed for target size in bytes
    # Each char is ~1 byte in UTF-8
    data = ''.join(random.choices(string.ascii_letters + string.digits, k=size_bytes))
    actual_size = len(data.encode('utf-8'))
    logger.debug(f"Generated data size: {actual_size} bytes")
    return data

def generate_random_id(max_id):
    return random.randint(1, max_id)

def single_request(url, size_bytes, operation='create', max_id=None):
    try:
        import requests
        if operation == 'create':
            data = {"data": generate_random_data(size_bytes)}
            response = requests.post(url, json=data)
        else:  # read operation
            object_id = generate_random_id(max_id)
            response = requests.get(f"{url}/{object_id}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        return False

def process_batch(args):
    url, batch_size, size_bytes, operation, max_id = args
    results = []
    for _ in range(batch_size):
        result = single_request(url, size_bytes, operation, max_id)
        results.append(result)
    return results

def main():
    parser = argparse.ArgumentParser(description='Load test for objects endpoint')
    parser.add_argument('total', type=int, help='Total number of requests to make')
    parser.add_argument('concurrent', type=int, help='Number of concurrent requests')
    parser.add_argument('--size', type=int, default=20, help='Approximate size of each request in bytes')
    parser.add_argument('--processes', type=int, default=mp.cpu_count(), help='Number of processes to use')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--operation', choices=['create', 'read'], default='create',
                       help='Operation to perform (create or read)')
    parser.add_argument('--max-id', type=int, default=20000,
                       help='Maximum object ID for read operations')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    url = 'http://localhost:8002/objects'
    total_requests = args.total
    concurrent_requests = args.concurrent
    size_bytes = args.size
    num_processes = min(args.processes, concurrent_requests)
    operation = args.operation
    max_id = args.max_id
    
    logger.info(f"Starting load test with {total_requests} total requests")
    logger.info(f"Using {num_processes} processes for concurrent execution")
    logger.info(f"Request size: ~{size_bytes} bytes")
    logger.info(f"Operation mode: {operation}")
    if operation == 'read':
        logger.info(f"Reading from object IDs up to {max_id}")
    
    start_time = time.time()
    
    batch_size = concurrent_requests
    num_batches = total_requests // batch_size
    remaining = total_requests % batch_size
    
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        batch_args = [(url, batch_size, size_bytes, operation, max_id) 
                     for _ in range(num_batches)]
        results = list(executor.map(process_batch, batch_args))
        
        if remaining > 0:
            final_batch = process_batch((url, remaining, size_bytes, operation, max_id))
            results.append(final_batch)
    
    end_time = time.time()
    duration = end_time - start_time
    
    successful = sum(sum(batch) for batch in results)
    total_completed = sum(len(batch) for batch in results)
    rate = total_completed / duration
    total_data = total_completed * size_bytes / 1024  # KB
    
    logger.info("----- Test Complete -----")
    logger.info(f"Completed {total_completed} requests, {successful} successful")
    logger.info(f"Total time: {duration:.2f} seconds")
    logger.info(f"Average rate: {rate:.2f} requests/second")
    logger.info(f"Total data transferred: {total_data:.2f} KB")
    logger.info(f"Data throughput: {(total_data/duration):.2f} KB/second")

if __name__ == "__main__":
    print("Script initialized")
    main()
    print("Script completed")
