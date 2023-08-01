# /usr/bin/python3
import argparse
import errno
import os
from datetime import datetime
from io import FileIO
from pathlib import Path
from typing import List, Optional

import requests
from tabulate import tabulate
from tqdm import tqdm

INVALUD_TOKEN_MESSAGE = "\nInvalid token"
LIST_ACTION = 'list'
UPLOAD_ACTION = 'upload'
DOWNLOAD_ACTION = 'download'


class DiskFullError(Exception):
    pass


class APIService:
    _CARTIOMATICS_API_URL = 'https://app.cardiomatics.com'
    _SIGNALS_ENDPOINT = '/api/v2/signals'
    _REQUEST_PRINTOUT_ENDPOINT = '/api/v2/signals/{}/report/printout'
    _PER_PAGE = 50
    _access_token = None
    _api_client = None

    class AccessDeniedError(Exception):
        pass

    class NotVisitedBeforeViaPortalError(Exception):
        pass

    class ObjectStorageUploadError(Exception):
        pass

    def __init__(self, access_token: str):
        self._access_token = access_token
        self._api_client = requests.Session()

        self._api_client.headers['Private-Token'] = self._access_token

    def _get_signals_page(self, page: int, new: Optional[bool] = None):
        """Requests list signals endpoint

        :param page: pagination page
        :param new: new filter flag, defaults to None
        :raises self.AccessDeniedError:
        :return: tuple (<last_page_index>, <JSON dict>)
        """
        url = self._CARTIOMATICS_API_URL + self._SIGNALS_ENDPOINT

        params = {'page': page, 'per_page': self._PER_PAGE}
        if new:
            params['new'] = new

        response = self._api_client.get(url, params=params)

        if response.status_code == 401:
            raise self.AccessDeniedError

        elif response.status_code == 200:
            last_page = response.headers['x-total-pages']
            return (last_page, response.json())

        else:
            raise NotImplementedError

    def create_new_signal(self, name: str, file_name: str):
        """Requests create signal endpoint

        :param name: signal name
        :param file_name: file name
        :raises self.AccessDeniedError:
        :raises NotImplementedError:
        :return: response dictionary (JSON dict)
        """
        url = self._CARTIOMATICS_API_URL + self._SIGNALS_ENDPOINT

        response = self._api_client.post(url, json={'name': name, 'file_names_list': [file_name]})

        if response.status_code == 401:
            raise self.AccessDeniedError

        elif response.status_code == 201:
            return response.json()

        else:
            raise NotImplementedError

    def upload_file_to_object_storage(self, url: str, file: FileIO, post_fields: dict):
        """Uploads file to object store as multipart/form request

        :param url: object storage url
        :param file: file object (opened)
        :param post_fields: object storage credentials
        :raises self.ObjectStorageUploadError:
        """
        response = requests.post(url, files={'file': file}, data=post_fields, stream=True)

        if not response.ok:
            raise self.ObjectStorageUploadError

        return response

    def get_list_signals_batches(self, new: Optional[bool] = None):
        """Direct pagination iterator over get signals endpoint

        :param new: filtering by new signals, defaults to None
        :yield: List of signals (JSON)
        """
        last_page, data = self._get_signals_page(1, new=new)
        yield data

        for page in range(2, int(last_page) + 1):
            _, data = self._get_signals_page(page, new=new)
            yield data

    def request_printout(self, signal_id: int):
        """Requests printout for given signal_id

        :param signal_id:
        :raises self.AccessDeniedError:
        :raises self.NotVisitedBeforeViaPortalError:
        :raises NotImplementedError:
        :return: printout response (JSON)
        """
        url = self._CARTIOMATICS_API_URL + self._REQUEST_PRINTOUT_ENDPOINT.format(signal_id)
        response = self._api_client.get(url)

        if response.status_code == 401:
            raise self.AccessDeniedError

        if response.status_code == 403:
            raise self.NotVisitedBeforeViaPortalError

        elif response.status_code == 200:
            return response.json()

        else:
            raise NotImplementedError

    def get_file(self, url: str):
        """Gets given url

        :param url: URL string
        :raises NotImplementedError:
        :return: requests.Response
        """
        response = requests.get(url, stream=True)

        if response.ok:
            return response

        else:
            raise NotImplementedError


