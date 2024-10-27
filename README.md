# Sangraha - Object Storage Service

A distributed object storage service built with FastAPI, RabbitMQ, and MinIO.

## System Architecture

### Backend Components
- **Storage Layer**: MinIO object storage
- **Message Queue**: RabbitMQ for async processing
- **Services**:
  - Object Getter Service (FastAPI)
  - Object Receiver Service (FastAPI)
  - Orchestrator Service (FastAPI)

### Deployment Architecture
- **Docker Swarm Mode**
  - Orchestrator Service: 1 replica
  - Object Receiver Service: 3 replicas
  - Object Getter Service: 3 replicas
  - RabbitMQ: 1 replica
  - MinIO: 1 replica
- **Local Registry**
  - Port: 5000
  - Used for service image distribution

1. **Distributed Storage**
   - Objects stored in MinIO with UUID-based naming
   - Support for three different object types (JSON, Image, PDF)
   - Content type verification using python-magic
   - Bucket-based storage organization

2. **Asynchronous Processing**
   - Three main queues:
     - object_write_queue
     - object_read_queue
     - object_response_queue
   - Message persistence enabled for reliability
   - Correlation IDs for request tracking

3. **API Design**
   - RESTful endpoints for object operations
   - Support for file uploads with MIME type validation
   - Pagination support for object listing
   - Health check endpoints

## Design Choices

### Performance Metrics
Current throughput varies based on the size of the objects being written. Smaller objects are written faster, as can be expected. The below test writes 100KB objects.


```bash
aiexplorations@DESKTOP-A6JND41 MINGW64 /c/Github/object_store_demo (master)
$ python src/test/test.py 500 10 --debug
Script initialized
2024-10-28 02:04:08,733 - INFO - Starting load test with 500 total requests
2024-10-28 02:04:08,733 - INFO - Using 8 processes for concurrent execution
2024-10-28 02:04:14,909 - INFO - ----- Test Complete -----
2024-10-28 02:04:14,909 - INFO - Completed 500 requests, 500 successful
2024-10-28 02:04:14,909 - INFO - Total time: 6.18 seconds
2024-10-28 02:04:14,909 - INFO - Average rate: 80.97 requests/second
Script completed
```

```bash
aiexplorations@DESKTOP-A6JND41 MINGW64 /c/Github/object_store_demo (master)
$ python src/test/test.py 500 25 --debug
Script initialized
2024-10-28 02:09:33,444 - INFO - Starting load test with 500 total requests
2024-10-28 02:09:33,444 - INFO - Using 8 processes for concurrent execution
2024-10-28 02:09:37,214 - INFO - ----- Test Complete -----
2024-10-28 02:09:37,214 - INFO - Completed 500 requests, 500 successful
2024-10-28 02:09:37,214 - INFO - Total time: 3.77 seconds
2024-10-28 02:09:37,214 - INFO - Average rate: 132.64 requests/second
Script completed
```

```bash
$ python src/test/test.py 500 50 --debug
Script initialized
2024-10-28 02:10:02,731 - INFO - Starting load test with 500 total requests
2024-10-28 02:10:02,731 - INFO - Using 8 processes for concurrent execution
2024-10-28 02:10:06,658 - INFO - ----- Test Complete -----
2024-10-28 02:10:06,659 - INFO - Completed 500 requests, 500 successful
2024-10-28 02:10:06,659 - INFO - Total time: 3.93 seconds
2024-10-28 02:10:06,659 - INFO - Average rate: 127.32 requests/second
Script completed
```
The below test writes 2KB-4KB objects.

```bash
$ python src/test/test.py 100 20 --size 2048 --debug
Script initialized
2024-10-28 02:14:01,463 - INFO - Starting load test with 100 total requests
2024-10-28 02:14:01,463 - INFO - Using 8 processes for concurrent execution
2024-10-28 02:14:01,463 - INFO - Request size: ~2048 bytes
2024-10-28 02:14:03,212 - INFO - ----- Test Complete -----
2024-10-28 02:14:03,213 - INFO - Completed 100 requests, 100 successful
2024-10-28 02:14:03,213 - INFO - Total time: 1.75 seconds
2024-10-28 02:14:03,214 - INFO - Average rate: 57.16 requests/second
2024-10-28 02:14:03,214 - INFO - Total data transferred: 200.00 KB
2024-10-28 02:14:03,214 - INFO - Data throughput: 114.33 KB/second
Script completed
```
```bash
$ python src/test/test.py 100 20 --size 4096 --debug
Script initialized
2024-10-28 02:15:36,758 - INFO - Starting load test with 100 total requests
2024-10-28 02:15:36,758 - INFO - Using 8 processes for concurrent execution
2024-10-28 02:15:36,758 - INFO - Request size: ~4096 bytes
2024-10-28 02:15:38,574 - INFO - ----- Test Complete -----
2024-10-28 02:15:38,574 - INFO - Completed 100 requests, 100 successful
2024-10-28 02:15:38,574 - INFO - Total time: 1.82 seconds
2024-10-28 02:15:38,574 - INFO - Average rate: 55.07 requests/second
2024-10-28 02:15:38,574 - INFO - Total data transferred: 400.00 KB
2024-10-28 02:15:38,574 - INFO - Data throughput: 220.28 KB/second
Script completed
```
And below, we test ~1MB objects.

