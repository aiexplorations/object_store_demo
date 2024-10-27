# Sangraha - Object Storage Service

A distributed object storage service built with FastAPI, RabbitMQ, and MinIO.

## System Architecture

### Backend Components
- **Storage Layer**: MinIO object storage
- **Message Queue**: RabbitMQ for async processing
- **Services**:
  - Object Getter Service (FastAPI)
  - Object Receiver Service (FastAPI)

### Key Design Elements
1. **Distributed Storage**
   - Objects stored in MinIO with content-addressable storage
   - Support for three different object types (JSON, Image, PDF)
   - Metadata stored separately from object data
   - Support for large file uploads through chunking

2. **Asynchronous Processing**
   - Upload requests queued via RabbitMQ
   - Separate services for read and write operations
   - Background workers for object processing

3. **API Design**
   - RESTful endpoints for object operations
   - Streaming support for large objects
   - Health check and monitoring endpoints

## Design Choices

1. **Service Separation**
   - Split read/write services for independent scaling
   - Loose coupling through message queue

2. **Storage Strategy**
   - MinIO for object persistence (S3-compatible)
   - Content-addressable storage for deduplication
   - Chunked upload support for large files

3. **Message Queue Integration**
   - RabbitMQ for reliable async processing
   - Dead letter queues for failed operations
   - Message persistence for system reliability

## Scale Considerations & Improvement Opportunities

### Scale Target
- Writes: Thousands per minute
- Reads: Hundreds per minute

### Potential Improvements

1. **Performance Optimizations**
   - Implement caching layer (e.g., Redis)
   - Add read replicas for MinIO
   - Introduce CDN for frequently accessed objects

2. **Scalability Enhancements**
   - Horizontal scaling of service instances
   - Sharding strategy for object storage
   - Load balancing improvements

3. **Reliability & Monitoring**
   - Enhanced error handling and retry mechanisms
   - Comprehensive metrics collection
   - Automated failover capabilities

4. **Feature Additions**
   - Object versioning support
   - Compression for storage efficiency
   - Enhanced metadata search capabilities

## Frontend
To be implemented
