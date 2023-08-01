import argparse
import unittest
from io import BytesIO, StringIO
from unittest.mock import ANY, patch

from freezegun import freeze_time

from ccc import APIService, PrintService, get_local_filename, handle_download, handle_list, handle_upload


class TestListCLIHandler(unittest.TestCase):
    @patch('ccc.APIService.get_list_signals_batches')
    @patch('ccc.PrintService.print_signals')
    def test_list_handler(self, print_signals, get_list_signals_batches):
        signals_data = [
            {"id": 1, "physician": {"name": "Dr. Smith"}, "created_at": "2023-07-29", "status": "Done", "new": False},
        ]
        get_list_signals_batches.return_value = [signals_data]

        args = argparse.Namespace(access_token='ACCESS_TOKEN')

        handle_list(args)

        get_list_signals_batches.assert_called_once_with(new=None)

        print_signals.assert_called_once_with(signals_data)

    def test_print_signals(self):
        signals_data = [
            {
                "id": 1,
                "physician": {"name": "Dr. Smithson"},
                "created_at": "2023-07-29",
                "status": "Done",
                "new": False,
            },
            {
                "id": 2,
                "physician": {"name": "Dr. Johnson"},
                "created_at": "2023-07-23",
                "status": "Done",
                "new": True,
            },
        ]
        with patch('sys.stdout', new=StringIO()) as fake_out:
            PrintService.print_signals(signals_data)
            printed = fake_out.getvalue()

        assert printed == (
            '  ID  Name          Created at    Status    New\n'
            '----  ------------  ------------  --------  -----\n'
            '   1  Dr. Smithson  2023-07-29    Done      False\n'
            '   2  Dr. Johnson   2023-07-23    Done      True\n'
        )


class MockFileObject(BytesIO):
    def __init__(self, content, name):
        super().__init__(content)
        self.name = name


class TestUploadCLIHandler(unittest.TestCase):
    @patch('ccc.APIService.create_new_signal')
    @patch('ccc.APIService.upload_file_to_object_storage')
    def test_upload_handler(self, upload_to_object_storage, create_new_signal):
        create_new_signal.return_value = {
            "files": [
                {"post_fields": {"file": "file_data", "file_name": "test_signal.pdf"}, "url": "https://example.com"}
            ]
        }

        signal_file = MockFileObject(b"file content", "signal_file.pdf")

        args = argparse.Namespace(access_token='ACCESS_TOKEN', file_path=signal_file, name="name")

        handle_upload(args)

        create_new_signal.assert_called_once_with("name", "signal_file.pdf")

        upload_to_object_storage.assert_called_once_with(
            "https://example.com", signal_file, {"file": "file_data", "file_name": "test_signal.pdf"}
        )


class TestDownloadCLIHandler(unittest.TestCase):
    @patch('ccc.APIService.get_list_signals_batches')
    @patch('ccc.APIService.request_printout')
    @patch('ccc.download_file_with_progress_bar')
    def test_download_handler(
        self,
        download_file_with_progress_bar,
        request_printout,
        get_list_signals_batches,
    ):
        get_list_signals_batches.return_value = [
            [
                {
                    "id": 1,
                    "physician": {"name": "Dr. Smith"},
                    "created_at": "2023-07-29",
                    "status": "Done",
                    "new": False,
                },
            ]
        ]  # NOTE: list of lists

        request_printout.return_value = {"url": "https://example.com", "name": "test_signal.pdf"}

        args = argparse.Namespace(access_token='ACCESS_TOKEN', dir_path='/my/path', new=False)

        handle_download(args)

        get_list_signals_batches.assert_called_once_with(new=False)

        request_printout.assert_called_once_with(1)

        download_file_with_progress_bar.assert_called_once_with(ANY, "https://example.com", '/my/path', ANY)

    @patch('ccc.APIService.get_list_signals_batches')
    @patch('ccc.APIService.request_printout')
    @patch('ccc.download_file_with_progress_bar')
    def test_download_handler_downloads_only_new_signals(
        self,
        download_file_with_progress_bar,
        request_printout,
        get_list_signals_batches,
    ):
        get_list_signals_batches.return_value = [
            [
                {
                    "id": 2,
                    "physician": {"name": "Dr. Smith"},
                    "created_at": "2023-07-29",
                    "status": "Done",
                    "new": True,
                },
            ]
        ]

        request_printout.return_value = {"url": "https://example.com", "name": "test_signal.pdf"}

        args = argparse.Namespace(access_token='ACCESS_TOKEN', dir_path='/my/path', new=True)

        handle_download(args)

        get_list_signals_batches.assert_called_once_with(new=True)

        download_file_with_progress_bar.assert_called_once_with(ANY, "https://example.com", '/my/path', ANY)

    @freeze_time('2023-01-01T00:00:00')
    def test_get_local_filename(self):
        assert get_local_filename('test.pdf') == 'test-2023-01-01T00:00:00.pdf'


if __name__ == '__main__':
    unittest.main()
