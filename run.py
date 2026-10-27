"""Start the local-first app. No default password; bootstrap code is generated locally."""
import os,sys,argparse,threading,webbrowser,time
from urllib.request import urlopen
from urllib.parse import urlparse
from xcomify.config import Settings
from xcomify.db import Database
from xcomify.models import User
from sqlalchemy import select

def main():
    p=argparse.ArgumentParser(description='Xcomify Central Command')
    p.add_argument('--demo',action='store_true',help='Use separate synthetic demonstration workspace')
    p.add_argument('--no-browser',action='store_true')
    p.add_argument('--host',default=None)
    args=p.parse_args()
    if args.demo:os.environ['XCOMIFY_DEMO']='true'
    settings=Settings.from_env();db=Database(settings.database_url);db.migrate()
    with db.Session() as s:configured=bool(s.scalar(select(User.id).limit(1)))
    print('\nXCOMIFY CENTRAL COMMAND | '+('SYNTHETIC DEMO' if settings.demo else 'PRIVATE WORKSPACE'))
    print('Open: '+settings.base_url)
    if not configured:print('\nONE-TIME SETUP CODE: '+settings.bootstrap_token+'\nPaste this into the first-run setup screen. Do not share it.\n')
    print('Keep this server window running. Closing the browser does not stop sync; stopping this process does.')
    host=args.host or ('0.0.0.0' if settings.production else '127.0.0.1')
    if not settings.production and host not in {'127.0.0.1','localhost','::1'}:
        raise SystemExit('Local mode only binds to loopback. Configure HTTPS production mode for network access.')
    if not args.no_browser and not settings.production:
        def open_when_ready():
            for _ in range(100):
                try:
                    with urlopen(settings.base_url+'/healthz',timeout=1) as response:
                        if response.status==200: webbrowser.open(settings.base_url);return
                except Exception:time.sleep(.25)
        threading.Thread(target=open_when_ready,daemon=True).start()
    from xcomify.main import create_app
    import uvicorn
    uvicorn.run(create_app(settings,db),host=host,port=urlparse(settings.base_url).port or (8787 if not settings.production else 8080),
                access_log=False,proxy_headers=False,log_level='warning')
if __name__=='__main__':main()
