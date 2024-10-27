from fastapi import FastAPI, HTTPException, File, UploadFile, Query
import pika
import json
import os
import uuid
import logging
from typing import Dict, Optional
import magic
from io import BytesIO
import asyncio
import time
from fastapi.responses import StreamingResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Object Store Orchestrator")

# Queue names
WRITE_QUEUE = 'object_write_queue'
READ_QUEUE = 'object_read_queue'
RESPONSE_QUEUE = 'object_response_queue'

class RabbitMQConnection:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.reconnect_delay = 1  # Start with 1 second delay
        self.max_reconnect_delay = 30  # Maximum delay between reconnection attempts
        
    def connect(self):
        try:
            if self.connection is None or self.connection.is_closed:
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host='rabbitmq',
                        credentials=pika.PlainCredentials('guest', 'guest'),
                        heartbeat=600,  # Increase heartbeat timeout
                        blocked_connection_timeout=300  # Add timeout for blocked connections
                    )
                )
                self.channel = self.connection.channel()
                
                # Declare queues
                self.channel.queue_declare(queue=WRITE_QUEUE, durable=True)
                self.channel.queue_declare(queue=READ_QUEUE, durable=True)
                self.channel.queue_declare(queue=RESPONSE_QUEUE, durable=True)
                
                logger.info("Successfully connected to RabbitMQ")
                self.reconnect_delay = 1  # Reset delay after successful connection
                return True
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {str(e)}")
            return False
            
    def ensure_connection(self):
        """Ensure that connection is open, reconnect if necessary"""
        while True:
            try:
                if self.connection is None or self.connection.is_closed:
                    if not self.connect():
                        logger.warning(f"Connection failed, waiting {self.reconnect_delay}s before retry")
                        time.sleep(self.reconnect_delay)
                        self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
                        continue
                return True
            except Exception as e:
                logger.error(f"Error ensuring connection: {str(e)}")
                time.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    def publish_message(self, queue, message, properties=None):
        """Publish message with automatic reconnection"""
        while True:
            try:
                if self.ensure_connection():
                    self.channel.basic_publish(
                        exchange='',
                        routing_key=queue,
                        body=message,
                        properties=properties or pika.BasicProperties(delivery_mode=2)
                    )
                    return True
            except Exception as e:
                logger.error(f"Error publishing message: {str(e)}")
                time.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

# Create global RabbitMQ connection handler
rabbitmq_handler = RabbitMQConnection()

@app.on_event("startup")
async def startup_event():
    try:
        rabbitmq_handler.connect()
        logger.info("Successfully initialized RabbitMQ connections")
    except Exception as e:
        logger.error(f"Failed to initialize service: {str(e)}")
        raise

@app.post("/objects")
async def create_object(object_data: Dict):
    """Handle object creation requests"""
    try:
        # Ensure data is in the correct format
        if 'data' not in object_data:
            raise HTTPException(status_code=400, detail="Request must include 'data' field")

        message = {
            'event_type': 'create_object',
            'payload': {
                'data': object_data['data']  # Match the format expected by handle_create_object
            },
            'request_id': str(uuid.uuid4())
        }
        
        logger.info(f"Sending create object request with payload: {message}")
        
        if rabbitmq_handler.publish_message(
            WRITE_QUEUE,
            json.dumps(message)
        ):
            return {"message": "Object creation request accepted", "request_id": message['request_id']}
        else:
            raise HTTPException(status_code=500, detail="Failed to publish message")
            
    except Exception as e:
        logger.error(f"Error queuing object creation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/objects/image")
async def upload_image(file: UploadFile = File(...)):
    """Handle image upload requests"""
    try:
        content = await file.read()
        mime_type = magic.from_buffer(content, mime=True)
        
        if not mime_type.startswith('image/'):
            raise HTTPException(status_code=400, detail=f"Invalid file type")
        
        message = {
            'event_type': 'upload_image',
            'payload': {
                'filename': file.filename,
                'content': content.hex(),  # Convert bytes to hex string
                'mime_type': mime_type
            },
            'request_id': str(uuid.uuid4())
        }
        
        if rabbitmq_handler.publish_message(
            WRITE_QUEUE,
            json.dumps(message)
        ):
            return {"message": "Image upload request accepted", "request_id": message['request_id']}
        else:
            raise HTTPException(status_code=500, detail="Failed to publish message")
            
    except Exception as e:
        logger.error(f"Error queuing image upload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/objects")
