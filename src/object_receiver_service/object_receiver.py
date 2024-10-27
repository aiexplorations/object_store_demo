from fastapi import FastAPI, HTTPException, File, UploadFile
from minio import Minio
import pika
import json
import os
from typing import Dict, Optional
import logging
import time
import uuid
import magic
from io import BytesIO
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Object Receiver Service")

QUEUE_NAME = os.getenv('RABBITMQ_QUEUE_NAME', 'object_queue')
BUCKET_NAME = "objects-bucket"

minio_client = None
rabbitmq_connection_params = None

# Queue names (add these right after BUCKET_NAME definition)
WRITE_QUEUE = 'object_write_queue'
READ_QUEUE = 'object_read_queue'
RESPONSE_QUEUE = 'object_response_queue'

def wait_for_services(max_retries: int = 30, delay: int = 1) -> None:
    """Wait for RabbitMQ and MinIO services to be available"""
    retry_count = 0
    while retry_count < max_retries:
        try:
            # Try connecting to RabbitMQ
            params = pika.ConnectionParameters(
                host='rabbitmq',
                port=5672,
                credentials=pika.PlainCredentials('guest', 'guest')
            )
            connection = pika.BlockingConnection(params)
            connection.close()
            logger.info("Successfully connected to RabbitMQ")
            
            # Try connecting to MinIO
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
            logger.warning(f"Waiting for services... ({str(e)})")
            time.sleep(delay)
            retry_count += 1
    
    raise Exception("Failed to connect to required services")

def process_message(ch, method, properties, body):
    try:
        logger.info(f"Received message from queue: {properties.correlation_id}")
        message = json.loads(body)
        event_type = message.get('event_type')
        payload = message.get('payload')
        request_id = message.get('request_id')
        
        logger.info(f"Processing {event_type} event with request_id: {request_id}")

        if event_type == 'upload_image':
            result = handle_upload_image(payload, request_id)  # Changed from handle_image_upload
        elif event_type == 'upload_pdf':
            result = handle_upload_pdf(payload, request_id)    # Changed from handle_pdf_upload
        elif event_type == 'create_object':
            result = handle_create_object(payload, request_id)
        else:
            logger.error(f"Unknown event type: {event_type}")
            result = {"error": "Unknown event type"}

        logger.info(f"Successfully processed {event_type} event")

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
            
        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info(f"Message processing completed for request_id: {request_id}")
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag)

def handle_create_object(payload: Dict, request_id: str):
    object_id = payload.get('object_id')
    data = payload.get('data')
    # Rest of the object creation logic
    
def handle_upload_image(payload: Dict, request_id: str):
    try:
        logger.info(f"Processing image upload request: {request_id}")
        content = bytes.fromhex(payload['content'])
        filename = payload['filename']
        
        # Generate a unique object ID
        object_id = str(uuid.uuid4())
        object_name = f"{object_id}-{filename}"
        
        # Create BytesIO object
        file_data = BytesIO(content)
        file_data.seek(0)
        
        # Detect mime type
        mime_type = magic.from_buffer(content, mime=True)
        logger.info(f"Detected MIME type: {mime_type}")
        
        if not mime_type.startswith('image/'):
            raise ValueError(f"Invalid file type. Expected image, got {mime_type}")
        
        logger.info(f"Uploading image to MinIO: {object_name}")
        minio_client.put_object(
            bucket_name=BUCKET_NAME,
            object_name=object_name,
            data=file_data,
            length=len(content),
            content_type=mime_type
        )
        
        logger.info(f"Successfully stored image: {object_name}")
        return {
            "message": "Image uploaded successfully",
            "object_id": object_id,
            "filename": filename
        }
        
    except Exception as e:
        logger.error(f"Error handling image upload: {str(e)}")
        return {"error": str(e)}

def handle_upload_pdf(payload: Dict, request_id: str):
    try:
        logger.info(f"Processing PDF upload request: {request_id}")
        content = bytes.fromhex(payload['content'])
        filename = payload['filename']
        
        # Generate a unique object ID
        object_id = str(uuid.uuid4())
        object_name = f"{object_id}-{filename}"
        
        # Create BytesIO object
        file_data = BytesIO(content)
        file_data.seek(0)
        
        # Detect mime type
        mime_type = magic.from_buffer(content, mime=True)
        logger.info(f"Detected MIME type: {mime_type}")
        
        if mime_type != 'application/pdf':
            raise ValueError(f"Invalid file type. Expected PDF, got {mime_type}")
        
        logger.info(f"Uploading PDF to MinIO: {object_name}")
        minio_client.put_object(
            bucket_name=BUCKET_NAME,
            object_name=object_name,
            data=file_data,
            length=len(content),
            content_type='application/pdf'
        )
        
        logger.info(f"Successfully stored PDF: {object_name}")
        return {
            "message": "PDF uploaded successfully",
            "object_id": object_id,
            "filename": filename
        }
        
    except Exception as e:
        logger.error(f"Error handling PDF upload: {str(e)}")
        return {"error": str(e)}

