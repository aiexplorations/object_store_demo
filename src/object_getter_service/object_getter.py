from fastapi import FastAPI, HTTPException, Query
from minio import Minio
from typing import Dict, List, Optional
import logging
import time
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Object Getter Service")

BUCKET_NAME = "objects-bucket"
minio_client = None

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
    """Initialize services on startup"""
    global minio_client
    
    try:
        wait_for_minio()
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
            
    except Exception as e:
        logger.error(f"Failed to initialize service: {str(e)}")
        raise

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
