from fastapi import FastAPI, HTTPException, Query
from minio import Minio
from typing import Dict, List, Optional
import logging
import time
import os
import json
import pika
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Object Getter Service")

BUCKET_NAME = "objects-bucket"
minio_client = None
rabbitmq_connection = None
channel = None

# Add these after the BUCKET_NAME definition (around line 16)
WRITE_QUEUE = 'object_write_queue'
READ_QUEUE = 'object_read_queue'
RESPONSE_QUEUE = 'object_response_queue'

def wait_for_minio(max_retries: int = 30, delay: int = 1) -> None:
    """Wait for MinIO service to be available"""
    retry_count = 0
    while retry_count < max_retries:
        try:
            minio = Minio(
                "minio:9000",
                access_key="minioadmin",
                secret_key="minioadmin",
                secure=False
            )
            minio.list_buckets()
            logger.info("Successfully connected to MinIO")
            return
        except Exception as e:
            logger.warning(f"Waiting for MinIO... ({str(e)})")
            time.sleep(delay)
            retry_count += 1
    
    raise Exception("Failed to connect to MinIO")

@app.on_event("startup")
async def startup_event():
    global minio_client, rabbitmq_connection, channel
    
    try:
        wait_for_minio()
        
        # Initialize MinIO client
        minio_client = Minio(
            "minio:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            secure=False
        )
        
        # Ensure bucket exists
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)
            
        # Initialize RabbitMQ connection with heartbeat
        params = pika.ConnectionParameters(
            host='rabbitmq',
            credentials=pika.PlainCredentials('guest', 'guest'),
            heartbeat=600,
            blocked_connection_timeout=300
        )
        rabbitmq_connection = pika.BlockingConnection(params)
        channel = rabbitmq_connection.channel()
        
        # Declare queues
        channel.queue_declare(queue=WRITE_QUEUE, durable=True)
        channel.queue_declare(queue=READ_QUEUE, durable=True)
        channel.queue_declare(queue=RESPONSE_QUEUE, durable=True)
        
        # Start consuming from read queue
        channel.basic_consume(
            queue=READ_QUEUE,
            on_message_callback=process_message,
            auto_ack=False
        )
        
        # Create background task for message consumption
        asyncio.create_task(consume_messages())
        
        logger.info("Successfully initialized services and started message consumer")
        
    except Exception as e:
        logger.error(f"Failed to initialize service: {str(e)}")
        raise

async def consume_messages():
    """Background task to consume messages"""
    while True:
        try:
            channel.connection.process_data_events(time_limit=1)
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error processing messages: {str(e)}")
            await asyncio.sleep(1)

