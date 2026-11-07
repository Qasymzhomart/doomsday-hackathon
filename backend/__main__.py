import os
import uvicorn
from .app import create_app

if __name__ == '__main__':
    uvicorn.run(create_app(), host='127.0.0.1', port=int(os.getenv('PORT','8000')))
