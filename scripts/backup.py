import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from xcomify.config import Settings
from xcomify.backup import create_backup
s=Settings.from_env()
print('Encrypted backup:',create_backup(s))
print('Store the backup recovery key separately:',s.data_dir/'backup-recovery.key')
