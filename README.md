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

### Key Design Elements

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

1. **Service Separation**
   - Dedicated services for:
     - Object receiving (writes)
     - Object getting (reads)
     - Request orchestration
   - Each service runs in its own container

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