```bash
$ python src/test/test.py 100 20 --size 1048576 --debug
Script initialized
2024-10-28 02:17:11,844 - INFO - Starting load test with 100 total requests
2024-10-28 02:17:11,844 - INFO - Using 8 processes for concurrent execution
2024-10-28 02:17:11,844 - INFO - Request size: ~1048576 bytes
2024-10-28 02:17:20,565 - INFO - ----- Test Complete -----
2024-10-28 02:17:20,565 - INFO - Completed 100 requests, 100 successful
2024-10-28 02:17:20,565 - INFO - Total time: 8.72 seconds
2024-10-28 02:17:20,565 - INFO - Average rate: 11.47 requests/second
2024-10-28 02:17:20,565 - INFO - Total data transferred: 102400.00 KB
2024-10-28 02:17:20,565 - INFO - Data throughput: 11741.98 KB/second
Script completed
```
The below test writes ~3MB objects, 1000 of them, 50 at a time.

```bash
$ python src/test/test.py 1000 50 --size 3145728 --debug
Script initialized
2024-10-28 02:18:21,976 - INFO - Starting load test with 1000 total requests
2024-10-28 02:18:21,976 - INFO - Using 8 processes for concurrent execution
2024-10-28 02:18:21,976 - INFO - Request size: ~3145728 bytes
2024-10-28 02:23:33,847 - INFO - ----- Test Complete -----
2024-10-28 02:23:33,848 - INFO - Completed 1000 requests, 1000 successful
2024-10-28 02:23:33,848 - INFO - Total time: 311.87 seconds
2024-10-28 02:23:33,849 - INFO - Average rate: 3.21 requests/second
2024-10-28 02:23:33,849 - INFO - Total data transferred: 3072000.00 KB
2024-10-28 02:23:33,850 - INFO - Data throughput: 9850.23 KB/second
Script completed
```


- Scalability targets:
  - Writes: 1000+ requests/minute - perhaps we should be clear about the size of the objects being written?
  - Reads: 500+ requests/minute - again, perhaps we should be clear about the size of the objects being read?

2. **Storage Strategy**
   - MinIO for object persistence
   - UUID-based object naming with original filenames
   - MIME type validation before storage
   - Automatic bucket creation on service startup

3. **Message Queue Integration**
   - RabbitMQ with durable queues
   - Heartbeat monitoring (600s timeout)
   - Async message processing with background tasks
   - Request-response pattern using reply queues

## Technical Implementation

### Services Configuration
- Python 3.9 base images
- FastAPI framework for all services
- Common dependencies:
  - fastapi
  - uvicorn
  - pika (RabbitMQ client)
  - minio
  - python-magic for file type detection

### Error Handling
- MIME type validation
- Service availability checks
- Request timeouts
- Dead letter queues for failed operations

### Monitoring
- Health check endpoints
- Logging with python-json-logger
- Request tracking with correlation IDs

## Scale Considerations & Improvement Opportunities

### Current Capabilities
- Supports multiple file types (JSON, Image, PDF)
- Handles concurrent requests through async processing
- Service-specific scaling possible through containerization
- Current scale: 
  - Writes: Hundreds per minute
  - Reads: Hundreds per minute
- Target scale:
  - Writes: Thousands per minute
  - Reads: Hundreds per minute

### Potential Improvements
1. **Performance Optimizations**
   - Implement caching layer
   - Add read replicas for MinIO
   - Optimize large file handling

2. **Scalability Enhancements**
   - Horizontal scaling of service instances
   - Load balancing implementation
   - Connection pooling for MinIO and RabbitMQ

3. **Reliability & Monitoring**
   - Enhanced error handling
   - Comprehensive metrics collection
   - Circuit breakers for external services

4. **Feature Additions**
   - Object versioning
   - Enhanced metadata search
   - Compression support

## Frontend
To be implemented
