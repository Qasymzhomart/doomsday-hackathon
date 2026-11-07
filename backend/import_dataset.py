import argparse
import json
from pathlib import Path
from .app import create_app
from .services import download_dataset, import_dataset

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('group_id')
    parser.add_argument('--file', type=Path)
    args = parser.parse_args()
    store = create_app().state.store
    data = json.loads(args.file.read_text(encoding='utf-8')) if args.file else download_dataset(args.group_id)
    print(json.dumps(import_dataset(store,data,args.group_id),ensure_ascii=False))