class PrintService:
    """Handles printing signals to console"""

    @classmethod
    def signals_object_to_column(cls, signal: dict):
        return [
            signal.get('id'),
            signal.get('physician').get('name'),
            signal.get('created_at'),
            signal.get('status'),
            signal.get('new'),
        ]

    @classmethod
    def print_signals(cls, signals: List[dict]):
        """Prints formated signals table

        :param signals: signals dict
        """
        columned_data_list = [cls.signals_object_to_column(signal) for signal in signals]

        print(
            tabulate(
                columned_data_list,
                headers=["ID", "Name", "Created at", "Status", "New"],
                tablefmt="signals-table",
                showindex=False,
            )
        )


def get_list_signals_batches_auth_handled(api_service: APIService, new: Optional[bool] = None):
    """Similar to APIService.get_list_signals_batches(), but handles invalid authorisation

    :param new: filtering by new signals, defaults to None
    :yield: List of signals (JSON)
    """
    iterator = iter(api_service.get_list_signals_batches(new=new))

    while True:
        try:
            signals_batch = next(iterator)

        except APIService.AccessDeniedError:
            print(INVALUD_TOKEN_MESSAGE)
            exit(1)

        except StopIteration:
            break

        yield signals_batch


def download_file_with_progress_bar(api_service: APIService, url: str, dir_path: str, file_name: str):
    """Downloads file with a progress bar

    :param api_service: APIService instance
    :param url: source url
    :param dir_path: download directory
    :param file_name: destination file name
    :raises DiskFullError: when disk is full
    """
    CHUNK_SIZE = 1024
    download_dest = os.path.join(dir_path, file_name)

    try:
        with api_service.get_file(url) as response:
            total = int(response.headers.get('content-length', 0))
            with open(download_dest, 'wb') as file, tqdm(
                desc=file_name,
                total=total,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024,
            ) as bar:
                for data in response.iter_content(chunk_size=CHUNK_SIZE):
                    size = file.write(data)
                    bar.update(size)

    except OSError as e:
        if e.errno == errno.ENOSPC:
            raise DiskFullError

        else:
            raise


def create_parser():
    """Creates parser that handles CLI arguments"""

    def dir_path(path):
        """Directory validator

        :param path: directory path ex. /tmp
        :return: path if path is directory
        """
        if os.path.isdir(path):
            return path
        else:
            print('Not a directory')
            exit(1)

    ACCESS_TOKEN_ARGUMENT = '--access-token'
    FILE_PATH_ARGUMENT = '--file-path'
    NAME_ARGUMENT = '--name'
    DIR_PATH_ARGUMENT = '--dir-path'
    NEW_ARGUMENT = '--new'

    parser = argparse.ArgumentParser(description='Cardiomatics Console Client')
    subparsers = parser.add_subparsers(dest='action', title='Available actions', required=True)

    list_parser = subparsers.add_parser(LIST_ACTION, help='List signals')
    list_parser.add_argument(
        ACCESS_TOKEN_ARGUMENT,
        required=True,
        help='Access token for authentication',
    )

    upload_parser = subparsers.add_parser(UPLOAD_ACTION, help='Upload signal')
    upload_parser.add_argument(
        FILE_PATH_ARGUMENT, help='File path to the signal file', type=argparse.FileType('rb'), required=True
    )
    upload_parser.add_argument(NAME_ARGUMENT, help="Name", required=True)
    upload_parser.add_argument(ACCESS_TOKEN_ARGUMENT, required=True, help='Access token for authentication')

    download_parser = subparsers.add_parser(DOWNLOAD_ACTION, help='Download action')
    download_parser.add_argument(ACCESS_TOKEN_ARGUMENT, required=True, help='Access token for authentication')
    download_parser.add_argument(DIR_PATH_ARGUMENT, help='Download directory path', type=dir_path, required=True)
    download_parser.add_argument(
        NEW_ARGUMENT,
        action='store_true',
        help='Filtering by only new signals',
        default=False,
    )

    return parser


