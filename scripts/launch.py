"""First-run helper: creates a private virtualenv; installs pinned requirements once."""
from pathlib import Path
import hashlib,os,subprocess,sys
ROOT=Path(__file__).resolve().parent.parent

def main():
    if sys.version_info<(3,11):
        raise SystemExit('Python 3.11 or newer is required. This build was tested with Python 3.13.')
    os.chdir(ROOT)
    env=ROOT/'.venv';interpreter=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not interpreter.exists():
        print('Creating the application environment...')
        subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
    requirements=ROOT/'requirements.lock'
    stamp=env/'xcomify-requirements.sha256';fingerprint=hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text().strip()!=fingerprint:
        print('Installing pinned dependencies. Internet access is needed for this first setup.')
        subprocess.run([str(interpreter),'-m','pip','install','-r',str(requirements)],check=True)
        stamp.write_text(fingerprint)
    command=[str(interpreter),str(ROOT/'run.py'),*sys.argv[1:]]
    print('Starting Xcomify. Keep this window open while using the software.')
    return subprocess.call(command)

if __name__=='__main__':
    try:sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print('\nSetup failed. Check your internet connection and the error shown above. No existing Sheet was changed.')
        sys.exit(exc.returncode)
    except KeyboardInterrupt:print('\nStopped. Your local database remains saved.');sys.exit(0)