async def list_objects(
    type: str = Query(..., description="Type of objects to list (json, image, pdf)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page")
):
    try:
        request_id = str(uuid.uuid4())
        message = {
            'event_type': 'list_objects',
            'payload': {
                'type': type,
                'page': page,
                'page_size': page_size
            },
            'request_id': request_id
        }

        # Create a dedicated response queue for this request
        response_queue = f"response_{request_id}"
        response_channel = rabbitmq_handler.connection.channel()
        response_channel.queue_declare(queue=response_queue, exclusive=True, auto_delete=True)
        
        response = None
        def response_callback(ch, method, props, body):
            if props.correlation_id == request_id:
                nonlocal response
                response = json.loads(body)
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"Response received for request: {request_id}")

        # Start consuming from response queue
        consumer_tag = response_channel.basic_consume(
            queue=response_queue,
            on_message_callback=response_callback,
            auto_ack=False
        )

        # Publish request with the dedicated response queue
        logger.info(f"Publishing list request for type: {type}, request_id: {request_id}")
        if rabbitmq_handler.publish_message(
            READ_QUEUE,
            json.dumps(message),
            properties=pika.BasicProperties(
                reply_to=response_queue,
                correlation_id=request_id,
                delivery_mode=2
            )
        ):
            # Wait for response with more frequent polling
            timeout = 10  # seconds
            start_time = time.time()
            while response is None and time.time() - start_time < timeout:
                response_channel.connection.process_data_events(time_limit=0.1)
                await asyncio.sleep(0.01)

            # Clean up
            try:
                response_channel.basic_cancel(consumer_tag)  # Cancel consumer before deleting queue
                response_channel.queue_delete(queue=response_queue)
                response_channel.close()
            except Exception as e:
                logger.error(f"Error cleaning up response queue: {str(e)}")

            if response is None:
                raise HTTPException(status_code=408, detail="Request timeout")

            return response
        else:
            raise HTTPException(status_code=500, detail="Failed to publish message")
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error processing list request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/objects/{object_id}")
async def get_object(object_id: str):
    """Handle object retrieval requests"""
    try:
        request_id = str(uuid.uuid4())
        message = {
            'event_type': 'get_object',
            'payload': {
                'object_id': object_id
            },
            'request_id': request_id
        }
        
        # Create a dedicated response queue for this request
        response_queue = f"response_{request_id}"
        response_channel = rabbitmq_handler.connection.channel()
        response_channel.queue_declare(queue=response_queue, exclusive=True, auto_delete=True)
        
        response = None
        def response_callback(ch, method, props, body):
            if props.correlation_id == request_id:
                nonlocal response
                response = json.loads(body)
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"Response received for request: {request_id}")

        # Start consuming from response queue
        consumer_tag = response_channel.basic_consume(
            queue=response_queue,
            on_message_callback=response_callback,
            auto_ack=False
        )
        
        # Publish request
        logger.info(f"Publishing get request for object: {object_id}")
        if rabbitmq_handler.publish_message(
            READ_QUEUE,
            json.dumps(message),
            properties=pika.BasicProperties(
                reply_to=response_queue,
                correlation_id=request_id,
                delivery_mode=2
            )
        ):
            # Wait for response with timeout
            timeout = 10  # seconds
            start_time = time.time()
            while response is None and time.time() - start_time < timeout:
                response_channel.connection.process_data_events(time_limit=0.1)
                await asyncio.sleep(0.01)
                
            # Clean up
            try:
                response_channel.basic_cancel(consumer_tag)
                response_channel.queue_delete(queue=response_queue)
                response_channel.close()
            except Exception as e:
                logger.error(f"Error cleaning up response queue: {str(e)}")
                
            if response is None:
                raise HTTPException(status_code=408, detail="Request timeout")
                
            if "error" in response:
                raise HTTPException(status_code=404, detail=response["error"])
                
            # Handle different types of responses
            if response['type'] == 'json':
                return response['data']
            elif response['type'] in ['image', 'pdf']:
                content = bytes.fromhex(response['data'])
                return StreamingResponse(
                    BytesIO(content),
                    media_type=response['mime_type'],
                    headers={
                        "Content-Disposition": f"attachment; filename={response['filename']}"
                    }
                )
            else:
                raise HTTPException(status_code=400, detail="Unsupported object type")
                
        else:
            raise HTTPException(status_code=500, detail="Failed to publish message")
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error processing get request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/objects/pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """Handle PDF upload requests"""
    try:
        content = await file.read()
        mime_type = magic.from_buffer(content, mime=True)
        
        if mime_type != 'application/pdf':
            raise HTTPException(status_code=400, detail=f"Invalid file type")
        
        message = {
            'event_type': 'upload_pdf',
            'payload': {
                'filename': file.filename,
                'content': content.hex(),
                'mime_type': mime_type
            },
            'request_id': str(uuid.uuid4())
        }
        
        if rabbitmq_handler.publish_message(
            WRITE_QUEUE,
            json.dumps(message)
        ):
            return {"message": "PDF upload request accepted", "request_id": message['request_id']}
        else:
            raise HTTPException(status_code=500, detail="Failed to publish message")
            
    except Exception as e:
        logger.error(f"Error queuing PDF upload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
