"""Project-scoped, non-executable local file library."""
import hashlib
import codecs
import json
import os
import time
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from .inputs import InputService, DEFAULT_LIMITS, read_bounded
from .models import NotFoundError, ValidationError
from .service import Service, timestamp

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_PROJECT_BYTES = 512 * 1024 * 1024
CHUNK_SIZE = 64 * 1024

FILE_TYPES = {
    '.png': ('image', 'image/png'), '.jpg': ('image', 'image/jpeg'), '.jpeg': ('image', 'image/jpeg'),
    '.webp': ('image', 'image/webp'), '.gif': ('image', 'image/gif'),
    '.pdf': ('document', 'application/pdf'), '.doc': ('document', 'application/msword'),
    '.docx': ('document', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    '.txt': ('document', 'text/plain'), '.md': ('document', 'text/markdown'), '.rtf': ('document', 'application/rtf'),
    '.csv': ('data', 'text/csv'), '.xls': ('data', 'application/vnd.ms-excel'),
    '.xlsx': ('data', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
    '.json': ('data', 'application/json'), '.xml': ('data', 'application/xml'),
    '.py': ('development', 'text/x-python'), '.js': ('development', 'text/javascript'),
    '.html': ('development', 'text/html'), '.css': ('development', 'text/css'),
    '.sql': ('development', 'application/sql'), '.yaml': ('development', 'application/yaml'),
    '.yml': ('development', 'application/yaml'), '.toml': ('development', 'application/toml'),
    '.zip': ('archive', 'application/zip'),
}
TEXT_EXTENSIONS = {'.txt', '.md', '.rtf', '.csv', '.json', '.xml', '.py', '.js', '.html', '.css', '.sql', '.yaml', '.yml', '.toml'}
IMAGE_SIGNATURES = {
    '.png': lambda b: b.startswith(b'\x89PNG\r\n\x1a\n'),
    '.jpg': lambda b: b.startswith(b'\xff\xd8\xff'), '.jpeg': lambda b: b.startswith(b'\xff\xd8\xff'),
    '.gif': lambda b: b.startswith((b'GIF87a', b'GIF89a')),
    '.webp': lambda b: len(b) >= 12 and b[:4] == b'RIFF' and b[8:12] == b'WEBP',
}


def valid_id(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError('Invalid project file identifier') from exc


def validate_name(value, *, preserve_extension=None):
    if not isinstance(value, str) or not value or len(value) > 255 or value in ('.', '..'):
        raise ValidationError('Filename must contain 1..255 safe characters')
    if any(ch in value for ch in ('/', '\\', ':', '\x00')) or any(ord(ch) < 32 for ch in value):
        raise ValidationError('Filename must not contain path separators or control characters')
    extension = Path(value).suffix.lower()
    if preserve_extension is None and extension not in FILE_TYPES:
        raise ValidationError('File extension is not supported')
    if preserve_extension is not None and extension != preserve_extension:
        raise ValidationError('Renamed display name must keep the original file extension')
    return value


def _project_assets_dir(database, project_id, *, create=False):
    base = database.path.resolve().parent / 'projects'
    project_dir = base / valid_id(project_id)
    assets = project_dir / 'assets'
    for folder in (base, project_dir, assets):
        if folder.exists() and (folder.is_symlink() or folder.resolve() != folder.absolute()):
            raise ValidationError('Project storage directory redirects outside its managed location')
    if create:
        assets.mkdir(parents=True, exist_ok=True)
    return assets


def _detect_mime(extension, prefix, path=None):
    if extension in IMAGE_SIGNATURES:
        if not IMAGE_SIGNATURES[extension](prefix):
            raise ValidationError('File content does not match its image extension')
        return FILE_TYPES[extension][1], 'content-signature'
    if extension == '.pdf':
        if not prefix.startswith(b'%PDF-'):
            raise ValidationError('File content does not match PDF format')
        return FILE_TYPES[extension][1], 'content-signature'
    if extension == '.zip' or extension in ('.docx', '.xlsx'):
        valid_zip_signature=prefix.startswith((b'PK\x03\x04',b'PK\x05\x06',b'PK\x07\x08'))
        if not valid_zip_signature or (extension in ('.docx','.xlsx') and not prefix.startswith(b'PK\x03\x04')):
            raise ValidationError('File content does not match ZIP-based format')
        try:
            with zipfile.ZipFile(path) as archive:
                entries=archive.infolist()
                if len(entries)>10000:
                    raise ValidationError('Archive contains too many entries')
                names={entry.filename for entry in entries}
                if extension=='.docx' and not {'[Content_Types].xml','word/document.xml'}<=names:
                    raise ValidationError('ZIP contents do not match DOCX format')
                if extension=='.xlsx' and not {'[Content_Types].xml','xl/workbook.xml'}<=names:
                    raise ValidationError('ZIP contents do not match XLSX format')
        except (OSError,zipfile.BadZipFile) as exc:
            raise ValidationError('File is not a valid ZIP-based format') from exc
        return FILE_TYPES[extension][1], 'content-signature'
    if extension in ('.doc', '.xls'):
        if not prefix.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
            raise ValidationError('File content does not match legacy Office format')
        return FILE_TYPES[extension][1], 'content-signature'
    if extension == '.rtf':
        if not prefix.lstrip().startswith(b'{\\rtf'):
            raise ValidationError('File content does not match RTF format')
        return FILE_TYPES[extension][1], 'content-signature'
    if extension in TEXT_EXTENSIONS:
        if extension == '.xml' and prefix.strip() and not prefix.lstrip().startswith((b'<', b'<?xml')):
            raise ValidationError('File content does not look like XML')
        return FILE_TYPES[extension][1], 'utf8-content'
    return FILE_TYPES[extension][1], 'content-signature'


class ProjectFileService:
    def __init__(self, database):
        self.database = database

    def _event(self, connection, project_id, file_id, event_type, details=None):
        connection.execute('INSERT INTO project_file_events VALUES (?,?,?,?,?,?)',
                           (str(uuid4()), project_id, file_id, event_type,
                            json.dumps(details or {}, sort_keys=True), timestamp()))

    def _project(self, connection, project_id):
        return Service(self.database)._get(connection, 'projects', valid_id(project_id))

    def cleanup_orphans(self, project_id, *, minimum_age_seconds=3600):
        """Remove stale unregistered upload blobs left by a terminated upload process."""
        project_id=valid_id(project_id)
        assets=_project_assets_dir(self.database,project_id)
        if not assets.exists(): return 0
        with self.database.connect() as connection:
            self._project(connection,project_id)
            registered={row['stored_name'] for row in connection.execute('SELECT stored_name FROM project_files WHERE project_id=?',(project_id,))}
        cutoff=time.time()-minimum_age_seconds
        removed=0
        for path in assets.iterdir():
            partial=path.name.startswith('.') and path.name.endswith('.partial')
            blob=path.name.endswith('.blob') and path.name not in registered
            if not (partial or blob): continue
            try:
                if path.lstat().st_mtime < cutoff:
                    path.unlink()
                    removed+=1
            except FileNotFoundError:
                continue
        return removed

    def upload_stream(self, project_id, filename, stream, content_length, *, folder_id=None):
        project_id = valid_id(project_id)
        filename = validate_name(filename)
        extension = Path(filename).suffix.lower()
        if type(content_length) is not int or not 1 <= content_length <= MAX_FILE_BYTES:
            raise ValidationError(f'File size must be 1..{MAX_FILE_BYTES} bytes')
        folder_id = valid_id(folder_id) if folder_id else None
        asset_id = str(uuid4())
        assets = _project_assets_dir(self.database, project_id)
        partial = assets / ('.' + asset_id + '.partial')
        target = assets / (asset_id + '.blob')
        digest = hashlib.sha256()
        received = 0
        prefix = b''
        decoder=codecs.getincrementaldecoder('utf-8-sig')() if extension in TEXT_EXTENSIONS and extension!='.rtf' else None
        stored = False
        registered = False
        try:
            with self.database.connect() as connection:
                self._project(connection, project_id)
                if folder_id:
                    folder = connection.execute('SELECT project_id FROM project_file_folders WHERE id=?', (folder_id,)).fetchone()
                    if folder is None or folder['project_id'] != project_id:
                        raise ValidationError('Folder does not belong to this project')
                total = connection.execute("SELECT coalesce(sum(size),0) FROM project_files WHERE project_id=? AND status='active'", (project_id,)).fetchone()[0]
                if total + content_length > MAX_PROJECT_BYTES:
                    raise ValidationError(f'Project file storage limit is {MAX_PROJECT_BYTES} bytes')
            assets = _project_assets_dir(self.database, project_id, create=True)
            with partial.open('xb') as output:
                while received < content_length:
                    block = stream.read(min(CHUNK_SIZE, content_length - received))
                    if not block:
                        raise ValidationError('Upload ended before the declared file size')
                    received += len(block)
                    if decoder is not None:
                        try: decoder.decode(block,final=False)
                        except UnicodeDecodeError as exc: raise ValidationError('Text files must be UTF-8 encoded') from exc
                    digest.update(block)
                    if len(prefix) < 8192:
                        prefix += block[:8192 - len(prefix)]
                    output.write(block)
                if decoder is not None:
                    try: decoder.decode(b'',final=True)
                    except UnicodeDecodeError as exc: raise ValidationError('Text files must be UTF-8 encoded') from exc
                output.flush()
                os.fsync(output.fileno())
            mime, detection = _detect_mime(extension, prefix, partial)
            sha256 = digest.hexdigest()
            with self.database.connect() as connection:
                self._project(connection, project_id)
                if folder_id:
                    folder = connection.execute('SELECT project_id FROM project_file_folders WHERE id=?', (folder_id,)).fetchone()
                    if folder is None or folder['project_id'] != project_id:
                        raise ValidationError('Folder does not belong to this project')
                duplicate = connection.execute("SELECT * FROM project_files WHERE project_id=? AND sha256=? AND status='active'", (project_id, sha256)).fetchone()
                if duplicate:
                    return {'duplicate': True, 'file': self._public(dict(duplicate))}
                total = connection.execute("SELECT coalesce(sum(size),0) FROM project_files WHERE project_id=? AND status='active'", (project_id,)).fetchone()[0]
                if total + received > MAX_PROJECT_BYTES:
                    raise ValidationError(f'Project file storage limit is {MAX_PROJECT_BYTES} bytes')
            os.link(partial, target)
            stored = True
            relative = f'projects/{project_id}/assets/{asset_id}.blob'
            imported_at = timestamp()
            with self.database.connect(write=True) as connection:
                self._project(connection, project_id)
                if folder_id:
                    folder = connection.execute('SELECT project_id FROM project_file_folders WHERE id=?', (folder_id,)).fetchone()
                    if folder is None or folder['project_id'] != project_id:
                        raise ValidationError('Folder does not belong to this project')
                duplicate = connection.execute("SELECT * FROM project_files WHERE project_id=? AND sha256=? AND status='active'", (project_id, sha256)).fetchone()
                if duplicate:
                    return {'duplicate': True, 'file': self._public(dict(duplicate))}
                total = connection.execute("SELECT coalesce(sum(size),0) FROM project_files WHERE project_id=? AND status='active'", (project_id,)).fetchone()[0]
                if total + received > MAX_PROJECT_BYTES:
                    raise ValidationError(f'Project file storage limit is {MAX_PROJECT_BYTES} bytes')
                connection.execute('''INSERT INTO project_files
                  (id,project_id,folder_id,original_name,display_name,stored_name,storage_relative_path,
                   extension,detected_mime,mime_detection,size,sha256,uploaded_at,uploaded_by,description,status,csv_input_id,import_status)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (asset_id,project_id,folder_id,filename,filename,asset_id+'.blob',relative,extension,mime,detection,
                   received,sha256,imported_at,'local CEO','', 'active',None,'not_imported' if extension=='.csv' else 'not_applicable'))
                self._event(connection, project_id, asset_id, 'uploaded', {'size': received, 'sha256': sha256})
            registered = True
            return {'duplicate': False, 'file': self.get(project_id, asset_id)}
        finally:
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
            # A DB failure after publication must not leave an unregistered blob.
            if stored and not registered:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _public(row):
        return {key: row[key] for key in ('id','project_id','folder_id','original_name','display_name','stored_name',
                'storage_relative_path','extension','detected_mime','mime_detection','size','sha256','uploaded_at',
                'uploaded_by','description','status','csv_input_id','import_status') if key in row}

    def list(self, project_id, *, search='', category='all', folder_id=None, unassigned=False):
        project_id = valid_id(project_id)
        if not isinstance(search, str) or len(search) > 200:
            raise ValidationError('Search must be at most 200 characters')
        if category not in ('all','images','documents','data','development','archives'):
            raise ValidationError('Unsupported file category')
        self.cleanup_orphans(project_id)
        with self.database.connect() as connection:
            self._project(connection, project_id)
            sql = "SELECT f.*,d.name folder_name FROM project_files f LEFT JOIN project_file_folders d ON d.id=f.folder_id WHERE f.project_id=? AND f.status IN ('active','quarantined')"
            params = [project_id]
            if search:
                sql += ' AND (lower(f.display_name) LIKE ? ESCAPE \'\\\' OR lower(f.original_name) LIKE ? ESCAPE \'\\\')'
                needle='%'+search.lower().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
                params.extend((needle,needle))
            if folder_id:
                sql += ' AND f.folder_id=?'; params.append(valid_id(folder_id))
            if unassigned:
                sql += ' AND NOT EXISTS(SELECT 1 FROM project_file_tasks a WHERE a.file_id=f.id AND a.removed_at IS NULL)'
            rows = [dict(row) for row in connection.execute(sql+' ORDER BY f.uploaded_at DESC,f.id', params)]
            for row in rows:
                row['tasks'] = [dict(r) for r in connection.execute('''SELECT t.id,t.title FROM project_file_tasks a
                  JOIN tasks t ON t.id=a.task_id WHERE a.file_id=? AND a.removed_at IS NULL ORDER BY t.title''',(row['id'],))]
        if category != 'all':
            category_name = {'images':'image','documents':'document','data':'data','development':'development','archives':'archive'}[category]
            rows = [row for row in rows if FILE_TYPES[row['extension']][0] == category_name]
        return rows

    def folders(self, project_id):
        project_id = valid_id(project_id)
        with self.database.connect() as connection:
            self._project(connection, project_id)
            return [dict(row) for row in connection.execute('''SELECT d.id,d.project_id,d.name,d.created_at,count(f.id) file_count
              FROM project_file_folders d LEFT JOIN project_files f ON f.folder_id=d.id AND f.status IN ('active','quarantined')
              WHERE d.project_id=? GROUP BY d.id ORDER BY d.name COLLATE NOCASE''',(project_id,))]

    def create_folder(self, project_id, name):
        project_id = valid_id(project_id)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or name.strip() in ('.','..') or any(c in name for c in ('/','\\','\x00')):
            raise ValidationError('Folder name must be 1..100 characters without path separators')
        folder_id = str(uuid4())
        with self.database.connect(write=True) as connection:
            self._project(connection, project_id)
            try:
                connection.execute('INSERT INTO project_file_folders VALUES (?,?,?,?)',(folder_id,project_id,name.strip(),timestamp()))
            except Exception as exc:
                if 'UNIQUE' in str(exc): raise ValidationError('A folder with that name already exists') from None
                raise
            self._event(connection,project_id,None,'folder_created',{'folder_id':folder_id,'name':name.strip()})
        return {'id':folder_id,'project_id':project_id,'name':name.strip()}

    def delete_folder(self, project_id, folder_id):
        project_id, folder_id = valid_id(project_id), valid_id(folder_id)
        with self.database.connect(write=True) as connection:
            self._project(connection, project_id)
            folder = connection.execute('SELECT name FROM project_file_folders WHERE id=? AND project_id=?',(folder_id,project_id)).fetchone()
            if folder is None: raise NotFoundError('Folder not found in this project')
            if connection.execute("SELECT 1 FROM project_files WHERE folder_id=? AND status IN ('active','quarantined') LIMIT 1",(folder_id,)).fetchone():
                raise ValidationError('Move or delete files from this folder first')
            connection.execute("UPDATE project_files SET folder_id=NULL WHERE folder_id=? AND status='deleted'",(folder_id,))
            connection.execute('DELETE FROM project_file_folders WHERE id=?',(folder_id,))
            self._event(connection,project_id,None,'folder_deleted',{'folder_id':folder_id,'name':folder['name']})
        return {'deleted':folder_id}

    def get(self, project_id, file_id):
        project_id,file_id = valid_id(project_id),valid_id(file_id)
        with self.database.connect() as connection:
            self._project(connection,project_id)
            row = connection.execute("SELECT f.*,d.name folder_name FROM project_files f LEFT JOIN project_file_folders d ON d.id=f.folder_id WHERE f.id=? AND f.project_id=? AND f.status IN ('active','quarantined')",(file_id,project_id)).fetchone()
            if row is None: raise NotFoundError('Project file not found')
            result = self._public(dict(row)); result['folder_name']=row['folder_name']
            result['tasks']=[dict(r) for r in connection.execute('''SELECT t.id,t.title FROM project_file_tasks a JOIN tasks t ON t.id=a.task_id
              WHERE a.file_id=? AND a.removed_at IS NULL ORDER BY t.title''',(file_id,))]
            return result

    def read(self, project_id, file_id):
        record = self.get(project_id,file_id)
        if record['status']!='active': raise ValidationError('Quarantined project files cannot be read, previewed or downloaded')
        expected = f"projects/{record['project_id']}/assets/{record['id']}.blob"
        if record['storage_relative_path'] != expected or record['stored_name'] != record['id']+'.blob':
            raise ValidationError('Project file storage record is invalid')
        path = _project_assets_dir(self.database,record['project_id']) / record['stored_name']
        data = read_bounded(path,MAX_FILE_BYTES)
        if len(data) != record['size'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValidationError('Project file digest or size mismatch')
        return record,data

    def update(self, project_id, file_id, *, display_name=None, description=None, folder_id=None, move=False):
        record = self.get(project_id,file_id)
        fields=[]; values=[]; changed={}
        if display_name is not None:
            display_name=validate_name(display_name,preserve_extension=record['extension'])
            fields.append('display_name=?'); values.append(display_name); changed['display_name']=display_name
        if description is not None:
            if not isinstance(description,str) or len(description)>4000: raise ValidationError('Description must be at most 4000 characters')
            fields.append('description=?'); values.append(description); changed['description']=description
        if move:
            new_folder = valid_id(folder_id) if folder_id else None
            if new_folder:
                with self.database.connect() as connection:
                    row=connection.execute('SELECT project_id FROM project_file_folders WHERE id=?',(new_folder,)).fetchone()
                if row is None or row['project_id']!=record['project_id']: raise ValidationError('Folder does not belong to this project')
            fields.append('folder_id=?'); values.append(new_folder); changed['folder_id']=new_folder
        if not fields: raise ValidationError('No file changes supplied')
        with self.database.connect(write=True) as connection:
            current=connection.execute("SELECT 1 FROM project_files WHERE id=? AND project_id=? AND status='active'",(record['id'],record['project_id'])).fetchone()
            if current is None: raise NotFoundError('Project file not found')
            connection.execute('UPDATE project_files SET '+','.join(fields)+' WHERE id=? AND project_id=?',( *values, record['id'], record['project_id']))
            self._event(connection,record['project_id'],record['id'],'metadata_updated',changed)
        return self.get(project_id,file_id)

    def attach(self, project_id, file_id, task_id):
        project_id,file_id,task_id=valid_id(project_id),valid_id(file_id),valid_id(task_id)
        with self.database.connect(write=True) as connection:
            project=self._project(connection,project_id)
            file=connection.execute("SELECT id FROM project_files WHERE id=? AND project_id=? AND status='active'",(file_id,project['id'])).fetchone()
            if file is None: raise NotFoundError('Project file not found')
            task=Service(self.database)._get(connection,'tasks',task_id)
            if task['project_id']!=project['id']: raise ValidationError('Task belongs to another project')
            existing=connection.execute('SELECT id FROM project_file_tasks WHERE file_id=? AND task_id=? AND removed_at IS NULL',(file_id,task_id)).fetchone()
            if existing: return {'id':existing['id'],'file_id':file_id,'task_id':task_id,'already_attached':True}
            link_id=str(uuid4())
            connection.execute('INSERT INTO project_file_tasks VALUES (?,?,?, ?,NULL)',(link_id,file_id,task_id,timestamp()))
            self._event(connection,project_id,file_id,'task_attached',{'task_id':task_id,'link_id':link_id})
        return {'id':link_id,'file_id':file_id,'task_id':task_id,'already_attached':False}

    def detach(self, project_id, file_id, task_id):
        project_id,file_id,task_id=valid_id(project_id),valid_id(file_id),valid_id(task_id)
        with self.database.connect(write=True) as connection:
            self._project(connection,project_id)
            file=connection.execute('SELECT id FROM project_files WHERE id=? AND project_id=?',(file_id,project_id)).fetchone()
            task=Service(self.database)._get(connection,'tasks',task_id)
            if file is None or task['project_id']!=project_id: raise NotFoundError('File/task association not found in this project')
            row=connection.execute('SELECT id FROM project_file_tasks WHERE file_id=? AND task_id=? AND removed_at IS NULL',(file_id,task_id)).fetchone()
            if row is None: raise NotFoundError('Active task attachment not found')
            connection.execute('UPDATE project_file_tasks SET removed_at=? WHERE id=?',(timestamp(),row['id']))
            self._event(connection,project_id,file_id,'task_detached',{'task_id':task_id,'link_id':row['id']})
        return {'detached':True,'file_id':file_id,'task_id':task_id}

    def task_attachments(self, task_id):
        task_id=valid_id(task_id)
        with self.database.connect() as connection:
            task=Service(self.database)._get(connection,'tasks',task_id)
            rows=connection.execute('''SELECT f.*,d.name folder_name FROM project_file_tasks a
              JOIN project_files f ON f.id=a.file_id LEFT JOIN project_file_folders d ON d.id=f.folder_id
              WHERE a.task_id=? AND a.removed_at IS NULL AND f.status='active' ORDER BY a.attached_at''',(task_id,))
            return [self._public(dict(row)) | {'folder_name':row['folder_name']} for row in rows]

    def task_attachment_history(self, task_id):
        task_id=valid_id(task_id)
        with self.database.connect() as connection:
            task=Service(self.database)._get(connection,'tasks',task_id)
            return [dict(row) for row in connection.execute('''SELECT a.id,a.file_id,f.original_name,f.display_name,f.status,
              a.attached_at,a.removed_at FROM project_file_tasks a JOIN project_files f ON f.id=a.file_id
              WHERE a.task_id=? ORDER BY a.attached_at,a.id''',(task_id,))]

    def ensure_csv_input(self, project_id, file_id):
        record,data=self.read(project_id,file_id)
        if record['extension']!='.csv': raise ValidationError('Only CSV files can be connected to csv-profile')
        if len(data)>DEFAULT_LIMITS['max_bytes']: raise ValidationError('CSV file exceeds the existing 10 MiB CSV input limit')
        inputs=InputService(self.database)
        if record['csv_input_id']:
            try:
                asset,existing=inputs.read(record['csv_input_id'])
                if existing==data:
                    return asset
            except (NotFoundError,ValidationError,OSError):
                pass
        with self.database.connect() as connection:
            candidates=[dict(row) for row in connection.execute('SELECT * FROM inputs WHERE sha256=? AND size=? ORDER BY imported_at,id',(record['sha256'],record['size']))]
        asset=None
        for candidate in candidates:
            try:
                verified,existing=inputs.read(candidate['id'])
                if existing==data:
                    asset=verified; break
            except (NotFoundError,ValidationError,OSError):
                continue
        if asset is None:
            path=_project_assets_dir(self.database,record['project_id'])/record['stored_name']
            asset=inputs.import_csv(path,original_name=record['original_name'])
        with self.database.connect(write=True) as connection:
            current=connection.execute("SELECT sha256,status FROM project_files WHERE id=? AND project_id=?",(record['id'],record['project_id'])).fetchone()
            if current is None or current['status']!='active' or current['sha256']!=record['sha256']:
                raise ValidationError('Project file changed during CSV input binding')
            connection.execute("UPDATE project_files SET csv_input_id=?,import_status='imported' WHERE id=?",(asset['id'],record['id']))
            self._event(connection,record['project_id'],record['id'],'csv_input_linked',{'input_id':asset['id'],'sha256':asset['sha256']})
        return asset

    def delete(self, project_id, file_id):
        project_id,file_id=valid_id(project_id),valid_id(file_id)
        with self.database.connect(write=True) as connection:
            self._project(connection,project_id)
            row=connection.execute("SELECT storage_relative_path,stored_name,status FROM project_files WHERE id=? AND project_id=? AND status IN ('active','quarantined')",(file_id,project_id)).fetchone()
            if row is None: raise NotFoundError('Project file not found')
            if row['status']=='active':
                connection.execute("UPDATE project_files SET status='quarantined' WHERE id=?",(file_id,))
                now=timestamp()
                active=[r['id'] for r in connection.execute('SELECT id FROM project_file_tasks WHERE file_id=? AND removed_at IS NULL',(file_id,))]
                connection.execute('UPDATE project_file_tasks SET removed_at=? WHERE file_id=? AND removed_at IS NULL',(now,file_id))
                self._event(connection,project_id,file_id,'quarantined',{'detached_link_ids':active})
        path=_project_assets_dir(self.database,project_id)/row['stored_name']
        try:
            if path.exists() or path.is_symlink():
                if path.is_symlink() or path.resolve()!=path.absolute(): raise ValidationError('File storage path redirects outside its project')
                path.unlink()
        except OSError as exc:
            raise ValidationError('File was quarantined but storage cleanup failed; retry after inspecting local storage') from exc
        with self.database.connect(write=True) as connection:
            connection.execute("UPDATE project_files SET status='deleted' WHERE id=? AND status='quarantined'",(file_id,))
            self._event(connection,project_id,file_id,'deleted',{})
        return {'deleted':file_id,'historical_input_preserved':True}

    def verify_storage(self, project_id, file_id):
        record,data=self.read(project_id,file_id)
        return {'file_id':record['id'],'size':len(data),'recorded_size':record['size'],
                'sha256':hashlib.sha256(data).hexdigest(),'recorded_sha256':record['sha256'],
                'matches':len(data)==record['size'] and hashlib.sha256(data).hexdigest()==record['sha256']}
