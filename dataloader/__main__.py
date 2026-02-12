"""Entry point for running the dataloader app."""
import uvicorn

if __name__ == "__main__":
    from dataloader.app import app
    uvicorn.run(app, host="0.0.0.0", port=8001)
