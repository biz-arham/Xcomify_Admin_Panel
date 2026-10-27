"""Run ONLY on the owner's machine. Do not share this command's output."""
import secrets
from cryptography.fernet import Fernet

if __name__ == '__main__':
    print('PRIVATE: put these values in the deployment secret settings, not chat or Git.')
    print('XCOMIFY_ENCRYPTION_KEY=' + Fernet.generate_key().decode())
    print('XCOMIFY_BOOTSTRAP_TOKEN=' + secrets.token_urlsafe(48))
    print('Keep the encryption key stable across web/worker deploys. Store an offline recovery copy.')
