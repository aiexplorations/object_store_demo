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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Object Receiver Service")

QUEUE_NAME = os.getenv('RABBITMQ_QUEUE_NAME', 'object_queue')
BUCKET_NAME = "objects-bucket"

minio_client = None
rabbitmq_connection_params = None

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
    """Process messages from RabbitMQ and store in MinIO"""
    try:
        # Parse the message
        message = json.loads(body)
        object_id = message.get('object_id')
        object_data = message.get('data')
        
        if not object_id or not object_data:
            logger.error("Invalid message format")
            return
        
        # Store in MinIO
        object_name = f"{object_id}.json"
        data = json.dumps(object_data).encode('utf-8')
        
        minio_client.put_object(
            BUCKET_NAME,
            object_name,
            data,
            length=len(data),
            content_type='application/json'
        )
        
        logger.info(f"Successfully stored object: {object_name}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        # Negative acknowledgment - message will be requeued
        ch.basic_nack(delivery_tag=method.delivery_tag)

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global minio_client, rabbitmq_connection_params
    
    try:
        # Wait for services first
        wait_for_services()
        
        # Initialize clients after services are available
        minio_client = Minio(
            "minio:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            secure=False
        )
        
        # Ensure bucket exists
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)
            logger.info(f"Created bucket: {BUCKET_NAME}")
        
        # Initialize RabbitMQ connection
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host='rabbitmq',
                port=5672,
                credentials=pika.PlainCredentials('guest', 'guest')
            )
        )
        channel = connection.channel()
        
        # Declare queue
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)
        
        # Start consuming in a separate thread
        import threading
        def start_consuming():
            try:
                channel.start_consuming()
            except Exception as e:
                logger.error(f"Consumer thread error: {str(e)}")
        
        consumer_thread = threading.Thread(target=start_consuming, daemon=True)
        consumer_thread.start()
        
        logger.info("RabbitMQ consumer initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize service: {str(e)}")
        raise

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
        # Read file content
        content = await file.read()
        
        # Check if file is PDF using python-magic
        mime_type = magic.from_buffer(content, mime=True)
        if mime_type != 'application/pdf':
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Expected PDF, got {mime_type}"
            )
        
        # Generate a unique object ID
        object_id = str(uuid.uuid4())
        
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
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
