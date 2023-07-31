# /usr/bin/python3
import argparse
import errno
import os
from datetime import datetime
from pathlib import Path

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

    def __init__(self, access_token):
        self._access_token = access_token
        self._api_client = requests.Session()

        self._api_client.headers['Private-Token'] = self._access_token

    def _get_signals_request(self, page, new=None):
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

    def post_new_signal(self, name, file_name):
        url = self._CARTIOMATICS_API_URL + self._SIGNALS_ENDPOINT

        response = self._api_client.post(url, json={'name': name, 'file_names_list': [file_name]})

        if response.status_code == 401:
            raise self.AccessDeniedError

        elif response.status_code == 201:
            return response.json()

        else:
            raise NotImplementedError

    def upload_file_to_object_storage(self, url, file, post_fields):
        response = requests.post(url, files={'file': file}, data=post_fields, stream=True)

        if not response.ok:
            raise self.ObjectStorageUploadError

    def _get_list_signals_batches(self, new=None):
        last_page, data = self._get_signals_request(1, new=new)
        yield data

        for page in range(2, int(last_page) + 1):
            _, data = self._get_signals_request(page, new=new)
            yield data

    def get_list_signals_batches(self, new=None):
        iterator = iter(self._get_list_signals_batches(new=new))

        while True:
            try:
                signals_batch = next(iterator)

            except APIService.AccessDeniedError:
                print(INVALUD_TOKEN_MESSAGE)
                exit(1)

            except StopIteration:
                break

            yield signals_batch

    def request_printout(self, signal_id):
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

    def download_file(self, url):
        response = requests.get(url, stream=True)

        if response.ok:
            return response

        else:
            raise NotImplementedError


def download_file_with_progress_bar(api_service, url, dir_path, file_name):
    CHUNK_SIZE = 1024
    download_dest = os.path.join(dir_path, file_name)

    try:
        with api_service.download_file(url) as response:
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
    def dir_path(string):
        if os.path.isdir(string):
            return string
        else:
            print('Not a directory')
            exit(1)

    ACCESS_TOKEN_ARGUMENT = '--access-token'

    parser = argparse.ArgumentParser(description='Cardiomatics Console Client')
    subparsers = parser.add_subparsers(dest='action', title='Available actions', required=True)

    list_parser = subparsers.add_parser(LIST_ACTION, help='List signals')
    list_parser.add_argument(ACCESS_TOKEN_ARGUMENT, required=True, help='Access token for authentication')

    upload_parser = subparsers.add_parser(UPLOAD_ACTION, help='Upload signal')
    upload_parser.add_argument('--file-path', help='File path to the signal file', type=argparse.FileType('rb'))
    upload_parser.add_argument('--name', help="Name")
    upload_parser.add_argument(ACCESS_TOKEN_ARGUMENT, required=True, help='Access token for authentication')

    download_parser = subparsers.add_parser(DOWNLOAD_ACTION, help='Download action')
    download_parser.add_argument(ACCESS_TOKEN_ARGUMENT, required=True, help='Access token for authentication')
    download_parser.add_argument('--dir-path', help='Download directory path', type=dir_path)
    download_parser.add_argument(
        '--new',
        action='store_true',
        help='Filtering by only new signals',
        default=False,
    )

    return parser


def signals_object_to_column(signal):
    return [
        signal.get('id'),
        signal.get('physician').get('name'),
        signal.get('created_at'),
        signal.get('status'),
        signal.get('new'),
    ]


def print_signals(signals):
    columned_data_list = [signals_object_to_column(signal) for signal in signals]

    print(
        tabulate(
            columned_data_list,
            headers=["ID", "Name", "Created at", "Status", "New"],
            tablefmt="signals-table",
            showindex=False,
        )
    )


def handle_list(args):
    api_service = APIService(args.access_token)
    signals = []

    signal_batches_iterator = iter(api_service.get_list_signals_batches())

    for signals_batch in signal_batches_iterator:
        for signal in signals_batch:
            signals.append(signal)

    print('\nList of signals:')
    print_signals(signals)


def handle_upload(args):
    api_service = APIService(args.access_token)

    file_name = os.path.basename(args.file_path.name)

    try:
        response_dict = api_service.post_new_signal(args.name, file_name)
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


def get_local_filename(base_file_name):
    file_without_extension = Path(base_file_name).stem
    file_extension = Path(base_file_name).suffix
    now = datetime.now().isoformat()
    return f'{file_without_extension}-{now}{file_extension}'


def handle_download(args):
    api_service = APIService(args.access_token)

    signal_batches_iterator = iter(api_service.get_list_signals_batches(new=args.new))

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
        print_signals(downloaded_reports)

    if not_downloaded_reports:
        print('\nNot downloaded reports (due error)')
        print_signals(not_downloaded_reports)

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
