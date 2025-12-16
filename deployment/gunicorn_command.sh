gunicorn \            
    --workers 5 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8001 \
    --timeout 120 \
    --access-logfile /var/log/rag-chat/access.log \
    --error-logfile /var/log/rag-chat/error.log \
    app.main:app --daemon