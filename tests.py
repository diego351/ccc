import argparse
import unittest
from io import BytesIO
from unittest.mock import ANY, patch

from ccc import handle_download, handle_list, handle_upload


class TestListCLIHandler(unittest.TestCase):
    @patch('ccc.APIService.get_list_signals_batches')
    @patch('ccc.print_signals')
    def test_list_handler(self, mock_print_signals, mock_get_list_signals_batches):
        # Mock the API response data
        signals_data = [
            {"id": 1, "physician": {"name": "Dr. Smith"}, "created_at": "2023-07-29", "status": "Done", "new": False},
            # Add more signals data as needed
        ]
        mock_get_list_signals_batches.return_value = [signals_data]

        # Mock argparse.Namespace with access_token argument
        args = argparse.Namespace(access_token='YOUR_ACCESS_TOKEN')

        # Call the handle_list function with the mocked arguments
        handle_list(args)

        # Ensure that the APIService.get_list_signals_batches method was called with the proper argument
        mock_get_list_signals_batches.assert_called_once_with()

        # Ensure that print_signals was called with the correct signals data
        mock_print_signals.assert_called_once_with(signals_data)


class MockFileObject(BytesIO):
    def __init__(self, content, name):
        super().__init__(content)
        self.name = name


class TestUploadCLIHandler(unittest.TestCase):
    @patch('ccc.APIService.post_new_signal')
    @patch('ccc.APIService.upload_file_to_object_storage')
    def test_upload_handler(self, mock_upload_to_object_storage, mock_post_new_signal):
        # Mock the API response data for post_new_signal
        response_data = {
            "files": [
                {"post_fields": {"file": "file_data", "file_name": "test_signal.pdf"}, "url": "https://example.com"}
            ]
        }
        mock_post_new_signal.return_value = response_data

        # Create a custom mock file object
        signal_data = b"Your test signal data"
        signal_file = MockFileObject(signal_data, "signal_file.pdf")

        # Mock argparse.Namespace with access_token and file_path arguments
        args = argparse.Namespace(access_token='YOUR_ACCESS_TOKEN', file_path=signal_file, name="Your Signal Name")

        # Call the handle_upload function with the mocked arguments
        handle_upload(args)

        # Ensure that the APIService.post_new_signal method was called with the proper arguments
        mock_post_new_signal.assert_called_once_with("Your Signal Name", "signal_file.pdf")

        # Ensure that APIService.upload_file_to_object_storage method was called with the correct arguments
        mock_upload_to_object_storage.assert_called_once_with(
            "https://example.com", signal_file, {"file": "file_data", "file_name": "test_signal.pdf"}
        )


class TestDownloadCLIHandler(unittest.TestCase):
    @patch('ccc.APIService.get_list_signals_batches')
    @patch('ccc.APIService.request_printout')
    @patch('ccc.download_file_with_progress_bar')
    def test_download_handler(
        self,
        mock_download_file_with_progress_bar,
        mock_request_printout,
        mock_get_list_signals_batches,
    ):
        # Mock the API response data for get_list_signals_batches
        signals_data = [
            {"id": 1, "physician": {"name": "Dr. Smith"}, "created_at": "2023-07-29", "status": "Done", "new": False},
            # Add more signals data as needed
        ]
        mock_get_list_signals_batches.return_value = [signals_data]

        # Mock the API response data for request_printout
        response_data = {"url": "https://example.com", "name": "test_signal.txt"}
        mock_request_printout.return_value = response_data

        # Mock argparse.Namespace with access_token and dir_path arguments
        args = argparse.Namespace(
            access_token='YOUR_ACCESS_TOKEN', dir_path='path/to/your/download_directory', new=False
        )

        # Call the handle_download function with the mocked arguments
        handle_download(args)

        # Ensure that the APIService.get_list_signals_batches method was called with the proper arguments
        mock_get_list_signals_batches.assert_called_once_with(new=False)

        # Ensure that the APIService.request_printout method was called for each signal
        mock_request_printout.assert_called_once_with(1)

        mock_download_file_with_progress_bar.assert_called_once_with(
            ANY, "https://example.com", 'path/to/your/download_directory', ANY
        )


if __name__ == '__main__':
    unittest.main()


# TODO: osobno otestować get_local_filename
2
