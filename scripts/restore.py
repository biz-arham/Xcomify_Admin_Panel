import sys,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from xcomify.backup import restore_backup
p=argparse.ArgumentParser(description='Restore into a NEW EMPTY directory with writes forced off.')
p.add_argument('--backup',required=True);p.add_argument('--key',required=True);p.add_argument('--destination',required=True)
p.add_argument('--confirm',required=True,choices=['READ_ONLY_RESTORE'])
a=p.parse_args();print('Restored:',restore_backup(a.backup,a.key,a.destination))
print('Set XCOMIFY_DATA_DIR to this new directory. Verify source state before re-enabling any writes.')
