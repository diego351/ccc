# CCC

1. Assuming you have latest python3 installed, open up ccc directory: `cd ccc`
2. Create virtualenv: `python3 -m venv .venv`
3. Activate virutalenv: `source .venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. For general help call: `python ccc.py -h`
6. For list action help call: `python ccc.py list -h`
7. For upload action help call: `python ccc.py upload -h`
8. For download action help call: `python ccc.py download -h`
9. Run tests: `python -m pytest tests.py`

## General usage

1. List: `python ccc.py list —-access-token token`
2. Upload: `python ccc.py upload --file-path /file/path/RECORD.GTM  --name name —-access-token=token`
3. Download: `python ccc.py download --dir-path /tmp -—access-token=token`
4. Download nw: `python ccc.py download --dir-path /tmp --new -—access-token=token`