@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint"""
    return {"status": "healthy"}

@app.get("/objects")
async def list_objects(
    type: str = Query(..., description="Type of objects to list (json, image, pdf)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page")
) -> Dict:
    """List objects from MinIO with pagination"""
    try:
        # Calculate skip and limit for pagination
        skip = (page - 1) * page_size
        
        # Define prefix based on type
        prefix = None
        if type == "json":
            prefix = ".json"
        elif type == "image":
            prefix = "-"  # All images have UUID-filename format
        elif type == "pdf":
            prefix = "-"  # All PDFs have UUID-filename format
        else:
            raise HTTPException(status_code=400, detail="Invalid type. Must be json, image, or pdf")
            
        # Get objects with pagination
        objects = []
        count = 0
        
        for obj in minio_client.list_objects(BUCKET_NAME, recursive=True):
            if prefix and (
                (type == "json" and obj.object_name.endswith(prefix)) or
                (type in ["image", "pdf"] and obj.object_name.find(prefix) != -1)
            ):
                count += 1
                if count > skip and len(objects) < page_size:
                    # Get object metadata
                    stat = minio_client.stat_object(BUCKET_NAME, obj.object_name)
                    objects.append({
                        "name": obj.object_name,
                        "size": obj.size,
                        "last_modified": obj.last_modified.isoformat(),
                        "content_type": stat.content_type
                    })
        
        total_pages = (count + page_size - 1) // page_size
        
        return {
            "total": count,
            "total_pages": total_pages,
            "current_page": page,
            "page_size": page_size,
            "objects": objects
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error listing objects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def process_message(ch, method, properties, body):
    try:
        logger.info(f"Received message from queue: {properties.correlation_id}")
        message = json.loads(body)
        event_type = message.get('event_type')
        payload = message.get('payload')
        request_id = message.get('request_id')
        
        logger.info(f"Processing {event_type} event with request_id: {request_id}")

        if event_type == 'list_objects':
            result = handle_list_objects(payload)
            logger.info(f"List objects returned {len(result.get('objects', []))} items")
        elif event_type == 'get_object':
            result = handle_get_object(payload)
            logger.info(f"Retrieved object: {payload.get('object_id')}")
        else:
            logger.error(f"Unknown event type: {event_type}")
            result = {"error": "Unknown event type"}

        # Send response back if reply_to is specified
        if properties.reply_to:
            logger.info(f"Sending response for request_id: {request_id}")
            ch.basic_publish(
                exchange='',
                routing_key=properties.reply_to,
                body=json.dumps(result),
                properties=pika.BasicProperties(
                    correlation_id=properties.correlation_id
                )
            )
            logger.info(f"Response sent successfully for request_id: {request_id}")
            
        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info(f"Message processing completed for request_id: {request_id}")
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag)

def handle_list_objects(payload: Dict):
    type = payload.get('type')
    page = payload.get('page', 1)
    page_size = payload.get('page_size', 10)
    
    logger.info(f"Handling list objects request for type: {type}, page: {page}, page_size: {page_size}")
    
    try:
        # Calculate skip and limit for pagination
        skip = (page - 1) * page_size
        logger.info(f"Calculated skip: {skip} for pagination")
        
        # Get objects with pagination
        objects = []
        count = 0
        
        logger.info("Starting object listing from MinIO")
        for obj in minio_client.list_objects(BUCKET_NAME, recursive=True):
            # Filter by type
            if type == "pdf" and obj.object_name.lower().endswith('.pdf'):
                count += 1
                if count > skip and len(objects) < page_size:
                    logger.debug(f"Found PDF object: {obj.object_name}")
                    stat = minio_client.stat_object(BUCKET_NAME, obj.object_name)
                    objects.append({
                        "name": obj.object_name,
                        "size": obj.size,
                        "last_modified": obj.last_modified.isoformat(),
                        "content_type": stat.content_type
                    })
            elif type == "image" and any(obj.object_name.lower().endswith(ext) 
                                       for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                count += 1
                if count > skip and len(objects) < page_size:
                    stat = minio_client.stat_object(BUCKET_NAME, obj.object_name)
                    objects.append({
                        "name": obj.object_name,
                        "size": obj.size,
                        "last_modified": obj.last_modified.isoformat(),
                        "content_type": stat.content_type
                    })
            elif type == "json" and obj.object_name.lower().endswith('.json'):
                count += 1
                if count > skip and len(objects) < page_size:
                    stat = minio_client.stat_object(BUCKET_NAME, obj.object_name)
                    objects.append({
                        "name": obj.object_name,
                        "size": obj.size,
                        "last_modified": obj.last_modified.isoformat(),
                        "content_type": stat.content_type
                    })
        
        logger.info(f"Found {count} total objects of type {type}, returning {len(objects)} items")
        
        total_pages = (count + page_size - 1) // page_size
        logger.info(f"Calculated total pages: {total_pages}")
        
        return {
            "total": count,
            "total_pages": total_pages,
            "current_page": page,
            "page_size": page_size,
            "objects": objects
        }
    except Exception as e:
        logger.error(f"Error listing objects: {str(e)}")
        return {"error": str(e)}

def handle_get_object(payload: Dict):
    object_id = payload.get('object_id')
    try:
        logger.info(f"Attempting to retrieve object: {object_id}")
        
        # List objects to find the full object name
        full_object_name = None
        
        for obj in minio_client.list_objects(BUCKET_NAME):
            logger.debug(f"Checking object: {obj.object_name}")
            if obj.object_name.startswith(object_id):
                full_object_name = obj.object_name
                break
                
        if not full_object_name:
            logger.error(f"Object not found: {object_id}")
            return {"error": "Object not found"}
            
        logger.info(f"Found object: {full_object_name}")
        data = minio_client.get_object(BUCKET_NAME, full_object_name)
        content = data.read()
        content_type = data.headers.get('content-type', '')
        
        # Determine response based on content type
        if content_type == 'application/json':
            return {
                "type": "json",
                "data": json.loads(content.decode('utf-8'))
            }
        elif content_type.startswith('image/'):
            return {
                "type": "image",
                "data": content.hex(),
                "mime_type": content_type,
                "filename": full_object_name.split('-', 1)[1]  # Remove UUID prefix
            }
        elif content_type == 'application/pdf':
            return {
                "type": "pdf",
                "data": content.hex(),
                "mime_type": content_type,
                "filename": full_object_name.split('-', 1)[1]  # Remove UUID prefix
            }
        else:
            logger.error(f"Unsupported content type: {content_type}")
            return {"error": f"Unsupported content type: {content_type}"}
            
    except Exception as e:
        logger.error(f"Error getting object: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
