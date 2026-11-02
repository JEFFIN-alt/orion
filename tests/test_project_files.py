"""Project file API tests use disposable databases and synthetic local bytes only."""
import base64
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4
from unittest.mock import patch

import test_control_room
from orion.approvals import ApprovalService
from orion.database import Database, SCHEMA, MIGRATION_2, MIGRATION_3, MIGRATION_4, MIGRATION_5, MIGRATION_6, MIGRATION_7, MIGRATION_8
from orion.execution import ExecutionService
from orion.inputs import InputService
from orion.models import ValidationError
from orion.project_files import FILE_TYPES, MAX_FILE_BYTES, ProjectFileService
from orion.service import Service
from orion.verification import VerificationService


class ProjectFileTests(unittest.TestCase):
    def setUp(self):
        test_control_room.ControlRoomTests.setUp(self)

    close_server = test_control_room.ControlRoomTests.close_server
    get = test_control_room.ControlRoomTests.get
    post = test_control_room.ControlRoomTests.post

    def upload(self, project_id, filename, content, folder_id=None, content_type='application/octet-stream'):
        headers={'Content-Type':content_type,'Origin':self.base,'X-Orion-Token':self.token,
                 'X-Orion-Request':str(uuid4()),'X-Orion-Filename':quote(filename,safe='')}
        if folder_id: headers['X-Orion-Folder']=quote(folder_id,safe='')
        request=Request(self.base+'/api/project-files?project_id='+project_id,data=content,headers=headers,method='POST')
        return json.load(urlopen(request))

    def test_single_multiple_image_document_preview_download_and_metadata(self):
        folder=self.post('/api/project-folders',{'project_id':self.project['id'],'name':'Reference files'})
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/FioAAAAASUVORK5CYII=')
        image=self.upload(self.project['id'],'chart.PNG',png,folder['id'])['file']
        document=self.upload(self.project['id'],'notes.md',b'# Placement\nFixture text\n')['file']
        listed=self.get('/api/project-files?project_id='+self.project['id'])
        self.assertEqual({x['id'] for x in listed},{image['id'],document['id']})
        self.assertEqual(image['folder_id'],folder['id'])
        self.assertEqual(image['detected_mime'],'image/png')
        self.assertEqual(image['sha256'],hashlib.sha256(png).hexdigest())
        self.assertEqual(image['uploaded_by'],'local CEO')
        self.assertEqual(self.get('/api/project-file?project_id='+self.project['id']+'&id='+image['id'])['size'],len(png))
        preview=urlopen(self.base+'/api/project-file-preview?project_id='+self.project['id']+'&id='+image['id'])
        self.assertEqual(preview.headers.get_content_type(),'image/png')
        self.assertEqual(preview.headers.get('X-Content-Type-Options'),'nosniff')
        self.assertIn('sandbox',preview.headers.get('Content-Security-Policy'))
        self.assertEqual(preview.read(),png)
        text=urlopen(self.base+'/api/project-file-preview?project_id='+self.project['id']+'&id='+document['id'])
        self.assertEqual(text.headers.get_content_type(),'text/plain')
        self.assertEqual(text.read(),b'# Placement\nFixture text\n')
        download=urlopen(self.base+'/api/project-file-download?project_id='+self.project['id']+'&id='+document['id'])
        self.assertIn('attachment',download.headers.get('Content-Disposition'))
        self.assertEqual(download.read(),b'# Placement\nFixture text\n')
        self.assertTrue(ProjectFileService(self.db).verify_storage(self.project['id'],image['id'])['matches'])

    def test_duplicates_search_category_unassigned_and_folders(self):
        folder=self.post('/api/project-folders',{'project_id':self.project['id'],'name':'Data'})
        first=self.upload(self.project['id'],'sample.csv',b'name,score\nA,90\n',folder['id'])
        duplicate=self.upload(self.project['id'],'copy.csv',b'name,score\nA,90\n')
        self.assertFalse(first['duplicate'])
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(duplicate['file']['id'],first['file']['id'])
        self.assertEqual(len(self.get('/api/project-files?project_id='+self.project['id'])),1)
        filtered=self.get('/api/project-files?project_id='+self.project['id']+'&category=data&search=sample')
        self.assertEqual([x['id'] for x in filtered],[first['file']['id']])
        self.assertEqual(self.get('/api/project-files?project_id='+self.project['id']+'&unassigned=true')[0]['id'],first['file']['id'])
        self.assertEqual(self.get('/api/project-folders?project_id='+self.project['id'])[0]['file_count'],1)
        with self.assertRaises(HTTPError):self.post('/api/project-folder-delete',{'project_id':self.project['id'],'folder_id':folder['id']})
        ProjectFileService(self.db).update(self.project['id'],first['file']['id'],folder_id=None,move=True)
        self.post('/api/project-folder-delete',{'project_id':self.project['id'],'folder_id':folder['id']})

    def test_supported_format_mime_mismatch_size_and_path_rejections(self):
        for name,content in (('../escape.txt',b'ok'),('bad.svg',b'<svg></svg>'),('fake.png',b'not png')):
            headers={'Content-Type':'application/octet-stream','Origin':self.base,'X-Orion-Token':self.token,
                     'X-Orion-Request':str(uuid4()),'X-Orion-Filename':quote(name,safe='')}
            request=Request(self.base+'/api/project-files?project_id='+self.project['id'],data=content,headers=headers,method='POST')
            with self.assertRaises(HTTPError):urlopen(request)
        with self.assertRaises(HTTPError):
            self.upload(self.project['id'],'bad.txt',b'valid text',content_type='text/html')
        with self.assertRaises(ValidationError):
            ProjectFileService(self.db).upload_stream(self.project['id'],'large.txt',BytesIO(b''),MAX_FILE_BYTES+1)
        self.assertEqual(self.get('/api/project-files?project_id='+self.project['id']),[])

    def test_partial_upload_is_removed_and_no_metadata_is_written(self):
        files=ProjectFileService(self.db)
        with self.assertRaises(ValidationError):files.upload_stream(self.project['id'],'incomplete.txt',BytesIO(b'abc'),4)
        folder=self.db.path.parent/'projects'/self.project['id']/'assets'
        self.assertFalse(list(folder.glob('*.partial')))
        self.assertEqual(files.list(self.project['id']),[])

    def test_stale_partial_and_unregistered_blob_cleanup(self):
        assets=self.db.path.parent/'projects'/self.project['id']/'assets';assets.mkdir(parents=True)
        partial=assets/'.crashed.partial';orphan=assets/('f'*36+'.blob')
        partial.write_bytes(b'incomplete');orphan.write_bytes(b'orphan')
        old=__import__('time').time()-7200;os.utime(partial,(old,old));os.utime(orphan,(old,old))
        service=ProjectFileService(self.db)
        self.assertEqual(service.cleanup_orphans(self.project['id']),2)
        self.assertFalse(partial.exists());self.assertFalse(orphan.exists())

    def test_supported_extension_catalog_and_content_detection(self):
        zip_bytes=io.BytesIO()
        with zipfile.ZipFile(zip_bytes,'w') as archive:
            archive.writestr('[Content_Types].xml','<Types/>')
            archive.writestr('word/document.xml','<document/>')
        docx=zip_bytes.getvalue()
        zip_bytes=io.BytesIO()
        with zipfile.ZipFile(zip_bytes,'w') as archive:
            archive.writestr('[Content_Types].xml','<Types/>')
            archive.writestr('xl/workbook.xml','<workbook/>')
        xlsx=zip_bytes.getvalue()
        zip_bytes=io.BytesIO()
        with zipfile.ZipFile(zip_bytes,'w') as archive: archive.writestr('readme.txt','no extraction')
        zip_data=zip_bytes.getvalue()
        binary={'.png':b'\x89PNG\r\n\x1a\nfixture','.jpg':b'\xff\xd8\xfffixture','.jpeg':b'\xff\xd8\xfffixture2',
          '.webp':b'RIFF0000WEBPfixture','.gif':b'GIF89afixture','.pdf':b'%PDF-1.7 fixture',
          '.doc':b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1doc','.xls':b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1xls',
          '.docx':docx,'.xlsx':xlsx,'.zip':zip_data,'.rtf':b'{\\rtf1 fixture}'}
        for extension in FILE_TYPES:
            payload=binary.get(extension,('fixture '+extension).encode())
            if extension=='.json':payload=b'{"fixture":true}'
            if extension=='.xml':payload=b'<fixture/>'
            result=ProjectFileService(self.db).upload_stream(self.project['id'],'test'+extension,BytesIO(payload),len(payload))
            self.assertFalse(result['duplicate'],extension)
            self.assertEqual(result['file']['extension'],extension)
            self.assertTrue(result['file']['detected_mime'])

    def test_task_attachments_are_scoped_removable_and_historic(self):
        project_file=self.upload(self.project['id'],'requirements.txt',b'project requirements')['file']
        task=self.service.create_task(self.project['id'],'Dataset Analysis')
        other=self.service.create_project('Other Project')
        other_task=self.service.create_task(other['id'],'Other task')
        attached=self.post('/api/task-file-attach',{'project_id':self.project['id'],'file_id':project_file['id'],'task_id':task['id']})
        self.assertFalse(attached['already_attached'])
        self.assertEqual(self.get('/api/task?id='+task['id'])['files'][0]['id'],project_file['id'])
        with self.assertRaises(HTTPError):self.post('/api/task-file-attach',{'project_id':self.project['id'],'file_id':project_file['id'],'task_id':other_task['id']})
        with self.assertRaises(HTTPError):self.get('/api/project-file?project_id='+other['id']+'&id='+project_file['id'])
        with self.assertRaises(HTTPError):urlopen(Request(self.base+'/api/project-files?project_id='+self.project['id'],data=b'bad',headers={'Content-Type':'application/octet-stream'}))
        self.post('/api/task-file-detach',{'project_id':self.project['id'],'file_id':project_file['id'],'task_id':task['id']})
        self.assertEqual(self.get('/api/task?id='+task['id'])['files'],[])
        with self.db.connect() as connection:
            rows=connection.execute('SELECT attached_at,removed_at FROM project_file_tasks WHERE file_id=?',(project_file['id'],)).fetchall()
        self.assertEqual(len(rows),1);self.assertIsNotNone(rows[0]['removed_at'])

    def test_csv_file_reuses_existing_input_and_uses_normal_worker_verification(self):
        payload=b'name,score\nAda,95\n'
        project_file=self.upload(self.project['id'],'placement.csv',payload)['file']
        task=self.service.create_task(self.project['id'],'Dataset Analysis',require_approval=True)
        first=self.post('/api/project-file-csv-bind',{'project_id':self.project['id'],'file_id':project_file['id'],'task_id':task['id']})
        self.assertEqual(first['sha256'],hashlib.sha256(payload).hexdigest())
        self.assertEqual(first['configuration']['input_id'],first['input_id'])
        assignment=self.get('/api/task?id='+task['id'])['lifecycle']['assignment']
        self.assertEqual(assignment['worker_id'],'csv-profile')
        self.assertEqual(self.get('/api/task?id='+task['id'])['files'][0]['id'],project_file['id'])
        approval=ApprovalService(self.db).request(task['id'],'csv-profile','Offline fixture review')
        ApprovalService(self.db).decide(approval['id'],'approved','Reviewed fixture operation')
        execution=ExecutionService(self.db).execute(task['id'],'csv-profile')
        self.assertEqual(execution['status'],'succeeded',execution['error'])
        self.assertEqual(VerificationService(self.db).history(execution['id'])[0]['status'],'passed')
        second_task=self.service.create_task(self.project['id'],'Second CSV task',require_approval=True)
        second=self.post('/api/project-file-csv-bind',{'project_id':self.project['id'],'file_id':project_file['id'],'task_id':second_task['id']})
        self.assertEqual(second['input_id'],first['input_id'])
        with self.db.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM inputs WHERE sha256=?',(first['sha256'],)).fetchone()[0],1)

    def test_file_deletion_detaches_links_but_preserves_historical_csv_input(self):
        payload=b'a,b\n1,2\n'
        file=self.upload(self.project['id'],'dataset.csv',payload)['file']
        task=self.service.create_task(self.project['id'],'CSV task',require_approval=True)
        result=self.post('/api/project-file-csv-bind',{'project_id':self.project['id'],'file_id':file['id'],'task_id':task['id']})
        self.post('/api/project-file-delete',{'project_id':self.project['id'],'file_id':file['id'],'confirm':file['id']})
        with self.assertRaises(HTTPError):self.get('/api/project-file?project_id='+self.project['id']+'&id='+file['id'])
        self.assertEqual(self.get('/api/task?id='+task['id'])['files'],[])
        self.assertEqual(InputService(self.db).get(result['input_id'])['sha256'],result['sha256'])
        with self.db.connect() as connection:
            self.assertEqual(connection.execute('SELECT status FROM project_files WHERE id=?',(file['id'],)).fetchone()['status'],'deleted')
        self.assertFalse((self.db.path.parent/'projects'/self.project['id']/'assets'/(file['id']+'.blob')).exists())

    def test_failed_delete_quarantines_file_and_retry_finishes_cleanup(self):
        uploaded=self.upload(self.project['id'],'retained.txt',b'cleanup fixture')['file']
        files=ProjectFileService(self.db)
        original=Path.unlink
        def fail_blob(path,*args,**kwargs):
            if path.name==uploaded['stored_name']:raise PermissionError('fixture lock')
            return original(path,*args,**kwargs)
        with patch('orion.project_files.Path.unlink',new=fail_blob):
            with self.assertRaises(ValidationError):files.delete(self.project['id'],uploaded['id'])
        record=files.get(self.project['id'],uploaded['id'])
        self.assertEqual(record['status'],'quarantined')
        self.assertIn(uploaded['id'],[f['id'] for f in files.list(self.project['id'])])
        with self.assertRaises(ValidationError):files.read(self.project['id'],uploaded['id'])
        self.assertEqual(files.delete(self.project['id'],uploaded['id'])['deleted'],uploaded['id'])
        self.assertFalse((self.db.path.parent/'projects'/self.project['id']/'assets'/uploaded['stored_name']).exists())

    def test_migration_from_schema_eight_preserves_existing_input_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'legacy.sqlite3';connection=sqlite3.connect(path)
            try:
                for version,statements in enumerate((SCHEMA,MIGRATION_2,MIGRATION_3,MIGRATION_4,MIGRATION_5,MIGRATION_6,MIGRATION_7,MIGRATION_8),start=1):
                    for statement in statements:connection.execute(statement)
                    connection.execute(f'PRAGMA user_version={version}')
                connection.commit()
            finally:connection.close()
            legacy=Database(path);service=Service(legacy);project=service.create_project('Migrating');task=service.create_task(project['id'],'Existing task')
            source=Path(tmp)/'source.csv';source.write_bytes(b'x\n1\n')
            asset=InputService(legacy).import_csv(source)
            InputService(legacy).bind(task['id'],asset['id'])
            approval=ApprovalService(legacy).request(task['id'],'csv-profile','Migration fixture')
            ApprovalService(legacy).decide(approval['id'],'approved','Preserved test authorization')
            executed_task=service.create_task(project['id'],'Historical execution')
            execution=ExecutionService(legacy).execute(executed_task['id'],'project-status')
            self.assertEqual(execution['status'],'succeeded')
            legacy.initialize()
            self.assertEqual(legacy.health()['schema_version'],9)
            self.assertEqual(service.get('projects',project['id']),project)
            self.assertEqual(service.get('tasks',task['id']),task)
            self.assertEqual(InputService(legacy).get(asset['id']),asset)
            with legacy.connect() as c:
                self.assertEqual(c.execute('SELECT input_id FROM csv_operations WHERE task_id=?',(task['id'],)).fetchone()['input_id'],asset['id'])
                self.assertEqual(c.execute('SELECT status FROM approvals WHERE id=?',(approval['id'],)).fetchone()['status'],'approved')
                self.assertEqual(c.execute('SELECT status FROM executions WHERE id=?',(execution['id'],)).fetchone()['status'],'succeeded')
                self.assertIsNotNone(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_files'").fetchone())

    def test_text_preview_never_serves_html_as_active_document(self):
        uploaded=self.upload(self.project['id'],'notes.html',b'<script>unsafe()</script>')['file']
        response=urlopen(self.base+'/api/project-file-preview?project_id='+self.project['id']+'&id='+uploaded['id'])
        self.assertEqual(response.headers.get_content_type(),'text/plain')
        self.assertEqual(response.read(),b'<script>unsafe()</script>')


if __name__=='__main__':
    unittest.main()
