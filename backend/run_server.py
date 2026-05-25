import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        # Allow large file uploads (50 MB) to stream fully without timing out
        timeout_keep_alive=120,        # seconds to keep idle connection alive
        timeout_graceful_shutdown=30,  # seconds to finish in-flight requests on shutdown
        h11_max_incomplete_event_size=0,  # disable h11 incomplete-event cap (no body-size limit at parser level)
    )
