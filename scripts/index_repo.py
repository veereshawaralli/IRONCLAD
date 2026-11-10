"""Explicit budgeted AST embedding index build; requires production extras."""
import argparse
import os
from pathlib import Path
from ironclad.knowledge import VectorIndex
from ironclad.store import Store

parser=argparse.ArgumentParser()
parser.add_argument('--repo',type=Path,required=True)
parser.add_argument('--budget',type=float,default=1.0)
args=parser.parse_args()
if not 0<args.budget<=10:
    parser.error('budget must be between zero and ten dollars')
store=Store(Path(os.environ.get('IRONCLAD_DB','.ironclad/events.db')))
index=VectorIndex()
try:
    print('Indexed',index.index(args.repo,store,args.budget),'AST chunks')
finally:
    index.db.close()
    store.db.close()
