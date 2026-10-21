"""Release integrity/isolation and lossless upgrade/rollback control checks."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from sme_fraud import release_manager as rm


class ReleaseManagerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared=tempfile.TemporaryDirectory(); cls.source=Path(cls.shared.name)/'source'; cls.source.mkdir()
        shutil.copytree(rm.ROOT/'sme_fraud',cls.source/'sme_fraud',ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(rm.ROOT/'review_ui',cls.source/'review_ui')
        (cls.source/'requirements-review-lock.txt').write_text('example==1.0\n',encoding='utf-8')
        cls.wheels=Path(cls.shared.name)/'wheels'; cls.wheels.mkdir()
        with zipfile.ZipFile(cls.wheels/'example-1.0-py3-none-any.whl','w') as wheel:
            wheel.writestr('example-1.0.dist-info/METADATA','Metadata-Version: 2.1\nName: example\nVersion: 1.0\n')

    @classmethod
    def tearDownClass(cls): cls.shared.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()

    def tearDown(self): self.temp.cleanup()

    def build(self,name='package',version='0.1.0'):
        return rm.build_release(self.source,self.wheels,self.root/name,version)

    def fake_install(self,name='installed',version='0.1.0'):
        package=self.root/('package_'+name); rm.build_release(self.source,self.wheels,package,version)
        output=self.root/name; commands=[]
        def execute(args,**kwargs):
            command=list(map(str,args)); commands.append(command)
            if '-c' in command: return json.dumps([3,12,'win32','AMD64'])
            if 'venv' in command:
                target=Path(command[-1])/'Scripts/python.exe'; target.parent.mkdir(parents=True); target.touch()
            return 'No broken requirements found.\n'
        environment=dict(prefix=str(output/'env'),base_prefix='base-python',user_site=False,packages={'example':'1.0','pip':'25'})
        with patch.object(rm,'execute',side_effect=execute),patch.object(rm,'environment_report',return_value=environment):
            receipt=rm.install_release(package,output)
        return output,receipt,commands

    def backup(self,contract):
        backup=self.root/'old_backup'; backup.mkdir()
        value=dict(version='case-management-backup-v1',runtime_contract=contract)
        value['manifest_sha256']=rm.digest(value)
        (backup/'backup_manifest.json').write_text(json.dumps(value),encoding='utf-8')
        return backup

    def deployment(self):
        root=self.root/'deployment'; root.mkdir()
        old=self.add_revision(root,'a'*32,'0.1.0')
        state=rm.commit_state(root,dict(format='sme-deployment-v1',generation=0,history=[],
            active=old['id'],active_sha256='1'*64,previous=None,previous_sha256=None),dict(action='initialize'))
        return root,old,state

    def add_revision(self,root,identifier,version):
        folder=root/'revisions'/identifier; folder.mkdir(parents=True); (folder/'data').mkdir()
        value=dict(id=identifier,installation=str(self.root/'runtime'),data=str(folder/'data'),app_version=version,
                   initial_sha256='1'*64,kind='suite')
        rm.write_record(folder/'revision.json',value)
        return value

    def test_release_binds_code_schema_assets_and_dependency_hashes(self):
        manifest=self.build(); checked=rm.verify_release(self.root/'package')
        self.assertEqual(checked['release_id'],manifest['release_id'])
        self.assertEqual(checked['schemas'],dict(review='8',p2='1'))
        self.assertEqual(checked['dependencies'],{'example':'1.0'})
        self.assertIn('--hash=sha256:',(self.root/'package/requirements.lock').read_text())
        self.assertFalse(any(name.startswith(('data/','.runtime/','reports/')) for name in checked['files']))

    def test_build_version_changes_only_packaged_version_metadata(self):
        original=(self.source/'sme_fraud/version.py').read_bytes()
        self.build(version='0.1.1+rehearsal')
        self.assertEqual(rm.literal(self.root/'package/app/sme_fraud/version.py','APP_VERSION'),'0.1.1+rehearsal')
        self.assertEqual((self.source/'sme_fraud/version.py').read_bytes(),original)

    def test_installed_asset_or_release_file_tampering_is_detected(self):
        self.build(); (self.root/'package/app/review_ui/app.js').write_text('TAMPERED')
        with self.assertRaisesRegex(ValueError,'checksum'): rm.verify_release(self.root/'package')

    def test_missing_or_wrong_version_wheel_is_rejected(self):
        empty=self.root/'empty'; empty.mkdir()
        with self.assertRaisesRegex(ValueError,'Wheelhouse'): rm.build_release(self.source,empty,self.root/'package','0.1.0')

    def test_bad_version_existing_destination_and_schema_mismatch_fail(self):
        with self.assertRaises(ValueError): self.build(version='latest')
        self.build()
        with self.assertRaises(FileExistsError): self.build()
        source=self.root/'other_source'; shutil.copytree(self.source,source)
        path=source/'sme_fraud/version.py'; path.write_text(path.read_text().replace("REVIEW_SCHEMA_VERSION = '8'","REVIEW_SCHEMA_VERSION = '9'"))
        with self.assertRaisesRegex(ValueError,'schema differs'): rm.build_release(source,self.wheels,self.root/'bad_schema','0.1.0')

    def test_zip_roundtrip_verifies_all_files(self):
        manifest=self.build(); rm.export_archive(self.root/'package',self.root/'release.zip')
        self.assertEqual(rm.unpack_archive(self.root/'release.zip',self.root/'unpacked')['release_id'],manifest['release_id'])

    def test_zip_traversal_is_rejected_before_creating_output(self):
        for index,name in enumerate(('../escape','C:/escape','folder\\..\\escape')):
            archive=self.root/f'bad{index}.zip'
            with zipfile.ZipFile(archive,'w') as output: output.writestr(name,'NO')
            with self.assertRaisesRegex(ValueError,'Unsafe'): rm.unpack_archive(archive,self.root/f'out{index}')
            self.assertFalse((self.root/f'out{index}').exists())

    def test_clean_install_uses_offline_hashes_and_separate_venv(self):
        installation,receipt,commands=self.fake_install()
        install=next(command for command in commands if 'install' in command)
        self.assertIn('--no-index',install); self.assertIn('--require-hashes',install)
        self.assertTrue(receipt['environment']['user_site'] is False)
        self.assertNotEqual(receipt['environment']['prefix'],receipt['environment']['base_prefix'])
        self.assertEqual(rm.verify_install(installation)['app_version'],'0.1.0')

    def test_failed_install_has_no_completion_receipt(self):
        self.build()
        with patch.object(rm,'execute',side_effect=RuntimeError('SIM_INSTALL_FAILURE')):
            with self.assertRaises(RuntimeError): rm.install_release(self.root/'package',self.root/'failed')
        self.assertFalse((self.root/'failed'/rm.RECEIPT).exists())

    def test_installation_cannot_modify_its_own_release_artifact(self):
        self.build()
        with self.assertRaisesRegex(ValueError,'separate'):
            rm.install_release(self.root/'package',self.root/'package/installed')
        self.assertFalse((self.root/'package/installed').exists())

    def test_installed_code_drift_is_detected(self):
        installation,_,_=self.fake_install()
        (installation/'app/sme_fraud/version.py').write_text('TAMPERED')
        with self.assertRaisesRegex(ValueError,'changed'): rm.verify_install(installation)

    def test_installed_dependency_drift_blocks_runtime_operations(self):
        installation,_,_=self.fake_install()
        with patch.object(rm,'environment_report',return_value={'packages':{'example':'2.0'}}):
            with self.assertRaisesRegex(ValueError,'drifted'): rm.runtime_call(installation,'inspect',self.root)

    def test_matching_archived_runtime_is_resolved_without_changing_backup(self):
        installation,receipt,_=self.fake_install(); backup=self.backup(receipt['manifest']['runtime_contracts']['review'])
        original=(backup/'backup_manifest.json').read_bytes()
        self.assertEqual(rm.matching_install(self.root,backup),installation)
        self.assertEqual((backup/'backup_manifest.json').read_bytes(),original)

    def test_no_matching_runtime_does_not_invent_a_migration(self):
        self.fake_install(); backup=self.backup({'unknown.py':'unknown'})
        with self.assertRaisesRegex(ValueError,'No archived'): rm.matching_install(self.root,backup)

    def test_restore_refuses_incompatible_runtime_before_executing_it(self):
        installation,_,_=self.fake_install(); backup=self.backup({'unknown.py':'unknown'})
        with patch.object(rm,'runtime_call') as call:
            with self.assertRaisesRegex(ValueError,'incompatible'): rm.restore_with(installation,backup,self.root/'out')
        call.assert_not_called()

    def test_unknown_backup_format_is_not_silently_opened(self):
        backup=self.backup({}); path=backup/'backup_manifest.json'; value=json.loads(path.read_text())
        value.pop('manifest_sha256'); value['version']='future-v99'; value['manifest_sha256']=rm.digest(value); path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'Unsupported backup'): rm.backup_requirement(backup)

    def test_holdout_is_rejected_before_manifest_read(self):
        with patch.object(Path,'read_text',side_effect=AssertionError('No holdout reads')):
            with self.assertRaisesRegex(ValueError,'005'): rm.backup_requirement(self.root/'sme_fraud_005')

    def test_upgrade_switches_only_after_unchanged_data_and_health(self):
        root,old,_=self.deployment(); new=self.add_revision(root,'b'*32,'0.1.1+rehearsal')
        with patch.object(rm,'runtime_call',return_value={'logical_sha256':'1'*64}),patch.object(rm,'make_revision',return_value=new):
            state=rm.upgrade(root,self.root/'candidate')
        self.assertEqual((state['active'],state['previous']),(new['id'],old['id']))
        self.assertEqual(state['history'][-1]['action'],'upgrade')

    def test_failed_candidate_health_keeps_active_and_records_failure(self):
        root,old,_=self.deployment()
        with patch.object(rm,'runtime_call',return_value={'logical_sha256':'1'*64}),patch.object(rm,'make_revision',side_effect=RuntimeError('SIM_HEALTH_FAILURE')):
            with self.assertRaisesRegex(RuntimeError,'SIM_HEALTH_FAILURE'): rm.upgrade(root,self.root/'candidate')
        state=rm.deployment_state(root)
        self.assertEqual(state['active'],old['id']); self.assertEqual(state['history'][-1]['action'],'upgrade_failed_active_unchanged')

    def test_concurrent_source_changes_prevent_cutover(self):
        root,old,_=self.deployment(); new=self.add_revision(root,'b'*32,'0.1.1')
        calls=iter([{'logical_sha256':'1'*64},{'status':'snapshotted'},{'logical_sha256':'2'*64}])
        with patch.object(rm,'runtime_call',side_effect=lambda *args:next(calls)),patch.object(rm,'make_revision',return_value=new):
            with self.assertRaisesRegex(RuntimeError,'Source changed'): rm.upgrade(root,self.root/'candidate')
        self.assertEqual(rm.deployment_state(root)['active'],old['id'])

    def upgraded(self):
        root,old,state=self.deployment(); new=self.add_revision(root,'b'*32,'0.1.1')
        rm.commit_state(root,dict(state,active=new['id'],previous=old['id'],active_sha256='1'*64,previous_sha256='1'*64),dict(action='upgrade'))
        return root,old,new

    def test_rollback_restores_previous_pointer_when_no_new_writes(self):
        root,old,new=self.upgraded()
        with patch.object(rm,'runtime_call',return_value={'logical_sha256':'1'*64}): state=rm.rollback(root)
        self.assertEqual((state['active'],state['previous']),(old['id'],new['id']))

    def test_rollback_with_new_writes_is_blocked_without_losing_them(self):
        root,_,new=self.upgraded()
        def call(installation,command,data): return dict(logical_sha256='2'*64 if command=='inspect' else '1'*64)
        with patch.object(rm,'runtime_call',side_effect=call):
            with self.assertRaisesRegex(RuntimeError,'Post-upgrade writes'): rm.rollback(root)
        self.assertEqual(rm.deployment_state(root)['active'],new['id'])

    def test_changed_previous_data_blocks_rollback(self):
        root,_,new=self.upgraded()
        def call(installation,command,data): return dict(logical_sha256='2'*64 if command=='probe' else '1'*64)
        with patch.object(rm,'runtime_call',side_effect=call):
            with self.assertRaisesRegex(RuntimeError,'Previous revision'): rm.rollback(root)
        self.assertEqual(rm.deployment_state(root)['active'],new['id'])

    def test_managed_service_lock_blocks_upgrade_and_rollback(self):
        root,_,_=self.upgraded()
        with rm.deployment_lock(root):
            with self.assertRaisesRegex(RuntimeError,'busy'): rm.upgrade(root,self.root/'candidate')
            with self.assertRaisesRegex(RuntimeError,'busy'): rm.rollback(root)

    def test_tampered_deployment_history_is_rejected(self):
        root,_,state=self.deployment(); state['history'][0]['action']='TAMPERED'; rm.write_record(root/'deployment.json',state)
        with self.assertRaisesRegex(ValueError,'history chain'): rm.deployment_state(root)
