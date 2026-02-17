"""
Sincronizar bitácora Excel con Google Drive usando Google Drive API.

SETUP:
1. pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
2. Crear proyecto en https://console.cloud.google.com/
3. Habilitar Google Drive API
4. Crear credenciales OAuth 2.0 → Descargar como credentials.json
5. Primera ejecución: se abrirá navegador para autorizar

Uso:
    python scripts/sync_bitacora_to_drive.py
"""
import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive.file']
BITACORA_PATH = "reports/H3_BITACORA_PREDICCIONES.xlsx"
BITACORA_NAME = "H3_BITACORA_PREDICCIONES.xlsx"
TOKEN_PATH = "token_gdrive.pickle"
CREDENTIALS_PATH = "credentials.json"

def get_drive_service():
    """Autenticar y obtener servicio de Google Drive."""
    creds = None
    
    # Token guardado previamente
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
    
    # Si no hay credenciales válidas, hacer login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                print(f"❌ Error: No se encuentra {CREDENTIALS_PATH}")
                print("   Descarga las credenciales OAuth 2.0 desde Google Cloud Console")
                return None
            
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Guardar token para próximas ejecuciones
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)
    
    return build('drive', 'v3', credentials=creds)

def find_file_in_drive(service, filename):
    """Buscar archivo en Google Drive por nombre."""
    try:
        results = service.files().list(
            q=f"name='{filename}' and trashed=false",
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        files = results.get('files', [])
        if files:
            return files[0]['id']
        return None
    except Exception as e:
        print(f"❌ Error buscando archivo: {e}")
        return None

def upload_to_drive(service, file_path, file_name, file_id=None):
    """Subir o actualizar archivo en Google Drive."""
    try:
        file_metadata = {'name': file_name}
        media = MediaFileUpload(file_path, 
                               mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                               resumable=True)
        
        if file_id:
            # Actualizar archivo existente
            file = service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            print(f"✅ Bitácora actualizada en Drive (ID: {file.get('id')})")
        else:
            # Crear archivo nuevo
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()
            print(f"✅ Bitácora subida a Drive")
            print(f"   ID: {file.get('id')}")
            print(f"   Link: {file.get('webViewLink')}")
            
            # Hacer el archivo accesible (opcional)
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }
            service.permissions().create(
                fileId=file.get('id'),
                body=permission
            ).execute()
            print(f"   📝 Archivo compartido públicamente (solo lectura)")
        
        return file.get('id')
    
    except Exception as e:
        print(f"❌ Error subiendo archivo: {e}")
        return None

def sync_bitacora():
    """Sincronizar bitácora local con Google Drive."""
    if not os.path.exists(BITACORA_PATH):
        print(f"❌ No se encuentra la bitácora: {BITACORA_PATH}")
        return False
    
    print("🔄 Autenticando con Google Drive...")
    service = get_drive_service()
    
    if not service:
        return False
    
    print(f"🔍 Buscando {BITACORA_NAME} en Drive...")
    file_id = find_file_in_drive(service, BITACORA_NAME)
    
    if file_id:
        print(f"   ✓ Archivo encontrado (ID: {file_id})")
        print("📤 Actualizando...")
    else:
        print("   ✗ Archivo no encontrado")
        print("📤 Subiendo nueva bitácora...")
    
    result_id = upload_to_drive(service, BITACORA_PATH, BITACORA_NAME, file_id)
    
    return result_id is not None

if __name__ == "__main__":
    import sys
    
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    
    success = sync_bitacora()
    sys.exit(0 if success else 1)