def handle_list(args: argparse.Namespace):
    """List action main handler

    :param args: argparse arguments, required: access_token:str
    """
    api_service = APIService(args.access_token)
    signals = []

    signal_batches_iterator = iter(get_list_signals_batches_auth_handled(api_service))

    for signals_batch in signal_batches_iterator:
        for signal in signals_batch:
            signals.append(signal)

    print('\nList of signals:')
    PrintService.print_signals(signals)


def handle_upload(args: argparse.Namespace):
    """Upload action main handler

    :param args: argparse arguments required: access_token:str, name:str, file_path: str
    """
    api_service = APIService(args.access_token)

    file_name = os.path.basename(args.file_path.name)

    try:
        response_dict = api_service.create_new_signal(args.name, file_name)
        print('Sucessfully created object on Cardiomatics API')

    except api_service.AccessDeniedError:
        print(INVALUD_TOKEN_MESSAGE)
        exit(1)

    post_fields = response_dict.get('files')[0].get('post_fields')
    object_storage_url = response_dict.get('files')[0].get('url')

    print('Uploading file to object store...')
    try:
        api_service.upload_file_to_object_storage(object_storage_url, args.file_path, post_fields)

    except api_service.ObjectStorageUploadError:
        print('Object store error')
        exit(1)

    print('Upload successful!')


def get_local_filename(base_file_name: str):
    """Helper function that creates unique filename to download
    example-filename.pdf -> example-filename-2023-01-01T00:00:00.pdf

    :param base_file_name: server file name
    :return: download file name
    """
    file_without_extension = Path(base_file_name).stem
    file_extension = Path(base_file_name).suffix
    now = datetime.now().isoformat()
    return f'{file_without_extension}-{now}{file_extension}'


def handle_download(args: argparse.Namespace):
    """Download action main handler

    :param args: argparse arguments. required: access_token:str, new:bool, dir_path:str
    """
    api_service = APIService(args.access_token)

    signal_batches_iterator = iter(get_list_signals_batches_auth_handled(api_service, new=args.new))

    downloaded_reports = []
    not_downloaded_reports = []

    for signals_batch in signal_batches_iterator:
        for signal in signals_batch:
            status = signal.get('status')
            if status not in ['Warning', 'Done']:
                not_downloaded_reports.append(signal)
                continue

            try:
                response = api_service.request_printout(signal.get('id'))

            except APIService.NotVisitedBeforeViaPortalError:
                not_downloaded_reports.append(signal)
                print('Not visited by app before')
                continue

            url = response.get('url')
            file_name = response.get('name')
            local_file_name = get_local_filename(file_name)

            try:
                download_file_with_progress_bar(api_service, url, args.dir_path, local_file_name)

            except DiskFullError:
                print("Disk full, can't download")
                exit(1)
            downloaded_reports.append(signal)

    if downloaded_reports:
        print(f'\nDownloaded signal reports: {len(downloaded_reports)}')
        PrintService.print_signals(downloaded_reports)

    if not_downloaded_reports:
        print('\nNot downloaded reports (due error)')
        PrintService.print_signals(not_downloaded_reports)

    if not (downloaded_reports + not_downloaded_reports):
        print('\nNo signals available')


def main():
    parser = create_parser()
    args = parser.parse_args()
    if args.action == LIST_ACTION:
        handle_list(args)
    elif args.action == UPLOAD_ACTION:
        handle_upload(args)
    elif args.action == DOWNLOAD_ACTION:
        handle_download(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