@app.on_event("startup")
async def startup_event():
    global minio_client, rabbitmq_connection, channel
    
    try:
        wait_for_services()
        
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
            heartbeat=600,  # Increase heartbeat timeout
            blocked_connection_timeout=300
        )
        rabbitmq_connection = pika.BlockingConnection(params)
        channel = rabbitmq_connection.channel()
        
        # Declare queues
        channel.queue_declare(queue=WRITE_QUEUE, durable=True)
        channel.queue_declare(queue=READ_QUEUE, durable=True)
        channel.queue_declare(queue=RESPONSE_QUEUE, durable=True)
        
        # Start consuming from write queue
        channel.basic_consume(
            queue=WRITE_QUEUE,
            on_message_callback=process_message,
            auto_ack=False  # Ensure messages aren't lost
        )
        
        # Start consuming in a background task
        asyncio.create_task(consume_messages())
        
        logger.info("Successfully initialized services")
        
    except Exception as e:
        logger.error(f"Failed to initialize service: {str(e)}")
        raise

async def consume_messages():
    """Background task to consume messages"""
    while True:
        try:
            channel.connection.process_data_events(time_limit=1)  # Process messages
            await asyncio.sleep(0.1)  # Prevent CPU overload
        except Exception as e:
            logger.error(f"Error processing messages: {str(e)}")
            await asyncio.sleep(1)  # Wait before retrying

@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint"""
    return {"status": "healthy"}

@app.post("/objects")
async def create_object(object_data: Dict):
    """
    Submit an object to be stored in MinIO
    """
    try:
        object_id = object_data.get('object_id')
        data = object_data.get('data')
        
        if not object_id or not data:
            raise HTTPException(status_code=400, detail="Invalid object format. Required fields: object_id, data")
            
        # Store in MinIO
        object_name = f"{object_id}.json"
        encoded_data = json.dumps(data).encode('utf-8')
        
        minio_client.put_object(
            BUCKET_NAME,
            object_name,
            encoded_data,
            length=len(encoded_data),
            content_type='application/json'
        )
        
        logger.info(f"Successfully stored object: {object_name}")
        return {"message": "Object stored successfully", "object_id": object_id}
        
    except Exception as e:
        logger.error(f"Error storing object: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/objects/image")
async def upload_image(file: UploadFile = File(...)):
    """
    Upload an image to be stored in MinIO
    """
    try:
        # Generate a unique object ID
        object_id = str(uuid.uuid4())
        
        # Get file content
        content = await file.read()
        
        # Check if file is an image using python-magic
        mime_type = magic.from_buffer(content, mime=True)
        if not mime_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Expected image, got {mime_type}"
            )
        
        # Store in MinIO with original filename
        object_name = f"{object_id}-{file.filename}"
        
        # Create BytesIO object and seek to start
        file_data = BytesIO(content)
        file_data.seek(0)
        
        minio_client.put_object(
            bucket_name=BUCKET_NAME,
            object_name=object_name,
            data=file_data,
            length=len(content),
            content_type=mime_type
        )
        
        logger.info(f"Successfully stored image: {object_name}")
        return {
            "message": "Image uploaded successfully",
            "object_id": object_id,
            "filename": file.filename,
            "content_type": mime_type
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error storing image: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/objects/pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF document to be stored in MinIO
    """
    try:
        logger.info(f"Starting PDF upload for file: {file.filename}")
        
        # Read file content
        content = await file.read()
        logger.info(f"File content read, size: {len(content)} bytes")
        
        # Check if file is PDF using python-magic
        mime_type = magic.from_buffer(content, mime=True)
        logger.info(f"Detected MIME type: {mime_type}")
        
        if mime_type != 'application/pdf':
            logger.warning(f"Invalid file type detected: {mime_type}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Expected PDF, got {mime_type}"
            )
        
        # Generate a unique object ID
        object_id = str(uuid.uuid4())
        object_name = f"{object_id}-{file.filename}"
        logger.info(f"Generated object name: {object_name}")
        
        # Create BytesIO object and seek to start
        file_data = BytesIO(content)
        file_data.seek(0)
        
        logger.info(f"Starting MinIO upload for object: {object_name}")
        minio_client.put_object(
            bucket_name=BUCKET_NAME,
            object_name=object_name,
            data=file_data,
            length=len(content),
            content_type='application/pdf'
        )
        
        logger.info(f"Successfully stored PDF: {object_name}")
        return {
            "message": "PDF uploaded successfully",
            "object_id": object_id,
            "filename": file.filename
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error storing PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
