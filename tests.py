import argparse
import unittest
from io import BytesIO, StringIO
from unittest.mock import ANY, patch

import pytest
import requests_mock
from freezegun import freeze_time

from ccc import APIService, PrintService, get_local_filename, handle_download, handle_list, handle_upload


class TestListCLIHandler:
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


class TestUploadCLIHandler:
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


class TestDownloadCLIHandler:
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


class TestAPIService:
    def setup_method(self, method):
        self.access_token = "ACCESS_TOKEN"
        self.api_service = APIService(self.access_token)

    def test_create_new_signal_success(self):
        expected_response = {'signal_id': '123'}

        with requests_mock.Mocker() as m:
            m.post('https://app.cardiomatics.com/api/v2/signals', status_code=201, json=expected_response)

            response = self.api_service.create_new_signal('name', 'example.txt')

            assert m.last_request.headers['Private-Token'] == self.access_token
            assert response == expected_response

    def test_create_new_signal_failure(self):
        with requests_mock.Mocker() as m:
            m.post(
                'https://app.cardiomatics.com/api/v2/signals',
                status_code=401,
                json={"detail": "Incorrect authentication credentials.", "status_code": 401},
            )

            with pytest.raises(APIService.AccessDeniedError):
                self.api_service.create_new_signal('name', 'example.txt')

            assert m.last_request.headers['Private-Token'] == self.access_token

    def test_request_printout_success(self):
        with requests_mock.Mocker() as m:
            m.get(
                'https://app.cardiomatics.com/api/v2/signals/123/report/printout',
                status_code=200,
                json={'test': 'test'},
            )

            response = self.api_service.request_printout(123)

            assert m.last_request.headers['Private-Token'] == self.access_token

            assert response == {'test': 'test'}

    @pytest.mark.parametrize(
        "status_code, exception",
        [
            (401, APIService.AccessDeniedError),
            (403, APIService.NotVisitedBeforeViaPortalError),
            (500, NotImplementedError),
        ],
    )
    def test_request_printout_failure(self, status_code, exception):
        with requests_mock.Mocker() as m:
            m.get(
                'https://app.cardiomatics.com/api/v2/signals/123/report/printout',
                status_code=status_code,
                json={'test': 'test'},
            )

            with pytest.raises(exception):
                self.api_service.request_printout(123)

            assert m.last_request.headers['Private-Token'] == self.access_token

    def test_get_list_signals_page_success(self):
        with requests_mock.Mocker() as m:
            m.get(
                f'https://app.cardiomatics.com/api/v2/signals?page=1&per_page={self.api_service._PER_PAGE}&new=True',
                status_code=200,
                headers={'x-total-pages': '2'},
                json=[{'id': 1}],
            )

            last_page, response = self.api_service._get_signals_page(1, True)

            assert last_page == '2'
            assert response == [{'id': 1}]

    def test_get_list_signals_page_failure(self):
        with requests_mock.Mocker() as m:
            m.get(
                f'https://app.cardiomatics.com/api/v2/signals?page=1&per_page={self.api_service._PER_PAGE}&new=True',
                status_code=401,
            )

            with pytest.raises(APIService.AccessDeniedError):
                self.api_service._get_signals_page(1, True)

    def test_get_list_signals_batches(self):
        self.api_service._PER_PAGE = 1

        with requests_mock.Mocker() as m:
            first_response = [{'id': 1}]
            m.get(
                'https://app.cardiomatics.com/api/v2/signals?page=1&per_page=1',
                status_code=200,
                headers={'x-total-pages': '3'},
                json=first_response,
            )
            second_response = [{'id': 2}]
            m.get(
                'https://app.cardiomatics.com/api/v2/signals?page=2&per_page=1',
                status_code=200,
                headers={'x-total-pages': '3'},
                json=second_response,
            )
            third_response = [{'id': 3}]
            m.get(
                'https://app.cardiomatics.com/api/v2/signals?page=3&per_page=1',
                status_code=200,
                headers={'x-total-pages': '3'},
                json=third_response,
            )

            responses = list(self.api_service.get_list_signals_batches())

            assert responses == [first_response, second_response, third_response]

            assert m.call_count == 3


if __name__ == '__main__':
    unittest.main()
