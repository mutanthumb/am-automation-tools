#!/usr/bin/env python
import os
import time
import unittest
import zipfile

import amclient
import vcr

from aips import create_dip
from tests.tests_helpers import TmpDir


SS_URL = "http://192.168.168.192:8000"
SS_USER_NAME = "test"
SS_API_KEY = "7021334bee4c9155c07e531608dd28a9d8039420"

AIP_UUID = "216dd8a6-c366-41f8-b11e-0c70814b3992"
TRANSFER_NAME = "transfer"
THIS_DIR = os.path.abspath(os.path.dirname(__file__))
TMP_DIR = os.path.join(THIS_DIR, ".tmp-create-dip")
OUTPUT_DIR = os.path.join(TMP_DIR, "output")


class TestCreateDip(unittest.TestCase):
    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_create_dip_download_aip_success.yaml"
    )
    def test_extract_aip_success(self):
        """Test that we can download and extract an AIP."""
        with TmpDir(TMP_DIR):
            # Download the AIP first
            aip_path = amclient.AMClient(
                aip_uuid=AIP_UUID,
                ss_url=SS_URL,
                ss_user_name=SS_USER_NAME,
                ss_api_key=SS_API_KEY,
                directory=TMP_DIR,
            ).download_aip()
            # Then test extraction
            aip_dir = create_dip.extract_aip(aip_path, AIP_UUID, TMP_DIR)
            assert aip_dir == f"{TMP_DIR}/{TRANSFER_NAME}-{AIP_UUID}"
            assert os.path.isdir(aip_dir)

    def test_extract_aip_fail(self):
        """Test that an extraction fails with a bad path."""
        aip_dir = create_dip.extract_aip("bad_path", AIP_UUID, TMP_DIR)
        assert aip_dir is None

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_create_dip_download_aip_success.yaml"
    )
    @unittest.mock.patch.dict(os.environ, {"TZ": "UTC"})
    def test_create_dip_success(self):
        """
        Test full DIP creation:
            - AIP download
            - AIP extraction
            - DIP folder creation
            - METS file creation
            - Objects folder creation
            - ZIP file creation
            - Files inside ZIP created with original
              filename and lastmodified date
        """
        with TmpDir(TMP_DIR):
            # Download the AIP first
            aip_path = amclient.AMClient(
                aip_uuid=AIP_UUID,
                ss_url=SS_URL,
                ss_user_name=SS_USER_NAME,
                ss_api_key=SS_API_KEY,
                directory=TMP_DIR,
            ).download_aip()
            # Extract it
            aip_dir = create_dip.extract_aip(aip_path, AIP_UUID, TMP_DIR)
            # Test DIP creation
            dip_dir = create_dip.create_dip(
                aip_dir, AIP_UUID, OUTPUT_DIR, "atom", "zipped-objects"
            )
            assert dip_dir == f"{OUTPUT_DIR}/{TRANSFER_NAME}-{AIP_UUID}"
            assert os.path.isdir(dip_dir)
            # Check a METS file exists
            dip_mets = f"{dip_dir}/METS.{AIP_UUID}.xml"
            assert os.path.isfile(dip_mets)
            # And an objects directory
            dip_objects = f"{dip_dir}/objects"
            assert os.path.isdir(dip_objects)
            # With a ZIP file with the transfer name inside
            dip_objects_zip = f"{dip_objects}/{TRANSFER_NAME}.zip"
            assert os.path.isfile(dip_objects_zip)
            # Check that the zipped files have their original filename
            # and the last modified date from the AIP
            aip_files = [
                {"filename": "file2.jpg", "lastmodified": None},
                {"filename": "folder1/file5.txt", "lastmodified": 1510849551},
                {"filename": "folder1/folder2/file6.txt", "lastmodified": 1510849568},
                {"filename": "folder1/folder2/file7.txt", "lastmodified": 1510849573},
                {"filename": "file.txt", "lastmodified": 1510849451},
                {"filename": "folder/file4.png", "lastmodified": None},
                {"filename": "folder/file3.txt", "lastmodified": 1510849507},
            ]
            zip_file = zipfile.ZipFile(dip_objects_zip, "r")
            for zip_file_info in zip_file.infolist():
                # Strip transfer name and '/', the main folder will end empty
                filename = zip_file_info.filename[len(TRANSFER_NAME) + 1 :]
                # Ignore main folder, METS, submissionDocumentation and directories
                if (
                    not filename
                    or filename == f"METS.{AIP_UUID}.xml"
                    or filename.startswith("submissionDocumentation")
                    or filename.endswith("/")
                ):
                    continue
                lastmodified = int(time.mktime(zip_file_info.date_time + (0, 0, -1)))
                # Find file by filename in file info
                aip_file_info = next(
                    (x for x in aip_files if x["filename"] == filename), None
                )
                assert aip_file_info
                # Check lastmodified date, if present in file info
                aip_lastmodified = aip_file_info["lastmodified"]
                if not aip_lastmodified:
                    continue
                # Somehow, between getting the last modified date from the METS file,
                # setting it in the DIP files with os.utime(), zipping the files and
                # getting it in here with infolist(), a mismatch of a second is found
                # in some of the files. No milliseconds are involved in the process so
                # this should not be a rounding issue.
                assert aip_lastmodified - 1 <= lastmodified <= aip_lastmodified + 1

    def test_create_dip_fail_no_aip_dir(self):
        """Test that a DIP creation fails with a bad path."""
        dip_dir = create_dip.create_dip(
            "bad_path", AIP_UUID, OUTPUT_DIR, "atom", "zipped-objects"
        )
        assert dip_dir is None

    def test_get_original_relpath_objects_dir(self):
        path = "%transferDirectory%objects/folder1/file5.txt"

        assert create_dip.get_original_relpath(path) == "folder1/file5.txt"

    def test_get_original_relpath_data_dir(self):
        path = "%transferDirectory%data/folder1/file5.txt"

        assert create_dip.get_original_relpath(path) == "folder1/file5.txt"

    def test_get_original_relpath_warn_invalid_prefix(self):
        path = "%transferDirectory%datas/folder1/file5.txt"

        assert create_dip.get_original_relpath(path) is None
